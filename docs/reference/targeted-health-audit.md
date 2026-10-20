# Targeted native health/resource snapshot audits

RiftReader2 reuses the production NativeMemorySnapshotFile.LoadAsync
loader to inspect retained, exact-source native memory snapshots. It does
**not** attach to or read a game process during analysis. The host-only
snapshot planner is described in
[targeted snapshot planning](targeted-health-snapshot.md).

## Audit one retained targeted snapshot

Run in PowerShell from the repository root, after a separately recorded
RIFT guest snapshot-native capture:

    dotnet src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll audit-targeted-health --request artifacts/field-discovery/targeted-01.request.json --manifest artifacts/field-discovery/targeted-01.manifest.json --receipt artifacts/field-discovery/targeted-01.receipt.json --snapshot artifacts/field-discovery/targeted-01.snapshot.json --output artifacts/field-discovery/targeted-01.audit.json

The command checks the exact producer-declared request SHA-256 against
the original request bytes, the snapshot's PID/creation ticks/build, native
chunk hashes and coverage through the existing loader, and the source
manifest's candidate group count, 80-byte ranges, addresses, int32 marker
layout, historical context SHA-256 and Lua receipt SHA-256. The receipt must
match the manifest's observer, player, generation, advancing sequence,
target process and numeric health/healthMax/raw power references. Inputs
and candidate counts are bounded. Duplicate JSON properties are rejected.
Successive same-epoch snapshots require their own Lua receipts/manifests,
pinned to exact fresh observations.

The output schema is targeted-health-snapshot-audit/1. Each successfully
read group reports the actual signed int32 values, individual matches to
current health, health maximum and raw power, and whether the entire
80-byte window still hashes identically to the earlier captured context.
Missing or partial chunks are **not decoded or zero-filled**; coverage and
failure information remain visible. An independently observed visual
level hint has no typed Lua identity and is deliberately never scored
as a typed match.

A Lua receipt more than **15 seconds** before the native snapshot begins
can still be included for byte auditing, but typedReferenceNearCapture
is false and no current-value matching claim is emitted. A near-in-time
typed reference is still not atomic with sequential native reads.

## Compare two audited observations

Once two independent captures in the **same exact game process epoch**
have been individually audited:

    dotnet src/RiftReader2.Cli/bin/Release/net10.0/RiftReader2.Cli.dll compare-targeted-health --before artifacts/field-discovery/targeted-01.audit.json --after artifacts/field-discovery/targeted-02.audit.json --output artifacts/field-discovery/targeted-change-01.json

The result schema is targeted-health-change-comparison/1. It requires
different retained native snapshot hashes but identical request hash,
PID/creation ticks/build, player/observer/generation, advancing typed
sequence, identical candidate addresses/marker tags and nonoverlapping
ordered capture intervals. Both native captures must be complete and
both Lua references near their respective captures. Contradictory internal
marker values, stale sources or unreadable groups are rejected rather
than converted into positive evidence.

Per-site outcomes distinguish typed changes tracked by the native int32
values, unchanged-or-possibly-cached values, and unexplained native
changes. One marker may track more than one changing typed quantity and
is explicitly marked ambiguous. Unchanged typed values cannot be used to
claim that an unrelated native change tracks health or power.

The comparison consumes **audited reports** and hashes their exact bytes;
it does not reload the original native snapshot bytes a second time.
Keep all original request/manifest/receipt/snapshot/audit files together
with the comparison evidence. The audit and comparison are intentionally
strict but cannot independently prove field meaning, distinguish replicated
copies as authoritative, or establish restart/update survival.

All results retain **candidate-only** qualification. No changed native
health or resource field has yet been qualified in RIFT.

See the [offline audit validation record](../validation/targeted-health-audit-2026-10-19.md)
for focused tests, the original VM availability blocker, and the full gate.
