# Invoked by run_xyz_workflow.py with a generated, base64-encoded settings object.
# No credentials or input actions are part of this guest script.
$ErrorActionPreference = 'Stop'
$settings = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__SETTINGS_BASE64__')) | ConvertFrom-Json
$utf8 = New-Object System.Text.UTF8Encoding($false)
$root = $settings.guestOutput
$out = Join-Path $root $settings.phase
function Assert-PlainPath([string]$path) {
    $current = [IO.Path]::GetFullPath($path)
    while ($current) {
        if ((Test-Path -LiteralPath $current) -and
            ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Linked guest path refused'
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}
Assert-PlainPath $root
Assert-PlainPath $settings.guestDirectory
if ($settings.phase -eq 'baseline') {
    if (Test-Path -LiteralPath $root) { throw 'Run directory already exists' }
    New-Item -ItemType Directory -Path $root | Out-Null
} elseif (-not (Test-Path -LiteralPath $root -PathType Container)) {
    throw 'Baseline run directory is missing'
}
if (Test-Path -LiteralPath $out) { throw 'Evidence directory already exists' }
New-Item -ItemType Directory -Path $out | Out-Null
$status = @{ phase=$settings.phase; target=$settings.target; noGameInput=$true; completed=$false }
try {
    $reader = Join-Path $settings.guestDirectory 'RiftReader2.Live.exe'
    $profile = Join-Path $settings.guestDirectory 'position-candidate-profile.json'
    Assert-PlainPath $reader
    Assert-PlainPath $profile
    if ((Get-FileHash -LiteralPath $reader -Algorithm SHA256).Hash -ne $settings.readerSha256) { throw 'Reader hash changed' }
    if ((Get-FileHash -LiteralPath $profile -Algorithm SHA256).Hash -ne $settings.profileSha256) { throw 'Profile hash changed' }
    $game = @(Get-Process -Name rift_x64 -ErrorAction Stop)
    if ($game.Count -ne 1 -or $game[0].Id -ne $settings.target.processId -or
        $game[0].StartTime.ToUniversalTime().Ticks -ne $settings.target.processStartUtcTicks) { throw 'Game epoch changed' }
    [IO.File]::WriteAllText((Join-Path $out 'pointer-request.json'),$settings.pointerRequest,$utf8)
    [IO.File]::WriteAllText((Join-Path $out 'typed-request.json'),$settings.typedRequest,$utf8)
    & $reader sample-position --profile $profile --samples 3 --interval-ms 500 --output (Join-Path $out 'samples.json') 1> (Join-Path $out 'samples.stdout.txt') 2> (Join-Path $out 'samples.stderr.txt')
    $status.sampleExit = $LASTEXITCODE
    & $reader follow-pointer --request (Join-Path $out 'pointer-request.json') --output (Join-Path $out 'pointer.json') 1> (Join-Path $out 'pointer.stdout.txt') 2> (Join-Path $out 'pointer.stderr.txt')
    $status.pointerExit = $LASTEXITCODE
    & $reader scout-copy-typed-native --request (Join-Path $out 'typed-request.json') --output (Join-Path $out 'lua') 1> (Join-Path $out 'lua.stdout.txt') 2> (Join-Path $out 'lua.stderr.txt')
    $status.luaExit = $LASTEXITCODE
    $status.completed = $true
} catch {
    $status.error = $_.Exception.Message
}
$status.atUtc = [DateTime]::UtcNow.ToString('o')
[IO.File]::WriteAllText((Join-Path $out 'status.json'),($status | ConvertTo-Json -Depth 8 -Compress),$utf8)
$files = @(Get-ChildItem -LiteralPath $out -File -Recurse | ForEach-Object {
    Assert-PlainPath $_.FullName
    @{ path=$_.FullName.Substring($out.Length+1).Replace('\','/'); byteLength=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
})
$totalBytes = 0L
foreach ($entry in $files) { $totalBytes += [long]$entry.byteLength }
if ($files.Count -gt 128 -or $totalBytes -gt 16777216) { throw 'Evidence exceeds transfer bounds' }
[IO.File]::WriteAllText((Join-Path $out 'files.json'),(ConvertTo-Json -InputObject $files -Depth 8 -Compress),$utf8)
$zip = Join-Path $root ($settings.phase+'.zip')
if (Test-Path -LiteralPath $zip) { throw 'Archive already exists' }
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip
$receipt = @{ phase=$settings.phase; sha256=(Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash; byteLength=(Get-Item -LiteralPath $zip).Length; status=$status }
[IO.File]::WriteAllText((Join-Path $root ($settings.phase+'.receipt.json')),($receipt | ConvertTo-Json -Depth 8 -Compress),$utf8)
exit 0
