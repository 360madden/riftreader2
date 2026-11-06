# Two-lab guidance hour — October 29, 2026

**Window:** 2026-10-29 18:58:37Z–19:58:37Z. The repository started at
`57c7356`; commit `c460ac7` was created during the hour at approximately 19:19Z.
This record separates retained proof from unproved behavior; command
delivery or a fresh reader feed is not, by itself, a movement result.

## Current checkpoint

The initial native Codex chats supplied the two guest-side inspection lanes. At
19:04Z the user launched RIFT in both guests and renewed the idle-lab
reservation. The root coordinator then shut down both native control hosts
cleanly before taking standalone VM-console ownership. Lab-1's helper startup
through its native chat restored the control path, with the six pinned runtime
hashes reported as matching. These coordination facts are retained as the
operating baseline; the hour's durable game evidence is recorded below.

Commit `c460ac7` added and tested the binding-recovery explanation, but the
bounded live readers in this hour remained the previously deployed
`A9C36D21...7B04E` executable; this run did not deploy a rebuilt reader binary.

| Item | State | Retained evidence or limit |
| --- | --- | --- |
| Separate VM identities | **Proved** | Lab-1 VMX PID 49392 / VNC 5905 and Lab-2 PID 52072 / VNC 5962 were stable across read-only captures in `artifacts/two-lab-hour-20261029/lab1-console-02/identity.json` and `lab2-console-02/identity.json`. |
| Lab-2 exact game identity | **Proved** | PID 4200, start ticks 639288974754421524, executable SHA `1935A05C...0A4BE8`; see `lab2-reader-02/preflight.json` and `summary.json`. |
| Lab-2 reader and bind | **Proved** | Reader postflight passed and `/rr2guide bind lab2 ...` delivered/released. The frozen initial-result source subsequently proves the matching reader/addon stream was `bound` and fresh; see `lab2-reader-02/summary.json`, `lab2-bind-01/execution.json`, and `lab2-result-01/deferred-source-receipt.json`. |
| Lab-1 reader, bind and feed | **Proved** | After a terminal Lab-2 reader receipt and no competing reader, Lab-1 reader postflight passed and `/rr2guide bind lab1 ...` delivered/released. A later frozen result source proves the bound/fresh feed independently of the mutable receiver latest file; see `lab2-to-lab1-handover-01/`, `lab1-reader-01/`, `lab1-bind-01/`, and `lab1-result-01/deferred-source-receipt.json`. |
| Lab-2 calculated result | **Proved** | `lab2-result-01/execution.json` retains exact identity, hashes, input/release success and the generated `+3 X / +4 Z / distance 5` command. Its after-screen visibly shows `RR2 GUIDANCE lab2 RESULT 1`, distance 5.00, dX +3.00 and dZ +4.00. |
| Lab-2 bounded movement | **Proved** | One root-reviewed 150 ms `S` pulse delivered and released successfully. Frozen fresh API observations changed X by -0.279785 and Z by -0.560059, planar displacement 0.626055, with the same game, reader nonce, player and epoch. See `lab2-movement-capture-01/`. |
| Lab-1 calculated results | **Proved** | `lab1-result-01/` retained exact identity, advancing post-input receipt, release and visible `RESULT 1`. After movement, `lab1-result-02/` independently recalculated from `(7423.4297, 863.5800, 2948.0000)` and completed as result 2 with distance 5.992354, dX +3.729980 and dZ +4.689941. |
| Lab-1 bounded movement | **Proved** | One root-reviewed 150 ms `W` pulse delivered and released successfully. Fresh API observations changed X by -0.729980 and Z by -0.689941, planar displacement 1.004435, with the same game, nonce, player and epoch; see `lab1-movement-capture-01/` and cleanup. |
| Movement invalidation (`Player moved`) | **Unproved on both labs** | Lab-2's original result had expired before its pulse. Lab-1's before screenshot still showed result age about 7.1 seconds, but its action occurred about 22.7 seconds after command entry; the later source was therefore expired. Neither trial establishes the displacement-invalidation branch. |
| Receiver-listener classification correction | **Passed** | Commit `53f1b63` recognizes receiver listener-table ownership; its full validation gate passed. |
| Fast post-receipt result path | **Passed on both labs; not a benchmark** | Commit `d7da20b` completed the full gate (`artifacts/validation/20261029T193419Z-9962783e`; 1,006 Python and 540 .NET tests among the recorded checks). Lab-2 result 2 completed in 2.347 seconds with outer receipt 761→763 and post-input capture +1.237 seconds; Lab-1 results 1 and 2 also completed with advancing post-input receipts. The earlier path took 14.627 seconds; these few runs do not establish general latency or reliability. |
| Fast-path negative result | **Blocked safely** | `lab2-result-03b` typed and released input but failed the post-check as `live-receipt-not-fresh`; `after` is absent. A possibly visible result is not accepted evidence when the required fresh receipt gate fails. |
| Bounded stale-receipt retry | **Passed** | Commit `2bc073f` waits for an advancing post-input receipt within existing bounds. Full gate `artifacts/validation/20261029T194027Z-ab9a7a36` passed 540 .NET, 1,008 Python (1,006 pass / 2 skip), 110 Lua, 22 shared cases and two round-trip cases. |
| Cross-lab arithmetic review | **Completed** | Each native Codex chat cross-checked the other lab's coordinate calculation through main-coordinator relay. This is complementary review, not direct lab-to-lab messaging or additional game evidence. |
| Final control hosts | **Proved ready and idle** | `final-host-verification.json` passed all checks at 19:50:43Z for Lab-1 PID 13240 and Lab-2 PID 51968. `final-idle-status.json` reconfirmed both connected/ready, disarmed, idle, no inputs down, and both resources unblocked with no holder at 19:56:51Z. |
| Temporary-reader cleanup | **Proved complete** | Lab-1 reader PID 9324 terminated with terminal sequence 519; the earlier Lab-2 reader PID 3468 was already absent. `receiver-final-cleanup.json` verifies the exact owned receiver PID 40940 and wrapper PID 57228 absent at 19:57:17Z. |

The Lab-2 reader is correctly exact-build scoped: native Power remains
`unsupported-native-power-build`, while the addon-derived coordinate observation
is fresh. The frozen source for initial result 1 identifies player
`u035400012DFEB5BC`, epoch 1, at
`(7186.1099, 822.4400, 3159.0300)`. `gameReady=false` in the host receiver is an
explicit delivery-only warning, not contrary evidence to the separately reviewed
in-game screenshots.

The later serial handover retained Lab-2 reader termination before launching
Lab-1's reader against the same executable SHA but distinct PID/start, VM,
nonce and player. Lab-1 result 1's frozen source sequence 3631 identifies player
`u035400012FA2D207`, epoch 1, at
`(7424.1597, 863.5800, 2948.6899)`. This proves isolated two-lab feed reuse,
not simultaneous reader operation or cross-lab field equivalence.

The accepted Lab-2 calculation used fresh source sequence 1987 at the same XYZ
and destination `(7189.1099, 822.4400, 3163.0300)`. The retained report labels
its bearing as coordinate-axis bearing rather than player facing.

The later movement trial used fresh before/after API evidence around one reviewed
backward pulse, not a historical native offset. Source sequence advanced
3059→3107 and coordinates changed from
`(7186.1099, 822.4400, 3159.0300)` to
`(7185.8301, 822.4400, 3158.4700)`. The action receipt records successful key
down/up, delivery and release, with no cancellation, target loss, uncertain
state or recovery requirement. Cleanup then verified the guest disarmed and
idle, no desktop inputs down, queue unheld, and the control host exited normally;
see `lab2-movement-cleanup-01/`.

Lab-1 then reproduced the useful round trip on a distinct VM, process, reader
nonce and player: fresh result delivery completed, and a separate reviewed
forward pulse produced 1.004435 units of API-coordinate displacement with clean
release and host cleanup. The movement happened too late for the result's
ten-second TTL, so the visible pre-action result plus later displacement must
not be rewritten as a successful `Player moved` invalidation.

After the fast-path change, `lab2-result-02/` independently completed with exact
game/VM identity preserved, input released, and fresh post-input receiver
evidence. Its after-screen visibly shows `RR2 GUIDANCE lab2 RESULT 2`, distance
5.62, dX +3.28 and dZ +4.56. Together with Lab-1 results 1 and 2, this is one of
three verified fast-path runs, not proof that all later deliveries will meet the
same timing. The retained `result-03b`
failure demonstrates that the freshness gate still blocks an insufficiently
fresh post-receipt rather than converting command insertion into success.

The hour closed with both durable control hosts healthy and idle and all bounded
reader/receiver helpers removed. The only substantive live acceptance gap from
this run is a movement pulse completed while its guidance result is still inside
the ten-second addon TTL, so that the actual `Player moved` branch can be
distinguished from ordinary expiry.

## Remaining acceptance boundary

For each claimed live result, retain the exact game/reader identity, fresh
source, reviewed command receipt, release certainty, and an after-screen showing
addon acceptance. A movement check additionally requires one bounded reviewed
action with release evidence and an addon transition specifically attributable
to displacement over 0.5 on an axis. Expiry, stale source, or transport success
alone is inconclusive. No native historical offset is needed for this addon/API
boundary test.
