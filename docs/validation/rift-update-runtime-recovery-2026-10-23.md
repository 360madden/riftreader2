# RIFT update recovery — October 23, 2026

## Scope

Recover existing RiftReader2 runtime and previously validated build evidence
before any new memory-field or navigation discovery. This pass did not modify
RIFT executable, game addon, V1, VM settings, or game memory. The existing
uncommitted navigation/control files remain separately owned and unstaged.

## Confirmed live facts

- VM: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, VMware PID 31884,
  VM start ticks 134371752823274925, unchanged across the recovery.
- Game: `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, PID 2768,
  creation ticks 639282812576974124. The guest control agent is the same
  previously installed singleton; a duplicate launch was rejected.
- Game executable SHA-256:
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
  This matches the retained October 19 executable baseline. It establishes
  **on-disk binary identity**, not unchanged server behavior, loaded module
  state or heap addresses.
- Native inspection via the existing installed RiftReader2.Live binary
  succeeded on the new process and recorded current PID/start/build and
  module base `0x7FF627AF0000` with module size 62,611,456 bytes.
- The historical candidate position root RVA `0x32E0200` was **not**
  revalidated. Attempts to submit a complete pointer-follow request
  through the guest Windows Run interface failed PowerShell parsing; there
  is no successful new pointer-follow report or XYZ comparison. Do not
  interpret the failed command-entry attempts as evidence that the native
  memory chain is broken.
- Guest input cleanup: diagnostic Windows Run dialog was dismissed and
  experimental command windows were closed in the maintenance interval.

## Runtime and durable queue recovery

The original host stopped for a bounded, read-only native inspection.
The V2 maintenance shutdown marker remains preserved and was not reused.
Before restoration, all original runtime file hashes, private host config,
VM epoch and free host ports were rechecked. Reusable V3 artifacts already
existed in the ignored recovery directory and were validated rather than
overwritten. The V3 process was launched independently in Windows session 2
through the one-use, hash-pinned wrapper.

V3 host PID **52208** was alive with the following listeners:
`192.168.56.1:49712` and `127.0.0.1:49715`.
The guest receiver reconnected; the coordinator reported **ready**, the
supervisor **running**, recoveryRequired false, armed false and no held inputs.

The canonical durable queue at
`artifacts/native-coordination-live/queue.sqlite3` retained its request
history, was neither deleted nor replaced, and completed recovery at
generation **503**, resource `vm:rift-lab-1`, unblocked/unheld, with
zero pending requests and one historical request. The last cleanup receipt
hash in the baseline was
`ef797401a444a9a5ce92bed1fac9d3f3ebabc075c885e2ab859dc86086922223`.

Read-only post-maintenance validation completed with exit code 0:
`artifacts/update-recovery-20261023-01/v3-readiness-baseline.json`,
SHA-256
`21EC7D81220CA14BD3492FA696D64474093ED00C3597376A93A7864BAAB0F402`.
It reports nativeReady true and no gameplay input. The game was **not in
foreground** when this baseline was taken; therefore it establishes recovered
transport, queue and identity but **not** immediate gameplay command
readiness. The normal startup shortcut and Windows boot recovery remain
separately unverified.

## Repo validation and next milestone

The current repository-wide gate completed earlier in this recovery with
364 C# tests, 462 Python tests, 108 Lua assertions, 22 Lua/C# shared cases
and a zero-warning Release build. No tracked source was edited for this
recovery note. The tracked branch at the checkpoint was
`codex/modular-foundation` at `5263615cae38f58fedb9b15ba358aee68ec5f8ad`,
with significant pre-existing navigation/control edits not staged here.

Next: avoid Windows Run long-text submission. Use a short, locally verified
and hash-pinned request transport to invoke the existing guest
`follow-pointer` tool with exact current process identity. Record the raw
report and compare native XYZ against a fresh typed Lua coordinate source,
with same-build candidate-only scope. Then check foreground game input
eligibility under exclusive coordinated VM control, and separately validate
whether the guest startup installation survives restart. Do not reuse prior
absolute heap addresses or start new discovery before these checks pass.
