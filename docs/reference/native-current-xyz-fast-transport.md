# Current native XYZ via persistent control transport

## Status and scope

This is an **offline-tested implementation**, not a deployed or live-accepted
service. No current guest release or connected agent is established by these
tests. A response under three seconds has **not** been demonstrated live for
this route. Do not deploy, start a controller, or operate a VM merely to follow
this note; use the applicable reviewed lab authorization and ownership workflow.

The result is a read-only, current-build **cached XYZ candidate**. The unit key
is obtained from the same anchored owner lookup as XYZ. Neither a recent
acquisition, a successful transport, nor matching sampled keys proves passive
coordinate refresh, player-motion semantics, uninterrupted owner continuity,
zone, or full-game restart recovery. The API itself may refresh the cache; see
[current-native-position-sampling](current-native-position-sampling.md).

## Invocation and admission

The integration entry point is Python
`scripts.fresh_native_xyz.query(config, expected_vm, expected_game,
host_config_path, *, lab="lab2", expected_zone=None)`. It is a callable, not
a standalone CLI. Use it from an existing authorized operation that owns fresh
target preflight and passes the actual objects; do not substitute old receipts
or guess addresses.

- `lab` is `lab1` or `lab2`; configuration must match that VM, its vmrun,
  VNC port and expected guest machine. The expected VM identity contains
  `vmx`, `port`, `logEpoch`, `listenerPid`, `pid`, `image`, and
  `startTicks`; the operation verifies that VM identity before and after.
- `expected_game` identifies the target process with `processId`,
  `processStartUtcTicks` and `executableSha256` (optionally the same lab).
  The exact accepted game SHA-256 is
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
  A different build, missing pin, changed process epoch, mismatched path, or
  ambiguous game process fails closed. Reacquire current identity after restart.
- The host verifies an authenticated matching guest, VM guard, matching host and
  guest agent instance ID, and guest status capability `nativeXyzVersion: 1`.
  The guest opens a new read-only session, resolves the current owner, rereads
  anchors, and revalidates the OS process/build before returning. Its configured
  executable path and machine must match. Never copy credentials or weaken these
  checks.
- The host endpoint `/api/native-xyz` uses the existing authenticated control
  transport and requires the identity request. It is read-only and does not
  accept an input-control lease. The guest rejects reads while armed, an action
  is active, or recovery is pending; the shared native-read lane excludes other
  native reads and actions. A five-second linked guest cancellation limit applies.
  STOP cancels the read; a slow physical read keeps its lane until it actually
  finishes. Cancellation does not authorize a second owner or overlapping read.

`expected_zone` must be omitted or `None`. A supplied zone blocks with
`native-xyz-zone-unavailable`: the source report has no zone, and this path
does not infer one.

## Timing and output

The host measures the endpoint request/response with its own monotonic clock.
A response taking **three seconds or longer** is rejected; this is an
acceptance gate, not a promise to return within three seconds. The existing
HTTP client has a **10-second request timeout**; that timeout is not an
acceptance threshold. Guest UTC acquisition start/end and response time must
fall within the host UTC request window extended by five seconds on either
side, and the guest response cannot precede its acquisition end. This tolerance
does not synchronize host and guest clocks or establish source freshness.

A successful result is labeled `candidate-only`. It reports VM and game
identity, agent instance, original observation time, candidate XYZ, lossless
decimal unit key and matching hexadecimal unit-ID candidate, response duration,
and `zoneStatus: unavailable-in-source-report`. The host validates the exact
report fields, finite values and owner identity. It writes a new
`samples.json` and `summary.json` under
`artifacts/native-current-xyz-agent/runs/<lab>/<unique-id>/`; the summary
includes the hash of the canonical report bytes. This is a host-serialized
report receipt, not proof of an authenticated game producer or live semantics.
A rejected, timed-out, mismatched or canceled operation is unavailable; never
reuse a prior result as a current reading.

## Offline verification

The focused guest capture, vitals, read-lane and synthetic loopback dispatch
tests passed **32/32**; host XYZ/vitals and route tests passed **48/48**.
These checks cover synthetic contracts and guards, not guest deployment, real
VM latency, movement, passive freshness, or restart behavior. A later live
operation requires its own target-specific authorization, fresh identity,
release/cleanup evidence, and independently reviewed results.

## Sustained tracking limitation

The current endpoint is a bounded one-shot operation, **not a sustained stream**.
The guest control connection rejects its 4,097th authenticated command when its
request-ID set exceeds 4,096, then reconnects. If each query uses both status and
XYZ commands, this is approximately 17 minutes at two queries per second or
34 minutes at one query per second, excluding other commands. Actual duration
varies with command traffic and operation time. Guest, host and client also
create per-query evidence files, causing accumulating artifact churn. These are
P2 blockers for an unattended continuous tracking loop; do not claim sustained
2 Hz production from the present offline tests. A future long-running design
must address lifecycle, evidence retention, identity and safe cancellation before
making a sustained-use claim.
