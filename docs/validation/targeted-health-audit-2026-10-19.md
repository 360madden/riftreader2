# Targeted native health audit and change comparison — October 19, 2026

## Scope and environment

This increment adds **offline** target-window auditing to the existing
modular .NET 10 CLI, rather than introducing another memory reader.
Sources are existing bounded native-memory-snapshot/1 reports, the
validated snapshot request, its provenance manifest and pinned typed Lua
receipt. It reuses the production native snapshot loader for hash,
coverage, identity and partial/unavailable-byte validation. No executable
memory acquisition or game input occurred in this increment.

At approximately 23:49 UTC, the saved field-discovery receiver record
was about **22,970 seconds old**, although it still described RIFT
PID 8356. That record cannot authorize another acquisition or reuse the
five old absolute session addresses. VMware vmrun list confirmed that
the original C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx was **not running**;
the sole running VM was
C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx. The bound original-VM VNC
identity correctly rejected a read-only screenshot with
target-vm-not-running. RiftReader2 did not start, stop, modify, or control
either VM. RIFT-Lab-2 belongs to a different runtime instance and was
not substituted for the intended game's original process epoch.

## Implemented

Two commands are integrated into RiftReader2.Cli:

- audit-targeted-health: validates the exact request bytes, target PID /
  process-start ticks / executable build, hash-pinned Lua receipt,
  provenance manifest, and each 80-byte candidate window using the
  existing NativeMemorySnapshotFile strict loader. Incomplete reads
  preserve missing coverage instead of inventing zeroes. A Lua receipt
  more than 15 seconds before the capture cannot support value matching.
  The purely visual level hint never counts as typed Lua evidence.
- compare-targeted-health: compares two previously audited native
  captures in the exact **same process epoch** with different source
  snapshot hashes, identical request/ranges and player/observer/generation,
  advancing typed Lua sequences and correctly ordered nonoverlapping
  intervals. It distinguishes coherent changes from unchanged possible
  caches and unexplained changes. Contradictions are rejected; the
  tool does not follow or qualify a pointer.

Both commands preserve exact input hashes and an explicit candidate-only
status. They do not assign health/resource meaning, claim navigation
automation, or suggest a candidate survives a restart or executable
update. The pairwise command consumes the submitted audited reports;
it does **not** independently reload each original snapshot again.

The practical command syntax and limitations are in the
[targeted audit guide](../reference/targeted-health-audit.md).

## Validation and remaining work

Focused regression coverage uses real synthetic NativeMemorySnapshotFile
objects and the existing CliRunner, with zero live RIFT dependency.
It covers correct changed-health/power matching, health maximum versus
current ambiguity, candidate-only semantics, stale receipt timing,
identity/build/hash disagreements, duplicated snapshots, corrupted
native chunks, unavailable windows, malformed markers, duplicate JSON
keys, internal comparison contradictions, ordered capture times,
and no-overwrite publishing. The pairwise tests also ensure unchanged
Lua quantities cannot explain unrelated native changes.

Focused .NET 10 Release validation passed **31/31 targeted audit and
comparison tests**, no skipped or failed cases (Workbridge job
rr2_targeted_audit_pair_final_focused_20261019_2007_26). The first full
gate correctly rejected unformatted new C# source; whitespace formatting
was applied only to the owned CLI and test files. The full repository
PowerShell 7 gate subsequently passed, exit code 0, on October 20 UTC
(job rr2_targeted_audit_formatted_full_gate_20261019_2010_32):
**273 C# tests** (256 core, 17 Windows), **114 Python tests**,
108 Lua assertions, 22 actual Lua-to-C# contract cases, a zero-warning
.NET 10 Release build, locked restore, formatting, native synthetic
publish smoke, deterministic replay, and 228 relative documentation
links. Ignored validation evidence:
artifacts/validation/20261020T000746Z-41a85216.

An additional negative check used the real saved RIFT memory header
snapshot from PID 11620 with the later targeted request and Lua
receipt for PID 8356. The new audit command rejected it with
exit code 2: "Snapshot PID/start/build differs from the request."
Workbridge job:
rr2_targeted_audit_real_saved_wrong_epoch_rejection_20261019_2011_33.
This confirms real saved evidence is rejected across those recorded
process epochs; it is not a current live memory capture.

**Offline targeted-audit integration milestone: COMPLETE.** No new
native health/resource meaning was qualified. Live acquisition remains
blocked by the intended VM/game session's absence.

**Next live acquisition:** re-establish which RIFT VM and process are
authorized as the target, reacquire a fresh game/typed API identity, and
rebuild the targeted request in that exact process epoch. Only then
capture the same small candidate windows before/after a genuinely changed
health or resource value, audit each capture and run the comparison.
The historical five addresses from PID 8356 must not be assumed valid
after a game or VM restart.

The concurrent movement-control roadmap and its uncommitted
docs/README.md, docs/status.md and planning document are outside this
change and must not be staged with this commit.
