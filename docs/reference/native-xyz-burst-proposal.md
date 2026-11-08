# Native XYZ bounded-burst proposal

Status: **PROPOSAL ONLY; NOT IMPLEMENTED OR DEPLOYED.**
Source review: 2026-11-08 UTC (2026-11-07 EST), AMD-DESKTOP,
`C:\work\riftreader2`. This note authorizes no live operation or code change.
The existing native-xyz route is a one-shot candidate acquisition, not a
qualified continuous tracker.

## Observed constraints

- `src/RiftReader2.Live/Control/ControlAgent.cs:186-197` keeps every accepted
  command ID in a per-connection HashSet and rejects command 4097. Sequence
  and the set reset on reconnect; agent instance ID does not
  (`146-167, 206-224`). This is a deterministic lifetime limit, not a leak.
- `scripts/fresh_native_xyz.py:125-138` issues status plus native-xyz per query:
  about 2048 samples per connection before other traffic. Batching alone only
  postpones the limit; reconnecting is not a transparent reliability fix.
- `Control/ControlNativeXyz.cs:61-70` opens/revalidates per sample.
  `WindowsNativeMemorySession.cs:57, 173-191` hashes executable bytes at open
  and final revalidation. These are on-disk hashes, not loaded-module attestation.
- Guest replies retain an atomic durable command receipt
  (`ControlAgent.cs:624-630, 684-696`). Host request/response records each
  flush/fsync (`scripts/control_host.py:409-420, 739-751`).
  The wrapper also creates a samples/summary pair per query
  (`scripts/fresh_native_xyz.py:153-174`).
- Host sequence is per AgentSession (`control_host.py:491, 731-735`);
  reconnect creates another AgentSession (`903-910`). Unknown/duplicate
  response IDs fail the transport (`759-779`), and timeouts have no retry
  (`741-744`). Preserve those properties.
- Two retained fast-vitals receipts show surrounding overhead, not a sustained
  XYZ rate or a measured breakdown:
  `artifacts/native-current-vitals/runs/lab2/0073567b1e6d43b687b369e27265b0d4/summary.json:65-68`
  records 0.174 ms native read and 0.2374648 s wall time;
  `artifacts/native-current-vitals/runs/lab2/049d647ee5b54aa184f240ad670b6e74/summary.json:65-68`
  records 0.113 ms native read and 0.2578257 s wall time.

## Proposed minimum protocol

Add one negotiated `native-xyz-burst` capability/contract. Keep existing
one-shot requests unchanged. No new daemon, scheduler, or unsolicited frames.

- Default: **16 observations, 50 ms minimum spacing**. Hard bounds:
  **32 observations and 2 s acquisition window**, whichever is reached first.
  Count/spacing/window must be validated together; do not accept an impossible
  requested schedule as a complete burst.
- Retain the existing 5 s guest work deadline and 8 s host request deadline.
  Opening and final hashing count against the work deadline, outside the
  acquisition window. Do not silently reuse the one-shot wrapper's separate
  3 s post-response acceptance cutoff.
- Admit machine, exact PID/start ticks, executable SHA/path, module mapping,
  expected agent instance, new connection epoch, and STOP generation.
  Keep existing disarmed/idle/no-recovery and native-read/action interlocks.
- Open one read-only process handle and hash once; call existing `ReadOwned`
  independently for every row, without caching resolved owners between rows.
  Require a nonzero, unchanged unit key and finite XYZ. The same handle must
  serve the entire burst; never reopen or silently rebind a replacement process.
- After all rows, perform existing full `RevalidateAsync`, including the
  second executable hash. Thus a successful burst has **two executable hashes**,
  not two per observation. Recheck cancellation/generation before publication.
  Boundary checks do not prove unchanged file/module bytes at every instant.
- Buffer bounded rows in memory; one final response, at most 64 KiB.
  Each row carries index, decimal-string unit key, unit ID, XYZ, UTC start/end,
  and relative monotonic start/end in one named burst clock domain.
  Include actual count, acquisition span, terminal reason and identity guards.
- Space reads without catch-up storms. Report actual timing; never claim a
  fixed cadence, interpolate missing points, or infer source freshness.
  Reject nonfinite/backwards clocks. UTC is metadata, not a substitute for
  monotonic scheduling or proof of host/guest synchronization.
- First version is all-or-nothing: successful count plus final revalidation
  yields candidate rows. Cancellation, budget exhaustion, changed owner or
  invalid identity yields terminal metadata/counts, **no usable rows**.
  Do not require provisional-stream/retraction machinery.
- Retain one guest command receipt, host request/response journal pair, and
  host batch artifact/digest/summary per burst. No per-row file or fsync.
  Crash loss is bounded to the uncommitted burst; do not claim otherwise.

Tradeoff: roughly one-second display chunks at the default setting, not
instant delivery of each row. More frequent smaller bursts reduce latency but
increase hashing/journal overhead. Tune only after measured runtime receipts.

## Command lifetime and reconnect

Replace the lifetime ID collection with a bounded **active-command ID set**,
not a periodically cleared replay window:

- Keep strict increasing sequence, GUID validation and the existing durable
  completed-receipt collision check.
- Keep an accepted ID active until its terminal receipt is durably written.
  Only then remove it; receipt failure aborts the transport. Synchronize set
  updates because completion and dispatch can run concurrently.
- Bound active work, not total completed commands. Reserve admission for STOP
  under saturation; preserve single native read and existing control fences.
  Never delete receipts merely to admit more commands.
- Negotiate a fresh connection-epoch GUID on every handshake; bind burst
  request/result to it and the agent instance. The instance survives reconnect
  and is insufficient alone.
- Disconnect invalidates the in-flight burst. No automatic retry, resumption,
  old-result attachment, or cross-epoch stitching. A new connection requires
  fresh process/instance/VM admission and starts a distinct tracking segment.

## STOP must mean drain, not only cancellation requested

Current STOP cancels native reads (`ControlAgent.cs:538-545`), but its handler
awaits active actions rather than native-read completion (`337-344`).
Host generation invalidation currently fences control operations, not native
reads (`control_host.py:514-520, 726-730`).

Extend that generation fence to queued bursts. Guest STOP cancels the burst,
blocks new acquisition and waits for acquisition/session disposal before a
drained-success acknowledgement. Separate acquisition draining from network
reply delivery to avoid circular waits. Serialize success commitment against
STOP: a result already committed before the fence is distinguishable from a
cancelled burst; the host must not update its active track with a late old-
generation response. If synchronous work cannot drain within the bound,
report `stop-pending`, retain the block, and never claim stopped or idle.
STOP/release and recovery protections for input remain intact.

## Focused acceptance criteria

- More than 10,000 mixed commands without count-triggered disconnect, while
  duplicate active/completed IDs and regressed sequences still reject.
- O(1) retained writes and exactly two executable hashes per successful burst;
  bounded rows, bytes, duration and active IDs.
- STOP before dispatch, during delay/read/hash, and at publication boundary
  prevents post-fence accepted rows; pending drain cannot admit another burst.
- Same-instance reconnect changes connection epoch; old/duplicate responses
  cannot populate a new track. No uncertain-delivery retry.
- PID reuse, owner change, bad XYZ, module/hash change, clock regression,
  excessive payload and final revalidation failure reject usable output.
- Fake clocks/sessions/transports cover deadline, receipt-write failure,
  cancellation, saturation, reconnect and shared-lane races.
- Runtime qualification remains separate: measured latency/jitter and STOP
  drain time, API-quiet/passive refresh, player semantics, restart recovery,
  and loaded-module limitations. No current evidence establishes those for
  this proposed burst route.

## Reviewed source fingerprints

SHA-256 snapshots used for the observations above (later edits require review):

- `ControlAgent.cs`: `81de5abd57414cf4feda7ad10dbca22d51e85e667b53de5e77d992b69def96e3`
- `ControlNativeXyz.cs`: `7d5cec192db47abef970baec592eb63f83c5e385d81ab6a33cc5d58f560144c1`
- `WindowsNativeMemorySession.cs`: `b17593eff780f31a2a0befcb7ec25bfc22248cdca4fa1d29caea073b48e1af2b`
- `scripts/control_host.py`: `691ddd144eb0f66b423a6b5f6fbe596cdd903d4e025633df53830f5acedab30c`
- `scripts/fresh_native_xyz.py`: `2f0d0fa6bc07a6b67312759944bccc0b491bbf77039319f79884f05b81842610`
