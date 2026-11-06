"""Read-only inventory of existing non-addon RIFT telemetry files in one lab.

Does not enable combat logging, read log contents, or modify game/config files.
All paths are candidate locations, not exhaustive filesystem search results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_codex import LabCodex
from scripts.vmware_guest_session import POWERSHELL, SessionError


GUEST = r'''
$ErrorActionPreference='Stop'
$game=Get-Process -Id $ExpectedPid -ErrorAction Stop
if($game.ProcessName -ne 'rift_x64' -or !(Test-Path -LiteralPath $game.Path -PathType Leaf)){
    throw 'rift-game-not-found'
}
$actualTicks=[string]$game.StartTime.ToUniversalTime().Ticks
$actualSha=(Get-FileHash -LiteralPath $game.Path -Algorithm SHA256).Hash
if($actualTicks -ne $ExpectedTicks -or $actualSha -ne $ExpectedSha){
    throw 'game-identity-mismatch'
}
if(Test-Path -LiteralPath $OutputPath){throw 'output-already-exists'}
$gameDir=Split-Path -Parent $game.Path
$appData=[Environment]::GetFolderPath('ApplicationData')
$documents=[Environment]::GetFolderPath('MyDocuments')
$locations=@(
    @{kind='combat-log';path=(Join-Path $gameDir 'CombatLog.txt')},
    @{kind='combat-log';path=(Join-Path $gameDir 'Log\CombatLog.txt')},
    @{kind='combat-log';path=(Join-Path $appData 'RIFT\CombatLog.txt')},
    @{kind='combat-log';path=(Join-Path $documents 'RIFT\CombatLog.txt')},
    @{kind='client-config';path=(Join-Path $appData 'RIFT\Rift.cfg')},
    @{kind='client-config';path=(Join-Path $gameDir 'Rift.cfg')},
    @{kind='ability-db';path=(Join-Path $gameDir 'telara.db')},
    @{kind='ability-db';path=(Join-Path $gameDir 'Data\telara.db')},
    @{kind='ability-db';path=(Join-Path $gameDir 'Assets\telara.db')}
)
$configOptions=@{}
foreach($location in $locations){
    if($location.kind -ne 'client-config' -or
       !(Test-Path -LiteralPath $location.path -PathType Leaf)){continue}
    foreach($line in (Get-Content -LiteralPath $location.path -TotalCount 500)){
        if($line -match '(?i)^\s*(LogCombatConsole|DocumentsDirectory|CombatLogFileFlushInterval)\s*=\s*(.*?)\s*$'){
            $key=$Matches[1]
            $value=$Matches[2].Trim().Trim('"').Trim()
            if($value.Length -le 256){$configOptions[$key]=$value}
        }
    }
}
$directoryOverride=$configOptions['DocumentsDirectory']
if($directoryOverride -and [System.IO.Path]::IsPathRooted($directoryOverride)){
    $locations+=@{kind='combat-log';path=(Join-Path $directoryOverride 'CombatLog.txt')}
    $locations+=@{kind='combat-log';path=(Join-Path $directoryOverride 'RIFT\CombatLog.txt')}
}
$files=@(foreach($location in $locations){
    if(Test-Path -LiteralPath $location.path -PathType Leaf){
        $item=Get-Item -LiteralPath $location.path -ErrorAction Stop
        [pscustomobject]@{
            kind=$location.kind;path=$item.FullName
            bytes=[long]$item.Length;modifiedUtc=$item.LastWriteTimeUtc.ToString('o')
        }
    }
})
$report=@{
    schemaVersion=1;evidenceKind='rift-passive-source-inventory/1'
    acquiredUtc=[DateTime]::UtcNow.ToString('o')
    computer=$env:COMPUTERNAME
    game=@{processId=$game.Id;processStartUtcTicks=[long]$actualTicks
           executableSha256=$actualSha;executablePath=$game.Path}
    checkedPaths=$locations.Count
    files=$files
    clientSettings=$configOptions
    limitation='Expected paths and configured DocumentsDirectory only; no log contents, writes or full game-directory search.'
}
$report|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $OutputPath -Encoding UTF8
'''


def ps_literal(value: str) -> str:
    """Quote a literal PowerShell string without allowing expression expansion."""
    return "'" + value.replace("'", "''") + "'"


def run(lab: str, game_pid: int, start_ticks: int, game_sha: str) -> dict:
    if lab not in ("lab1", "lab2") or game_pid <= 0 or start_ticks <= 0:
        raise ValueError("invalid-lab-or-game-identity")
    if not re.fullmatch(r"[0-9A-Fa-f]{64}", game_sha):
        raise ValueError("invalid-game-executable-sha")
    api = LabCodex()
    _, _, config, settings = api._configuration(lab)
    native = api._native(config, settings, api.run_root / ".doctor")
    vm_identity = api.collect_identity(native)
    folder = ROOT / "artifacts" / "passive-game-sources" / lab / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    guest_prefix = settings["guestRoot"] + "\\passive-source-inventory-" + uuid.uuid4().hex
    guest_output = guest_prefix + ".json"
    guest_script = guest_prefix + ".ps1"
    commands = [
        "$ExpectedPid=" + str(game_pid),
        "$ExpectedTicks=" + ps_literal(str(start_ticks)),
        "$ExpectedSha=" + ps_literal(game_sha.upper()),
        "$OutputPath=" + ps_literal(guest_output),
        GUEST,
    ]
    with tempfile.TemporaryDirectory() as temporary:
        local_script = Path(temporary) / "inventory.ps1"
        local_script.write_text("\n".join(commands), encoding="utf-8")
        expected_sha = hashlib.sha256(local_script.read_bytes()).hexdigest().upper()
        with api._session(config, settings, vm_identity, folder) as guest:
            guest.run("copyFileFromHostToGuest", str(local_script), guest_script)
            try:
                guest.powershell(
                    "if((Get-FileHash -LiteralPath " + ps_literal(guest_script) +
                    ").Hash -ne " + ps_literal(expected_sha) +
                    "){throw 'source-inventory-script-hash'}", timeout=30)
                guest.run("runProgramInGuest", POWERSHELL, "-NoProfile",
                          "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-File", guest_script, timeout=45)
                guest.copy_from_guest(guest_output, folder / "inventory.json")
            finally:
                try:
                    guest.powershell("Remove-Item -LiteralPath " +
                                     ps_literal(guest_script) +
                                     " -Force -ErrorAction SilentlyContinue", timeout=30)
                except SessionError:
                    pass
    report = json.loads((folder / "inventory.json").read_text(encoding="utf-8-sig"))
    game = report["game"]
    if (report["schemaVersion"] != 1 or
            report["evidenceKind"] != "rift-passive-source-inventory/1" or
            game["processId"] != game_pid or game["processStartUtcTicks"] != start_ticks or
            game["executableSha256"].upper() != game_sha.upper()):
        raise ValueError("guest-inventory-identity-or-schema-invalid")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--lab", choices=("lab1", "lab2"), required=True)
    p.add_argument("--game-pid", type=int, required=True)
    p.add_argument("--game-start-ticks", type=int, required=True)
    p.add_argument("--game-sha", required=True)
    a = p.parse_args()
    report = run(a.lab, a.game_pid, a.game_start_ticks, a.game_sha)
    print(json.dumps({
        "lab": a.lab,
        "gamePid": report["game"]["processId"],
        "computer": report["computer"],
        "checkedPaths": report["checkedPaths"],
        "files": report["files"],
        "clientSettings": report["clientSettings"],
        "limitation": report["limitation"],
    }, indent=2))


if __name__ == "__main__":
    main()

