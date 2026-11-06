"""Dispatch bounded read-only Codex CLI jobs to identity-pinned RIFT lab VMs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from vm_console_native import collect_identity, validate_config, verify_identity
from vmware_guest_session import GuestSession, POWERSHELL, SessionError


DEFAULT_CONFIG = ROOT / ".local" / "lab-codex.json"
WORKER = ROOT / "scripts" / "Invoke-LabCodexJob.ps1"
REPORT_SCHEMA = ROOT / "contracts" / "lab-codex" / "report.schema.json"
RUN_ROOT = ROOT / "artifacts" / "lab-codex"
MAX_JSON = 2 * 1024 * 1024
MAX_REPORT = 256 * 1024
MAX_TASK = 256 * 1024
MAX_INPUT = 2 * 1024 * 1024
MAX_INPUTS = 32
MAX_TOTAL_INPUT = 16 * 1024 * 1024
TERMINAL = frozenset({"succeeded", "failed", "timed-out", "cancelled"})
ALL_STATUS = TERMINAL | {"starting", "running"}
STATE_FIELDS = {
    "schemaVersion", "jobId", "lab", "requestSha256", "workerSha256",
    "status", "workerPid", "workerStartUtcTicks", "cliPid", "cliStartUtcTicks",
    "cliSha256", "cliVersion", "cliExitCode", "errorCode", "startedAtUtc",
    "updatedAtUtc", "completedAtUtc", "report",
}
PS_SHA256 = ("function Get-LabCodexSha256($p){$s=[Security.Cryptography.SHA256]::Create();"
             "$f=[IO.File]::OpenRead($p);try{([BitConverter]::ToString("
             "$s.ComputeHash($f))).Replace('-','')}finally{$f.Dispose();$s.Dispose()}};")
DOCTOR_COLLECTOR = r'''param([string]$CliPath,[string]$ResultPath)
$ErrorActionPreference='Stop'
function Get-LabCodexSha256($p){$s=[Security.Cryptography.SHA256]::Create();$f=[IO.File]::OpenRead($p);try{([BitConverter]::ToString($s.ComputeHash($f))).Replace('-','')}finally{$f.Dispose();$s.Dispose()}}
function Invoke-Rr2DoctorProcess([string]$p,[string]$a){
  $i=New-Object Diagnostics.ProcessStartInfo;$i.FileName=$p;$i.Arguments=$a
  $i.UseShellExecute=$false;$i.CreateNoWindow=$true;$i.RedirectStandardOutput=$true;$i.RedirectStandardError=$true
  $q=New-Object Diagnostics.Process;$q.StartInfo=$i
  try {
    if(-not $q.Start()){return [pscustomobject]@{code=$null;output='';errorCode='start-failed'}}
    $ot=$q.StandardOutput.ReadToEndAsync();$et=$q.StandardError.ReadToEndAsync()
    if(-not $q.WaitForExit(15000)){try{$q.Kill()}catch{};if(-not $q.WaitForExit(3000)){return [pscustomobject]@{code=$null;output='';errorCode='cleanup-failed'}};return [pscustomobject]@{code=$null;output='';errorCode='timeout'}}
    $o=$ot.GetAwaiter().GetResult();[void]$et.GetAwaiter().GetResult()
    if($o.Length-gt4096){$o=$o.Substring(0,4096)}
    [pscustomobject]@{code=$q.ExitCode;output=$o;errorCode=$null}
  } catch { [pscustomobject]@{code=$null;output='';errorCode='process-failed'} }
  finally {$q.Dispose()}
}
$r=[ordered]@{schemaVersion=1;phase='initializing';byteLength=$null;sha256=$null;version=$null;versionExitCode=$null;loginExitCode=$null;loginAvailable=$false;errorCode=$null;exceptionType=$null;fullyQualifiedErrorId=$null;scriptLine=$null}
try {
  $r.phase='cli-metadata'
  $i=Get-Item -LiteralPath $CliPath -Force
  $r.byteLength=[long]$i.Length
  if($i.PSIsContainer-or($i.Attributes-band[IO.FileAttributes]::ReparsePoint)-ne0){$r.errorCode='cli-metadata-invalid'}
  if($null-eq$r.errorCode){$r.phase='cli-version';$x=Invoke-Rr2DoctorProcess $CliPath '--version';if($null-ne$x.errorCode){$r.errorCode='cli-version-'+$x.errorCode}else{$r.versionExitCode=$x.code;$m=[regex]::Match($x.output,'(?i)codex(?:-cli)?\s+[0-9][0-9A-Za-z.+-]{0,63}');if($x.code-ne0){$r.errorCode='cli-version-exit'}elseif(-not$m.Success){$r.errorCode='cli-version-invalid'}else{$r.version=$m.Value}}}
  if($null-eq$r.errorCode){$r.phase='cli-login';$x=Invoke-Rr2DoctorProcess $CliPath 'login status';if($null-ne$x.errorCode){$r.errorCode='cli-login-'+$x.errorCode}else{$r.loginExitCode=$x.code;$r.loginAvailable=($x.code-eq0);if(-not$r.loginAvailable){$r.errorCode='cli-login-unavailable'}}}
  $r.phase='cli-sha256';$r.sha256=Get-LabCodexSha256 $i.FullName
  if($null-eq$r.errorCode){$r.phase='completed'}
} catch {
  $r.errorCode='cli-doctor-failed';$r.exceptionType=$_.Exception.GetType().FullName
  $identifier=[string]$_.FullyQualifiedErrorId;if($identifier.Length-gt160-or$identifier-notmatch'^[A-Za-z0-9,._:+-]*$'){$identifier='sanitized-error-id'}
  $r.fullyQualifiedErrorId=$identifier;$r.scriptLine=[int]$_.InvocationInfo.ScriptLineNumber
} finally {
  [IO.File]::WriteAllText($ResultPath,(ConvertTo-Json $r -Compress)+"`n",(New-Object Text.UTF8Encoding($false)))
}
'''


class LabCodexError(RuntimeError):
    """A stable failure that excludes guest output, credentials and raw argv."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _json_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise LabCodexError("duplicate-json-property")
        value[key] = item
    return value


def _decode_json(data: bytes, *, maximum: int = MAX_JSON):
    if not 0 < len(data) <= maximum:
        raise LabCodexError("json-size-invalid")
    try:
        return json.loads(data.decode("utf-8-sig"), object_pairs_hook=_json_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LabCodexError("json-invalid") from error


def _read_json(path: Path, *, maximum: int = MAX_JSON):
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file() or resolved.is_symlink():
            raise LabCodexError("file-unavailable")
        return _decode_json(resolved.read_bytes(), maximum=maximum)
    except OSError as error:
        raise LabCodexError("file-unavailable") from error


def _write_new(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise LabCodexError("output-already-exists") from error


def _write_bytes_new(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with temporary.open("xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise LabCodexError("output-already-exists") from error
        except OSError as error:
            raise LabCodexError("output-publication-failed") from error
    finally:
        temporary.unlink(missing_ok=True)


def _label(value, name: str, maximum: int = 128) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= maximum
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value)):
        raise LabCodexError(f"invalid-{name}")
    return value


def _windows_path(value, name: str) -> str:
    if (not isinstance(value, str) or len(value) > 1024
            or not re.match(r"^[A-Za-z]:\\", value)
            or any(char in value for char in "'\"\r\n")
            or any(part in ("", ".", "..") for part in PureWindowsPath(value).parts[1:])):
        raise LabCodexError(f"invalid-{name}")
    return str(PureWindowsPath(value))


def _safe_relative(root: Path, value, name: str, *, maximum: int,
                   tracked: bool = True) -> tuple[str, Path, bytes]:
    if not isinstance(value, str) or "\\" in value or Path(value).is_absolute():
        raise LabCodexError(f"invalid-{name}-path")
    relative = Path(value)
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise LabCodexError(f"invalid-{name}-path")
    try:
        resolved = (root / relative).resolve(strict=True)
        resolved.relative_to(root.resolve())
        if not resolved.is_file() or resolved.is_symlink():
            raise LabCodexError(f"invalid-{name}-file")
        data = resolved.read_bytes()
    except (OSError, ValueError) as error:
        raise LabCodexError(f"invalid-{name}-file") from error
    if not 0 < len(data) <= maximum:
        raise LabCodexError(f"invalid-{name}-size")
    normalized = relative.as_posix()
    if tracked:
        tracked_result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", normalized],
            capture_output=True, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if tracked_result.returncode:
            raise LabCodexError(f"untracked-{name}")
    return normalized, resolved, data


def load_config(path: Path) -> tuple[Path, bytes, dict]:
    try:
        resolved = path.resolve(strict=True)
        data = resolved.read_bytes()
    except OSError as error:
        raise LabCodexError("config-unavailable") from error
    value = _decode_json(data, maximum=64 * 1024)
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "vmrun", "labs"}:
        raise LabCodexError("config-fields-invalid")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        raise LabCodexError("config-schema-invalid")
    vmrun = Path(_windows_path(value["vmrun"], "vmrun"))
    labs = value["labs"]
    if not isinstance(labs, dict) or not 1 <= len(labs) <= 32:
        raise LabCodexError("config-labs-invalid")
    parsed = {}
    vmx_paths = set()
    vnc_ports = set()
    for raw_name, raw in labs.items():
        name = _label(raw_name, "lab")
        expected = {"vmx", "vncPort", "cliPath", "guestRoot"}
        if not isinstance(raw, dict) or not (set(raw) == expected or
                                             set(raw) == expected | {"legacyGuestVmx"}):
            raise LabCodexError("lab-config-fields-invalid")
        port = raw["vncPort"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise LabCodexError("invalid-vnc-port")
        vmx = Path(_windows_path(raw["vmx"], "vmx"))
        legacy_vmx = (Path(_windows_path(raw["legacyGuestVmx"], "legacy-guest-vmx"))
                      if "legacyGuestVmx" in raw else None)
        if legacy_vmx is not None and str(legacy_vmx).casefold() == str(vmx).casefold():
            raise LabCodexError("duplicate-legacy-guest-vmx")
        vmx_key = str(PureWindowsPath(str(vmx))).replace("/", "\\").casefold()
        if vmx_key in vmx_paths:
            raise LabCodexError("duplicate-vmx")
        if port in vnc_ports:
            raise LabCodexError("duplicate-vnc-port")
        vmx_paths.add(vmx_key); vnc_ports.add(port)
        parsed[name] = {
            "vmx": vmx,
            "vncPort": port,
            "cliPath": _windows_path(raw["cliPath"], "cli-path"),
            "guestRoot": _windows_path(raw["guestRoot"], "guest-root").rstrip("\\"),
            "legacyGuestVmx": legacy_vmx,
        }
    for entry in parsed.values():
        legacy = entry["legacyGuestVmx"]
        if legacy is not None and str(PureWindowsPath(str(legacy))).casefold() in vmx_paths:
            raise LabCodexError("legacy-guest-vmx-active-conflict")
    return resolved, data, {"vmrun": vmrun, "labs": parsed}


def _report_valid(value) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "summary", "findings", "limitations"
    } or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
        return False
    if not isinstance(value["summary"], str) or len(value["summary"]) > 4000:
        return False
    findings = value["findings"]
    limitations = value["limitations"]
    if not isinstance(findings, list) or len(findings) > 64:
        return False
    if (not isinstance(limitations, list) or len(limitations) > 32
            or any(not isinstance(item, str) or len(item) > 2000 for item in limitations)):
        return False
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"claim", "confidence", "evidence"}:
            return False
        evidence = finding["evidence"]
        if (not isinstance(finding["claim"], str) or len(finding["claim"]) > 4000
                or finding["confidence"] not in ("observed", "inferred", "unverified")
                or not isinstance(evidence, list) or len(evidence) > 16
                or any(not isinstance(item, str) or len(item) > 1000 for item in evidence)):
            return False
    return True


class LabCodex:
    def __init__(self, config_path: Path = DEFAULT_CONFIG, *, repo_root: Path = ROOT,
                 run_root: Path = RUN_ROOT, worker_path: Path = WORKER,
                 session_factory=GuestSession, collect=collect_identity, verify=verify_identity,
                 sleep=time.sleep):
        self.config_path = Path(config_path)
        self.root = Path(repo_root).resolve()
        self.run_root = Path(run_root)
        self.worker_path = Path(worker_path)
        self.session_factory = session_factory
        self.collect_identity = collect
        self.verify_identity = verify
        self.sleep = sleep

    def _configuration(self, lab: str):
        path, data, config = load_config(self.config_path)
        if lab not in config["labs"]:
            raise LabCodexError("unknown-lab")
        return path, data, config, config["labs"][lab]

    def _native(self, config: dict, lab: dict, output: Path):
        return validate_config(lab["vmx"], lab["vncPort"], config["vmrun"], output,
                               require_files=True)

    @staticmethod
    def _no_prompt():
        raise SessionError("cached-guest-credential-required")

    def _session(self, config, lab, identity, output):
        native = self._native(config, lab, output)
        extra = {}
        if lab.get("legacyGuestVmx") is not None:
            extra["legacy_guest_credential_target"] = (
                "RiftReader2 Guest Windows: " + str(lab["legacyGuestVmx"].resolve(strict=False))
            )
        return self.session_factory(
            config["vmrun"], lab["vmx"],
            lambda: self.verify_identity(native, identity),
            _guest_prompt=self._no_prompt, **extra,
        )

    def doctor(self, lab_name: str) -> dict:
        _, config_bytes, config, lab = self._configuration(lab_name)
        if not self.worker_path.is_file() or self.worker_path.is_symlink():
            raise LabCodexError("worker-unavailable")
        worker_sha = _sha(self.worker_path.read_bytes())
        native = self._native(config, lab, self.run_root / ".doctor")
        identity = self.collect_identity(native)
        token = uuid.uuid4().hex
        guest_script = lab["guestRoot"] + "\\doctor-" + token + ".ps1"
        guest_result = lab["guestRoot"] + "\\doctor-" + token + ".json"
        with tempfile.TemporaryDirectory() as directory:
            local_script = Path(directory) / "doctor.ps1"
            local_result = Path(directory) / "doctor.json"
            local_script.write_text(DOCTOR_COLLECTOR, encoding="utf-8", newline="\n")
            with self._session(config, lab, identity, self.run_root / ".doctor") as guest:
                guest.powershell("[IO.Directory]::CreateDirectory('" + lab["guestRoot"] +
                                 "')|Out-Null", timeout=30)
                guest.run("copyFileFromHostToGuest", str(local_script), guest_script, timeout=60)
                guest.run("runProgramInGuest", POWERSHELL, "-NoProfile", "-NonInteractive",
                          "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File",
                          guest_script, "-CliPath", lab["cliPath"], "-ResultPath", guest_result,
                          timeout=60)
                guest.copy_from_guest(guest_result, local_result, timeout=60)
                guest.powershell("Remove-Item -LiteralPath '" + guest_script + "','" +
                                 guest_result + "' -Force -ErrorAction SilentlyContinue", timeout=30)
            cli = _decode_json(local_result.read_bytes(), maximum=4096)
        if (not isinstance(cli, dict) or set(cli) != {"schemaVersion", "phase", "byteLength", "sha256",
                "version", "versionExitCode", "loginExitCode", "loginAvailable", "errorCode",
                "exceptionType", "fullyQualifiedErrorId", "scriptLine"}
                or cli["schemaVersion"] != 1
                or cli["phase"] not in {"initializing", "cli-metadata", "cli-version",
                                        "cli-login", "cli-sha256", "completed"}
                or (cli["version"] is not None and (not isinstance(cli["version"], str)
                                                     or len(cli["version"]) > 128))
                or (cli["versionExitCode"] is not None and type(cli["versionExitCode"]) is not int)
                or (cli["loginExitCode"] is not None and type(cli["loginExitCode"]) is not int)
                or type(cli["loginAvailable"]) is not bool):
            raise LabCodexError("doctor-result-invalid")
        if (cli["exceptionType"] is not None
                and (not isinstance(cli["exceptionType"], str)
                     or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.+]{0,199}", cli["exceptionType"]))):
            raise LabCodexError("doctor-result-invalid")
        if (cli["fullyQualifiedErrorId"] is not None
                and (not isinstance(cli["fullyQualifiedErrorId"], str)
                     or not re.fullmatch(r"[A-Za-z0-9,._:+-]{0,160}",
                                         cli["fullyQualifiedErrorId"]))):
            raise LabCodexError("doctor-result-invalid")
        if cli["scriptLine"] is not None and (type(cli["scriptLine"]) is not int
                                               or cli["scriptLine"] <= 0):
            raise LabCodexError("doctor-result-invalid")
        if cli["errorCode"] is not None:
            if not isinstance(cli["errorCode"], str) or not re.fullmatch(r"[a-z0-9-]{1,64}", cli["errorCode"]):
                raise LabCodexError("doctor-result-invalid")
            detail = "doctor-" + cli["errorCode"] + ":phase=" + cli["phase"]
            if cli["exceptionType"] is not None:
                detail += ":type=" + cli["exceptionType"]
            if cli["scriptLine"] is not None:
                detail += ":line=" + str(cli["scriptLine"])
            if cli["fullyQualifiedErrorId"] is not None:
                detail += ":id=" + cli["fullyQualifiedErrorId"]
            raise LabCodexError(detail)
        if (type(cli["byteLength"]) is not int or cli["byteLength"] <= 0
                or not isinstance(cli["sha256"], str)
                or not re.fullmatch(r"[0-9A-Fa-f]{64}", cli["sha256"])
                or cli["versionExitCode"] != 0 or cli["loginExitCode"] != 0
                or not isinstance(cli["version"], str)):
            raise LabCodexError("doctor-result-invalid")
        if not cli["loginAvailable"]:
            raise LabCodexError("codex-login-unavailable")
        return {"schemaVersion": 1, "status": "ready", "scope": "diagnostic-only",
                "lab": lab_name, "configSha256": _sha(config_bytes),
                "vmIdentity": identity, "workerSha256": worker_sha,
                "cli": {"byteLength": cli["byteLength"],
                        "sha256": cli["sha256"].upper(), "version": cli["version"]},
                "login": "available"}

    def _git_provenance(self) -> dict:
        head = subprocess.run(["git", "-C", str(self.root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
        dirty = subprocess.run(["git", "-C", str(self.root), "status", "--porcelain"],
                               capture_output=True, text=True, check=False)
        if head.returncode or dirty.returncode or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head.stdout.strip()):
            raise LabCodexError("git-provenance-unavailable")
        return {"head": head.stdout.strip().lower(), "dirty": bool(dirty.stdout)}

    def _bundle(self, run_dir: Path, inputs: list[str]):
        if not isinstance(inputs, list) or len(inputs) > MAX_INPUTS or len(set(inputs)) != len(inputs):
            raise LabCodexError("invalid-input-list")
        records = []
        total = 0
        archive = run_dir / "workspace.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("workspace/", b"")
            for item in inputs:
                relative, _, data = _safe_relative(self.root, item, "input", maximum=MAX_INPUT)
                total += len(data)
                if total > MAX_TOTAL_INPUT:
                    raise LabCodexError("input-total-too-large")
                bundle.writestr("workspace/" + relative, data)
                records.append({"path": relative, "byteLength": len(data), "sha256": _sha(data)})
        return archive, records

    def dispatch(self, lab_name: str, task: str, inputs: list[str], timeout_seconds: int = 300) -> dict:
        if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 1800:
            raise LabCodexError("invalid-timeout")
        config_path, config_bytes, config, lab = self._configuration(lab_name)
        task_name, _, task_bytes = _safe_relative(
            self.root, task, "task", maximum=MAX_TASK, tracked=False
        )
        if not self.worker_path.is_file() or self.worker_path.is_symlink():
            raise LabCodexError("worker-unavailable")
        worker_bytes = self.worker_path.read_bytes()
        schema_bytes = REPORT_SCHEMA.read_bytes()
        if not worker_bytes or not isinstance(_decode_json(schema_bytes), dict):
            raise LabCodexError("worker-contract-unavailable")
        job_id = str(uuid.uuid4())
        self.run_root.mkdir(parents=True, exist_ok=True)
        run_dir = self.run_root / job_id
        run_dir.mkdir(exist_ok=False)
        try:
            task_path = run_dir / "task.md"; task_path.write_bytes(task_bytes)
            worker_path = run_dir / "Invoke-LabCodexJob.ps1"; worker_path.write_bytes(worker_bytes)
            schema_path = run_dir / "report.schema.json"; schema_path.write_bytes(schema_bytes)
            archive, input_records = self._bundle(run_dir, inputs)
            native = self._native(config, lab, run_dir / "identity")
            identity = self.collect_identity(native)
            request = {
                "schemaVersion": 1, "jobId": job_id, "lab": lab_name,
                "cliPath": lab["cliPath"], "timeoutSeconds": timeout_seconds,
            }
            request_path = run_dir / "request.json"
            request_bytes = (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode()
            request_path.write_bytes(request_bytes)
            hashes = {path.name: _sha(path.read_bytes()) for path in
                      (worker_path, request_path, task_path, schema_path, archive)}
            guest_job = lab["guestRoot"] + "\\" + job_id
            receipt = {
                "schemaVersion": 1, "jobId": job_id, "lab": lab_name,
                "createdAtUtc": _utc(), "configPath": str(config_path),
                "configSha256": _sha(config_bytes), "guestJobDirectory": guest_job,
                "requestSha256": hashes["request.json"],
                "workerSha256": hashes["Invoke-LabCodexJob.ps1"],
                "reportSchemaSha256": hashes["report.schema.json"],
                "task": {"path": task_name, "byteLength": len(task_bytes),
                         "sha256": hashes["task.md"]},
                "workspaceArchive": {"byteLength": archive.stat().st_size,
                                     "sha256": hashes["workspace.zip"]},
                "inputs": input_records, "git": self._git_provenance(),
                "vmIdentity": identity,
            }
            _write_new(run_dir / "run.json", receipt)
            with self._session(config, lab, identity, run_dir / "identity") as guest:
                guest.powershell(
                    "$ErrorActionPreference='Stop';$p='" + guest_job +
                    "';if(Test-Path -LiteralPath $p){throw 'job-exists'};[IO.Directory]::CreateDirectory($p)|Out-Null",
                    timeout=30,
                )
                for local in (worker_path, request_path, task_path, schema_path, archive):
                    guest.run("copyFileFromHostToGuest", str(local.resolve()),
                              guest_job + "\\" + local.name, timeout=120)
                hash_table = ";".join("'" + name + "'='" + digest + "'"
                                      for name, digest in hashes.items())
                guest.powershell(
                    "$ErrorActionPreference='Stop';" + PS_SHA256 + "$j='" + guest_job +
                    "';$h=@{" + hash_table + "};$h.Keys|%{$p=$j+'\\'+$_;if((Get-LabCodexSha256 $p)-ne$h[$_]){throw " +
                    "'stage-hash-mismatch'}};Expand-Archive -LiteralPath " +
                    "($j+'\\workspace.zip') -DestinationPath $j -Force",
                    timeout=120,
                )
                guest.run(
                    "runProgramInGuest", "-noWait", POWERSHELL, "-NoProfile", "-NonInteractive",
                    "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File",
                    guest_job + "\\Invoke-LabCodexJob.ps1", "-JobDirectory", guest_job,
                    "-RequestSha256", receipt["requestSha256"], timeout=30,
                )
            return {"status": "dispatched", "jobId": job_id, "lab": lab_name,
                    "run": str(run_dir.resolve()), "provenance": receipt}
        except BaseException:
            raise

    def _load_run(self, run: Path):
        run = Path(run)
        if not run.is_absolute():
            raise LabCodexError("run-path-must-be-absolute")
        try:
            run = run.resolve(strict=True)
            run.relative_to(self.run_root.resolve(strict=True))
        except (OSError, ValueError) as error:
            raise LabCodexError("run-path-invalid") from error
        receipt = _read_json(run / "run.json", maximum=256 * 1024)
        required = {"schemaVersion", "jobId", "lab", "createdAtUtc", "configPath",
                    "configSha256", "guestJobDirectory", "requestSha256", "workerSha256",
                    "reportSchemaSha256", "task", "workspaceArchive", "inputs", "git",
                    "vmIdentity"}
        if not isinstance(receipt, dict) or set(receipt) != required or receipt["schemaVersion"] != 1:
            raise LabCodexError("run-receipt-invalid")
        try:
            job_id = str(uuid.UUID(receipt["jobId"]))
        except (ValueError, TypeError, AttributeError) as error:
            raise LabCodexError("run-job-invalid") from error
        if run.name != job_id or receipt["jobId"] != job_id:
            raise LabCodexError("run-job-mismatch")
        _label(receipt["lab"], "lab")
        try:
            expected_config = self.config_path.resolve(strict=True)
            recorded_config = Path(receipt["configPath"]).resolve(strict=True)
        except OSError as error:
            raise LabCodexError("config-unavailable") from error
        if recorded_config != expected_config:
            raise LabCodexError("run-config-mismatch")
        config_path, config_bytes, config = load_config(Path(receipt["configPath"]))
        if _sha(config_bytes) != receipt["configSha256"] or receipt["lab"] not in config["labs"]:
            raise LabCodexError("config-drift")
        lab = config["labs"][receipt["lab"]]
        if receipt["guestJobDirectory"] != lab["guestRoot"] + "\\" + job_id:
            raise LabCodexError("run-guest-path-mismatch")
        native = self._native(config, lab, run / "identity")
        if self.verify_identity(native, receipt["vmIdentity"]) != receipt["vmIdentity"]:
            raise LabCodexError("vm-identity-drift")
        return run, receipt, config, lab

    def _copy_guest_json(self, guest, guest_path: str, run: Path, name: str, maximum=MAX_JSON):
        temporary = run / ("." + name + "." + uuid.uuid4().hex)
        try:
            guest.copy_from_guest(guest_path, temporary, timeout=60)
            data = temporary.read_bytes()
            return data, _decode_json(data, maximum=maximum)
        finally:
            temporary.unlink(missing_ok=True)

    def _guest_file_exists(self, guest, guest_path: str, run: Path) -> bool:
        token = uuid.uuid4().hex
        guest_probe = str(PureWindowsPath(guest_path).parent / (".probe-" + token + ".json"))
        local_probe = run / (".probe-" + token + ".json")
        script = ("$t='" + guest_path + "';$o='" + guest_probe +
                  "';$v=if(Test-Path -LiteralPath $t -PathType Leaf){'true'}else{'false'};" +
                  "[IO.File]::WriteAllText($o,('{\"schemaVersion\":1,\"present\":'+$v+'}')," +
                  "(New-Object Text.UTF8Encoding($false)))")
        try:
            guest.powershell(script, timeout=30)
            guest.copy_from_guest(guest_probe, local_probe, timeout=60)
            value = _decode_json(local_probe.read_bytes(), maximum=256)
            if (not isinstance(value, dict) or set(value) != {"schemaVersion", "present"}
                    or value["schemaVersion"] != 1 or type(value["present"]) is not bool):
                raise LabCodexError("state-existence-invalid")
            return value["present"]
        finally:
            local_probe.unlink(missing_ok=True)
            try:
                guest.powershell("Remove-Item -LiteralPath '" + guest_probe +
                                 "' -Force -ErrorAction SilentlyContinue", timeout=30)
            except SessionError:
                pass

    def _state(self, run: Path, receipt: dict, config: dict, lab: dict):
        state_path = receipt["guestJobDirectory"] + "\\state.json"
        with self._session(config, lab, receipt["vmIdentity"], run / "identity") as guest:
            if not self._guest_file_exists(guest, state_path, run):
                raise LabCodexError("state-not-published")
            data, state = self._copy_guest_json(
                guest, state_path, run, "state.json", 256 * 1024
            )
        if not isinstance(state, dict) or set(state) != STATE_FIELDS:
            raise LabCodexError("state-fields-invalid")
        if (state["schemaVersion"] != 1 or state["jobId"] != receipt["jobId"]
                or state["lab"] != receipt["lab"]
                or state["requestSha256"] != receipt["requestSha256"]
                or state["workerSha256"] != receipt["workerSha256"]
                or state["status"] not in ALL_STATUS):
            raise LabCodexError("state-identity-invalid")
        for key in ("workerPid", "workerStartUtcTicks", "cliPid", "cliStartUtcTicks"):
            if state[key] is not None and (type(state[key]) is not int or state[key] <= 0):
                raise LabCodexError("state-type-invalid")
        if state["cliExitCode"] is not None and type(state["cliExitCode"]) is not int:
            raise LabCodexError("state-type-invalid")
        for key in ("cliSha256", "cliVersion", "errorCode", "startedAtUtc", "updatedAtUtc", "completedAtUtc"):
            if state[key] is not None and (not isinstance(state[key], str) or len(state[key]) > 512):
                raise LabCodexError("state-type-invalid")
        if state["cliSha256"] is not None and not re.fullmatch(r"[0-9A-Fa-f]{64}", state["cliSha256"]):
            raise LabCodexError("state-type-invalid")
        if state["errorCode"] is not None and not re.fullmatch(r"[a-z0-9-]{1,128}", state["errorCode"]):
            raise LabCodexError("state-type-invalid")
        report = state["report"]
        if report is not None:
            if (not isinstance(report, dict) or set(report) != {"path", "byteLength", "sha256"}
                    or report["path"] != "report.json" or type(report["byteLength"]) is not int
                    or not 0 < report["byteLength"] <= MAX_REPORT
                    or not re.fullmatch(r"[0-9A-Fa-f]{64}", report["sha256"])):
                raise LabCodexError("state-report-invalid")
        if state["status"] == "succeeded" and report is None:
            raise LabCodexError("state-report-missing")
        if state["status"] == "succeeded" and state["cliExitCode"] != 0:
            raise LabCodexError("state-success-invalid")
        if state["status"] in TERMINAL and state["completedAtUtc"] is None:
            raise LabCodexError("state-terminal-invalid")
        return data, state

    def status(self, run: Path) -> dict:
        run, receipt, config, lab = self._load_run(run)
        _, state = self._state(run, receipt, config, lab)
        return {"schemaVersion": 1, "jobId": receipt["jobId"], "lab": receipt["lab"],
                "status": state["status"], "state": state,
                "evidenceBoundary": "guest-reported-not-accepted-fact"}

    def collect(self, run: Path) -> dict:
        run, receipt, config, lab = self._load_run(run)
        existing = run / "collected.json"
        if existing.exists():
            result = _read_json(existing)
            if (not isinstance(result, dict)
                    or result.get("jobId") != receipt["jobId"]
                    or result.get("lab") != receipt["lab"]
                    or result.get("provenance") != receipt
                    or not isinstance(result.get("state"), dict)
                    or result.get("evidenceBoundary") != "guest-report-requires-main-host-review"):
                raise LabCodexError("collection-invalid")
            report_ref = result["state"].get("report")
            if report_ref is not None:
                if not isinstance(report_ref, dict):
                    raise LabCodexError("collection-report-invalid")
                try:
                    report_bytes = (run / "report.json").read_bytes()
                except OSError as error:
                    raise LabCodexError("collection-report-unavailable") from error
                if (len(report_bytes) != report_ref.get("byteLength")
                        or _sha(report_bytes) != str(report_ref.get("sha256", "")).upper()
                        or not _report_valid(_decode_json(report_bytes))):
                    raise LabCodexError("collection-report-invalid")
            return result
        state_bytes, state = self._state(run, receipt, config, lab)
        if state["status"] not in TERMINAL:
            raise LabCodexError("job-not-terminal")
        report_value = None
        report_ref = state["report"]
        if report_ref is not None:
            with self._session(config, lab, receipt["vmIdentity"], run / "identity") as guest:
                report_bytes, report_value = self._copy_guest_json(
                    guest, receipt["guestJobDirectory"] + "\\report.json", run,
                    "report.json", MAX_REPORT,
                )
            if (len(report_bytes) != report_ref["byteLength"]
                    or _sha(report_bytes) != report_ref["sha256"].upper()
                    or not _report_valid(report_value)):
                raise LabCodexError("report-validation-failed")
            state_after_bytes, state_after = self._state(run, receipt, config, lab)
            if state_after_bytes != state_bytes or state_after != state:
                raise LabCodexError("terminal-state-drift")
            _write_bytes_new(run / "report.json", report_bytes)
        result = {"schemaVersion": 1, "jobId": receipt["jobId"], "lab": receipt["lab"],
                  "status": state["status"], "state": state, "report": report_value,
                  "provenance": receipt,
                  "evidenceBoundary": "guest-report-requires-main-host-review"}
        _write_new(existing, result)
        return result

    def cancel(self, run: Path) -> dict:
        run, receipt, config, lab = self._load_run(run)
        _, state = self._state(run, receipt, config, lab)
        if state["status"] in TERMINAL:
            return {"status": state["status"], "jobId": receipt["jobId"],
                    "lab": receipt["lab"], "cancelRequested": False}
        request = {"jobId": receipt["jobId"], "requestSha256": receipt["requestSha256"]}
        local = run / "cancel.request"
        if not local.exists():
            _write_new(local, request)
        data = local.read_bytes()
        if _decode_json(data) != request:
            raise LabCodexError("cancel-request-drift")
        incoming = receipt["guestJobDirectory"] + "\\cancel.request.incoming"
        final = receipt["guestJobDirectory"] + "\\cancel.request"
        with self._session(config, lab, receipt["vmIdentity"], run / "identity") as guest:
            guest.run("copyFileFromHostToGuest", str(local.resolve()), incoming, timeout=60)
            guest.powershell(
                "$ErrorActionPreference='Stop';" + PS_SHA256 + "$s='" + incoming + "';$d='" + final +
                "';if(Test-Path -LiteralPath $d){Remove-Item -LiteralPath $s -Force}else{" +
                "if((Get-LabCodexSha256 $s)-ne '" + _sha(data) +
                "'){throw 'cancel-hash-mismatch'};Move-Item -LiteralPath $s -Destination $d}",
                timeout=30,
            )
        return {"status": "cancel-requested", "jobId": receipt["jobId"], "lab": receipt["lab"]}

    def run(self, lab: str, task: str, inputs: list[str], timeout_seconds=300,
            poll_seconds=1.0):
        dispatched = self.dispatch(lab, task, inputs, timeout_seconds)
        deadline = time.monotonic() + timeout_seconds + 60
        while True:
            try:
                current = self.status(Path(dispatched["run"]))
            except LabCodexError as error:
                if str(error) != "state-not-published":
                    raise
                if time.monotonic() >= deadline:
                    raise LabCodexError("host-poll-timeout") from None
                self.sleep(poll_seconds)
                continue
            if current["status"] in TERMINAL:
                return self.collect(Path(dispatched["run"]))
            if time.monotonic() >= deadline:
                raise LabCodexError("host-poll-timeout")
            self.sleep(poll_seconds)

    def batch(self, plan_path: Path) -> dict:
        try:
            resolved_plan = Path(plan_path).resolve(strict=True)
            plan_bytes = resolved_plan.read_bytes()
        except OSError as error:
            raise LabCodexError("batch-plan-unavailable") from error
        plan = _decode_json(plan_bytes, maximum=256 * 1024)
        if not isinstance(plan, dict) or set(plan) != {"schemaVersion", "jobs"} \
                or plan["schemaVersion"] != 1 or not isinstance(plan["jobs"], list) \
                or not 1 <= len(plan["jobs"]) <= 32:
            raise LabCodexError("batch-plan-invalid")
        labs = []
        jobs = []
        for item in plan["jobs"]:
            if not isinstance(item, dict) or set(item) != {"lab", "task", "inputs", "timeoutSeconds"}:
                raise LabCodexError("batch-job-invalid")
            lab = _label(item["lab"], "lab")
            if lab in labs:
                raise LabCodexError("batch-lab-duplicate")
            labs.append(lab); jobs.append(item)
        results = [None] * len(jobs)
        with ThreadPoolExecutor(max_workers=len(jobs)) as executor:
            futures = {executor.submit(self.run, item["lab"], item["task"], item["inputs"],
                                       item["timeoutSeconds"]): index
                       for index, item in enumerate(jobs)}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index] = future.result()
                except (LabCodexError, SessionError) as error:
                    results[index] = {"lab": jobs[index]["lab"], "status": "host-failed",
                                      "reason": str(error)}
        self.run_root.mkdir(parents=True, exist_ok=True)
        batch_dir = self.run_root / ("batch-" + str(uuid.uuid4()))
        batch_dir.mkdir(exist_ok=False)
        all_succeeded = all(isinstance(item, dict) and item.get("status") == "succeeded"
                            for item in results)
        result = {"schemaVersion": 1,
                  "status": "succeeded" if all_succeeded else "completed-with-failures",
                  "scope": "guest-reports-require-main-host-review",
                  "createdAtUtc": _utc(),
                  "plan": {"path": str(resolved_plan), "sha256": _sha(plan_bytes)},
                  "jobs": results, "run": str(batch_dir.resolve()),
                  "index": str((batch_dir / "batch.json").resolve())}
        _write_new(batch_dir / "batch.json", result)
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "dispatch", "run", "status", "collect", "cancel", "batch"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path, default=argparse.SUPPRESS)
        if name == "doctor":
            command.add_argument("--lab", required=True)
        elif name in ("dispatch", "run"):
            command.add_argument("--lab", required=True)
            command.add_argument("--task", required=True)
            command.add_argument("--input", action="append", default=[])
            command.add_argument("--timeout-seconds", type=int, default=300)
        elif name in ("status", "collect", "cancel"):
            command.add_argument("--run", required=True, type=Path)
        else:
            command.add_argument("--plan", required=True, type=Path)
    return parser


def _result_exit_code(command: str, result: dict) -> int:
    if command in ("run", "batch") and result.get("status") != "succeeded":
        return 2
    return 0


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    tool = LabCodex(getattr(args, "config", DEFAULT_CONFIG))
    try:
        if args.command == "doctor": result = tool.doctor(args.lab)
        elif args.command == "dispatch": result = tool.dispatch(args.lab, args.task, args.input, args.timeout_seconds)
        elif args.command == "run": result = tool.run(args.lab, args.task, args.input, args.timeout_seconds)
        elif args.command == "status": result = tool.status(args.run)
        elif args.command == "collect": result = tool.collect(args.run)
        elif args.command == "cancel": result = tool.cancel(args.run)
        else: result = tool.batch(args.plan)
        print(json.dumps(result, indent=2, sort_keys=True))
        return _result_exit_code(args.command, result)
    except (LabCodexError, SessionError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
