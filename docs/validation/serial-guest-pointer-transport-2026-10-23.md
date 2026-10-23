# Serialized short-command guest pointer transport — October 23, 2026

## Problem and scope

The historical RIFT player-position pointer at RVA 0x32E0200 is a
**candidate**, previously observed in two process epochs of executable build
7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD.
The current guest process is PID 2768, start ticks
639282812576974124, with that same executable SHA-256.

Recent attempts to follow the pointer from Windows' Run dialog **did not
run the native reader successfully**. The long PowerShell commands suffered
truncated text and parser errors. A nine-action batch of short Windows Run
commands also failed because the guest UI had not settled between commands:
a screenshot showed a Run-dialog failure ("Windows cannot find '/c'"), not
a native memory failure. A clean pointer-follow report and fresh Lua/native
XYZ comparison have **not** been obtained from this process.

Do not call this a memory-layout regression, an update-survival pass or a
qualified position field. The installed game's on-disk executable hash
matches the old baseline; live heap and pointer structures remain unverified.

## Reuse-first fix

New source: scripts/prepare_serial_guest_pointer.py

Rather than write another native memory reader or change the concurrently
owned scripts/vm_console_native.py, this host-only tool builds the existing
native-pointer-follow-request/1 contract, Base64-encodes its exact canonical
JSON, and generates **one bounded Windows Run action per plan file**.
The receiving guest uses existing Windows cmd.exe and certutil.exe to
assemble and decode the request. The native reader is the already installed
RiftReader2.Live.exe with follow-pointer support.

The planner:
- Validates exact PID, creation ticks, uppercase SHA-256, canonical RVA,
  bounded terminal read length, safe guest executable path and temporary
  filename before publishing any file.
- Restricts command length to 180 ASCII characters and plan length to
  20 steps. Chunks are 64 Base64 characters, so CMD does not need to
  parse or quote the complex JSON structure.
- Emits request.json, manifest.json and numbered step-NN.json files into
  an already existing, empty directory. Every file uses no-overwrite
  same-directory publication; existing artifacts are preserved.
- Inserts a guest certutil SHA-256 display after decoding but **before**
  the final native read. The displayed checksum must match the manifest's
  requestSha256. The final step must not be issued otherwise.
- Explicitly marks all generated steps as **unexecuted**; no request
  generation, Run-dialog screenshot or process launch alone counts as a
  successful native read.

Sample read-only plan, generated against an independently confirmed current
guest identity:

    python scripts/prepare_serial_guest_pointer.py --pid 2768 --start-ticks 639282812576974124 --build 7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD --name oct23v2 --guest-exe C:\RIFT_TRANSFER\RiftReader2Control\build-5ae1b56791ad\RiftReader2.Live.exe --out-dir artifacts/update-recovery-20261023-01/serial-pointer-plan-20261023-v2

The ignored local plan has 10 single-action files, maximum command
length 175, and exact request SHA-256
76FE68E1446396AD32E0E6CC5D0219DE6C5E9205C4FAF9BED66E21C225CE505E.
It was generated only after checking the connected host, idle/disarmed
guest, exact current process identity and coordinator-ready state.

## Execution rule

Do **not** merge the numbered steps into a single bootstrap action list.
For each step, acquire exclusive VM console ownership using the existing
control/maintenance workflow, invoke only that one file, inspect the
resulting guest state, confirm that the Windows Run dialog has closed and
the command completed, and then continue. After the decode step, verify
the actual guest SHA-256 matches requestSha256 and the current PID,
creation ticks and build still match. The last step is an actual native
reader invocation; treat it as unverified until its report exists, has a
complete result and matches the exact request and fresh typed Lua position.

If either the VM or game has restarted, discard these guest-session
plans and create new ones with fresh target identity. Keep the coordinated
host in a valid maintenance state during VNC use and restore it with a
new shutdown marker afterward. Do not send movement or game input.

## Validation

Focused suite: python -m unittest tests.test_serial_guest_pointer

Eleven tests passed, including a real Windows cmd.exe / certutil.exe
integration that reconstructed byte-identical JSON. Additional tests
cover unsafe metacharacters, incorrect target identity, invalid lengths,
unsafe paths/output names, deterministic manifests, absence of game
execution, and refusal to overwrite output. One test directly checks
that a second CLI invocation cannot replace the first plan.

**Status:** host-side short-command reconstruction and immutable plan
generation qualified. Live serial guest dispatch and actual RIFT
follow-pointer validation remain **pending**. The coordinated host
was restored after the failed batch attempt as PID 48724 in Windows
session 2, ports 49712/49715, guest connected, coordinator ready,
supervisor running, disarmed and no held inputs.

The substantial pre-existing navigation/control worktree changes
remain separately owned and were not mixed into this work.

## Final validation gate

The focused standalone suite passed 11/11, including actual Windows
cmd.exe and certutil.exe request reconstruction with byte-for-byte SHA-256
verification. It does not execute the last step, so no game process
access is implied by these tests.

The unmodified repository-wide PowerShell 7 gate passed with exit 0
on October 23 (job rr2_serial_guest_full_repo_gate_107): 364 C# tests,
462 Python tests, 108 Lua lifecycle/encoder assertions, 22 real Lua/C#
contract cases, zero-warning .NET 10 Release build, native synthetic
publishing checks, formatting, locked restore and 332 relative links.
The isolated new serial-transport suite is **additional** to the 462 tests;
it was not added to the concurrently edited scripts/validate.ps1.
The ignored gate evidence is
artifacts/validation/20261023T231129Z-141ee7c0.

The recovered V4 host stayed live and connected after this offline pass,
under Windows session 2 (host PID 48724), with the coordinator ready and
guest disarmed. No new native XYZ pointer read was accepted or field
qualified. The historical absolute heap addresses were never reused.

