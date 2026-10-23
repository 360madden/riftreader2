# Live RIFT known-position pointer recovery — October 23, 2026

## Outcome: same-build native pointer resolution restored

The game remained in RIFT-Lab-1, VM process PID 31884, running the
unchanged on-disk RIFT executable:

- Game PID: 2768
- Game creation ticks: 639282812576974124
- Executable SHA-256:
  7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD
- Historical candidate root RVA: 0x32E0200
- Prior observed float32 XYZ offsets in its owner: 0x320 / 0x324 / 0x328

The original Windows Run approach was correctly rejected after repeated
failure to dispatch even short commands. The replacement execution path
uses the **already open guest PowerShell prompt**, with each keystroke
sent through the existing exact-VM VNC console under its exclusive
maintenance mutex. It is NOT Windows Run.

A harmless direct-shell command first executed and showed the exact
marker RR2_DIRECT_SHELL_OK. The old Run/BAT transport's command quoting
was shown to be incompatible with direct PowerShell redirection.
The recovered sequence instead used PowerShell Set-Content, Add-Content,
guest certutil -decode, and guest Get-FileHash against a new guest-local
request file. The screenshot shows:

- Certutil decoded precisely 321 bytes.
- The guest SHA-256 exactly matched the pinned canonical request hash:
  76FE68E1446396AD32E0E6CC5D0219DE6C5E9205C4FAF9BED66E21C225CE505E.
- The exact request included the current PID/start/build and a maximum
  5-second read for the known module-relative root.
- The existing deployed RiftReader2.Live.exe follow-pointer command was
  subsequently invoked once. Its returned JSON recorded a completed
  pointer resolution and an 816-byte terminalRead with status success,
  no failed read address and no failed read.
- Float32 decoded from terminal offsets 0x320/0x324/0x328:
  X=7459.142, Y=863.7189, Z=2973.08.
- SHA-256 of the native report, independently displayed by the guest:
  40351546D62620736D40BA89B487EA8157E75DFA713B7B1E1D71F1790E0896AE.

The native report itself remains in the guest user's TEMP folder as
rr2-oct23v3-report.json. The host has retained screenshot and console
session evidence, not a byte-for-byte host copy of the full report.
This limitation must be preserved when determining independent
qualification. The new game process produced a successful chain, which
supports **same-build position-locator recovery across process epochs**.
It does not independently establish that XYZ is the player's actual
position without a fresh typed Lua reference.

Evidence under ignored artifacts/update-recovery-20261023-01:

- direct-shell-benign-proof/screen.png — SHA-256
  CF845717E4CD1D09B598F2EF55A3377271315D3239393290560FCF4E12C3462A
- direct-ps-hash-check-v3/screen.png — SHA-256
  37276F583240C3349892E29EC581B0B734292AD67E96B18F12D2B86CF2A4E295
- direct-ps-follow-v3/screen.png — SHA-256
  B5978815B6C41CEFB0517D5380D713B54F9C52C9378EF547D34167AE937C8A1A
- direct-native-xyz-v3/screen.png — SHA-256
  A676D09C460F86917C43B5EBD3E0E46C85C959CD6F21D147A33FCE33B2F63F3F

## Repeatable command preparation

Tracked source: scripts/prepare_direct_shell_pointer.py
Tracked tests: tests/test_direct_shell_pointer.py

The planner produces exact, session-bound native-pointer-follow-request/1
bytes and bounded PowerShell commands. It NEVER launches a game reader,
connects to the VM, or assumes Windows Run is usable. Each step must
execute inside a visually verified guest PowerShell prompt under sole
console ownership. The planner requires a strict PID/start/build, safe
guest executable path and command limits. Source files are atomically
published without overwriting existing plans. The guest request hash
must be compared to the manifest BEFORE native execution.

The new standalone suite passed eight tests, including a **real host
Windows PowerShell 5.1 and certutil** 321-byte reconstruction roundtrip.
It verifies identity validation, unsafe inputs, deterministic requests,
atomic no-overwrite and lack of native execution during planning.
The source plan for PID 2768 remains ignored at
artifacts/update-recovery-20261023-01/direct-ps-source-plan;
its manifest has 10 commands and the above request hash.

## Runtime restoration and remaining acceptance gates

After native inspection, the guest diagnostic terminal was closed, and
the native coordinated host was restored with a new pinned V6 process
and shutdown marker instead of clearing/reusing the maintenance marker.
The restored host PID is 4028 in Windows session 2. Ports 49712/49715
are owned by that process. The existing guest agent reconnected,
coordinator ready, supervisor running, disarmed/idle and no held inputs.
The game PID/start/build were unchanged throughout; game foreground was
not established by the final status query.

A fresh typed-Lua observation for PID 2768 was NOT available. Existing
field-discovery and movement-parity receipts were from older game
processes (e.g. 8356 and 3400), and were correctly refused as a
comparison oracle. The same-build native chain read is successful, but
current XYZ semantics and health/resource data remain candidate-only.
Next recover the read-only Lua observer and compare same-epoch XYZ,
then capture genuinely changed health/resource samples. Do not use
old absolute heap pointers or start unrelated discovery until that
independent reference is restored.

Tracked concurrent navigation/controller files were left untouched
throughout this recovery.

## Validation completed

The focused direct-shell planner suite passed **8/8 tests**, including a
real Windows PowerShell 5.1 + certutil byte-identical JSON reconstruction.
The full repository PowerShell 7 gate passed with exit 0 on October 23
(job rr2_direct_shell_full_gate_169): 364 C# tests (274 core + 90 Windows),
462 Python tests, 108 Lua assertions, 22 actual Lua-to-C# contract cases,
a zero-warning .NET 10 Release build, locked restore, formatting and
332 relative documentation links. Local ignored gate evidence:
`artifacts/validation/20261023T233256Z-4f2e19d1`.
The focused eight new tests are **additional**, not part of the 462 Python
full-gate count, because the concurrent navigation workflow owns
`scripts/validate.ps1` and it was deliberately left unchanged.

Post-maintenance native host V6 was confirmed alive in Windows session 2,
PID 4028, with native ports 49712/49715, guest connected, coordinator ready,
supervisor running, game PID 2768, recoveryRequired false, disarmed and
no held desktop inputs. The game was not foreground according to the final
control host status; that is not a claim of gameplay-input readiness.

