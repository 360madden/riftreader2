# Lab 2 ChatGPT/tool handoff optimization — November 7, 2026

The largest avoidable delay was the extra model-facing handoff between the
completed Lab 2 command and the image-loading tool. It is now removed from the
preferred inspection path. In three before and three after trials, actual
session-log dispatch-through-image-return time fell **9.848 to 4.642 seconds
median**, saving **5.206 seconds / 52.86%**. This measures the handoff improvement,
not faster reasoning or faster work inside the VM.

## Measurement

| Same inspection and image delivery | Before median | After median |
| --- | ---: | ---: |
| Session outer dispatch through final image return | 9.848 s | 4.642 s |
| JS command-start through image-loaded stamps | 9.783 s | 4.598 s |
| JS command-return to image-dispatch gap | 4.976 s | Below 1 ms timestamp resolution within one call |
| Underlying guarded workflow | 3.554 s | 3.689 s |
| Model-facing tool calls | 2 | 1 |

Before outer spans were **10.012, 9.107, 9.848 s**; after spans were
**4.642, 4.533, 4.723 s**. All samples remain included. The baseline's three
logged return-to-next-image-dispatch gaps were **4.961, 4.616 and 5.321 s**.
An additional historical trace audit found comparable gaps of 5.631, 7.429 and
18.435 s. Those older observations establish recurrence, not another controlled
comparison. Outer wrapper residual over nested command wall time was about
0.19–0.20 s in the clean examples, much smaller than the extra handoff.

The JS measurements use UTC `Date.now()` stamps; session logs independently
corroborate their boundaries with consistent millisecond offsets. These are
wall-clock observations, not monotonic timestamps or model-internal timing.
After has no separate outer image dispatch; its zero-millisecond internal gap
only means both stamps fall in the same millisecond. Image loading still takes
time. Completion excludes subsequent visual interpretation and final prose.
Three sequential trials per route are not a general latency percentile.

Evidence: [comparison](../../artifacts/tool-handoff-optimization-20261107/comparison.json),
[before audit](../../artifacts/tool-handoff-optimization-20261107/before-independent-audit.json),
[after audit](../../artifacts/tool-handoff-optimization-20261107/after-independent-audit.json),
[session timing audit](../../artifacts/tool-handoff-optimization-20261107/before-session-timing-audit.json),
and [redacted trace](../../artifacts/tool-handoff-optimization-20261107/redacted-session-trace.json).
Only timing metadata and IDs are retained from the session log; no raw prompts,
arguments, credentials or tool output were copied into that trace.

## Implemented route

`scripts/inspect_lab2_tool.py --output <fresh absolute directory>` runs the
existing fixed Lab 2 native/UI workflow and checks its delivery artifacts. A
single `functions.exec` awaits the command, polls any returned session internally,
requires successful verified delivery, then awaits `tools.view_image` and returns
the pixels. The model no longer needs another turn solely to issue the predictable
image call. The [recipe](../workflows/lab2-tool-handoff.md) is the preferred route
in `AGENTS.md`; the underlying standalone workflow remains available.

The driver rejects failed operations, unexpected paths, reparse ancestry,
oversized artifacts, changed image/metadata hashes, inconsistent capture/state
bindings and missing release proof. It emits no usable image on failure. It
retains the status `verified-awaiting-visual-review` and candidate-only native
qualification. Both Scheduler proofs, both late full inventories, fresh executable
hashes, queue ownership and STOP/watchdog cleanup remain in the original workflow.
No runtime-pinned source was changed. No new service or OpenAI API call is needed.

Review also caught a JavaScript precision issue in the parsed delivery projection:
the native unit key exceeds the exact integer range of `Number`. The final compact
delivery returns that key as a decimal string. Authoritative source reports remain
unchanged. This presentation-only correction followed the timing trials and is
covered by the focused tests and retained-result replay; it does not change the
one-call execution path. A subsequent live one-call postflight also verified the
final string projection and returned the expected image. That postflight is
excluded from the three-run timing comparison. Identity audits use original
Python-parsed artifacts.

OpenAI's [latency guide](https://developers.openai.com/api/docs/guides/latency-optimization)
recommends fewer sequential requests and deterministic code where possible.
This implementation follows that guidance; the measured benefit above comes
from the local experiment, not the documentation.

## Verification and limits

The root alone performed live operations, all on **Lab 2**. Workers investigated
the timeline, implemented the driver and independently reviewed/audited it without
live authority. All six trials shared identical VM/game/controller/guest,
connection, receipt, configuration, runtime-source and supervisor pins. Native,
image, metadata, state and plan bindings passed; every request/capture was unique.
Cleanup generations advanced 2437 through 2447, each with verified STOP and final
ready/disarmed/idle state and no sampled held inputs. The root reviewed all six
returned images after release and observed the expected RIFT world/UI.

Nine focused tests passed, including path, image/metadata hash, capture/epoch,
reparse, cleanup and failed-workflow refusals. Full validation exited 0: **719
.NET tests passed; 1,838 Python tests ran, 1,836 passed and two skipped**, plus
Lua contracts, native smoke, helper ownership, formatting and 1,081 relative
links. Evidence: `artifacts/validation/20261107T111253Z-85f9ed6f` and the
[full gate log](../../artifacts/tool-handoff-optimization-20261107/full-validation.log).
The final [postflight](../../artifacts/tool-handoff-optimization-20261107/postflight.json)
retained the baseline pins and all runtime hashes, returned the verified image
in the same call, and left Lab 2 ready/disarmed/idle. Queue generation 2449 was
unblocked/unheld with no active Lab 2 request or sampled held inputs.
No gameplay input, focus change, deployment, VM/game restart or Lab 1 guest
operation occurred. The fix removes this unnecessary handoff; it does not remove
pauses where the next action needs fresh interpretation or a model decision.
