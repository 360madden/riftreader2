# Native Warrior Power: locator and live evidence

October 25, 2026 (local date; capture timestamps extend into October 26 UTC).

The new `sample-power` command follows the actual player resource objects and
reconstructs the game's Power getter. One controlled Light's Balm cast agrees
with fresh Lua during consumption and regeneration, both before and after
**one complete normal game exit and relaunch**. This is exact-build evidence, not patch
recovery or a claim about other classes/resources. Health-change testing stays
deferred.

## Reusable locator

Applicable executable SHA-256:
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
Recipe identifier: `player-power-7C356C9D-v1`.

Each arrow below reads one unsigned 64-bit pointer; all offsets are hexadecimal.
No absolute heap address is retained as a locator.

```text
module + 32E0200 -> player owner
owner  + 400     -> unit component
component + 38  -> resource wrapper
wrapper + 10    -> resource handle
handle + 0      -> resource record
```

The component, wrapper and record vtables must equal module base plus
`2648E90`, `27184F0`, and `2B378D8`, respectively. The resource-type object
at `[component+40]` must contain integer `1` at `+168`, the branch used for
Warrior Power in this build. A missing cached component is unavailable; the
reader never calls the game's fallback resolver or changes reference counts.

| Input | Location | Type |
|---|---|---|
| Base value | record + 18 | int32 |
| Record sequence | record + 1C | int32 |
| Maximum | record + 20 | int32 |
| Regeneration rate | record + 2C | int32 |
| Cached sequence | wrapper + 18 | int32 |
| Time anchor | wrapper + 1C | float32 |
| Current frame clock | `[module+335A0E0] + 18` | float32 |
| Scale | module + 2649B94 | float32, bits `BC23D70A` |

The two sequences must match. Otherwise the reader reports unavailable and
tries afresh on the next observation; it never performs the getter's cache writes.
With float32 rounding at each arithmetic step:

```text
adjustment = truncate(rate * scale * (clock - anchor))
Power = clamp(baseValue - adjustment, 0, maximum)
```

Observed rate `1200` and scale approximately `-0.01` give regeneration of
12 points/second. The stored base alone is not current Power. Each observation
resolves the chain again, checks object types, reads the inputs twice, compares
the pointers and mutable inputs, and brackets acquisition with existing process
identity/build checks. Null/partial reads, invalid values, sequence changes and
stale processes return null Power. These checks reduce mixed observations;
external reads are not atomic with the game.

Implementation: [reader](../../src/RiftReader2.Application/PowerCandidateReader.cs),
[command](../../src/RiftReader2.Live/PowerSampleCommand.cs),
[focused tests](../../tests/RiftReader2.Tests/PowerCandidateTests.cs).

```powershell
# Supply the current, independently checked game PID and start ticks.
.\RiftReader2.Live.exe sample-power --pid CURRENT_PID --start-ticks CURRENT_TICKS `
  --output NEW_REPORT_PATH --samples 120 --interval-ms 100
```

The schedule is bounded to 600 observations and 60 seconds. Intervals follow
completed reads, not a guaranteed sampling rate. Outputs are immutable and
include identity, recipe, per-read timestamps, resolved pointers, raw wrapper
and record bytes, computed values, and explicit candidate qualification.
Use the existing VMware Tools/cached-login route to deploy and retrieve results.

## Evidence and provenance

The exact guest executable was copied read-only and hash verified. Focused
offline Ghidra inspection located the API assignment to `power` at RVA
`9A4C13` and its getter at `13276C0`; `powerMax` calls getter `13284B0`.
Player-root helper `486BF0` reads `32E0200`; component helper `53CE30`
uses owner `+400`. Resource handle helper `1F7C1D0` resolves the record and
checks runtime type `729`. The external reader uses exact-build vtable checks
instead of invoking these functions. The initial REA whole-program analysis
timed out; focused analysis of the original PE with automatic analysis disabled
completed. No debugger, memory writes, injection, or game calls were used.

The old float64 candidate `0x202DBECE9C8` read zero while Lua reported 100.
Its allocation descriptor links to a heap named `MovieView "PlayerPortrait.gfx"`.
That is evidence of a portrait UI allocation, not a durable authoritative Power
locator. The allocation-role interpretation remains inference; raw linked bytes
and hashes are retained in `portrait-owner-review.json`.

Working evidence: `artifacts/power-locator-20261025-01/`.
The original PE, focused project, disassembly, captures and scripts remain there.
The newly published reader SHA is
`EC0AF9B3FF3BA84F1657C8216176AAEBF6323912AE8464F8AF2B774E529A0A7D`;
it is deployed separately at
`C:\RIFT_TRANSFER\RiftReader2Control\power-reader-EC0AF9B3FF3B.exe`.
The managed input agent and NAT setup were unchanged. Deployment and every
returned capture archive were hash verified using VMware Tools, with cached
guest credentials and no login prompt.

## Live result before restart

Game PID `1224`, start UTC ticks `639285359295548343`.
Player owner `0x202BA8B1480`, component `0x202F2E56870`, wrapper
`0x202F2E57280`, handle `0x202F2E568C0`, record `0x202CC590A80`.
These addresses are evidence for this process only.

- Stationary baseline: 5/5 complete native reads at 100/100; four valid Lua
  frames at 100, three near-time pairs with zero residual.
- One reviewed Light's Balm click in slot 7: target positioned at screen
  `(623,685)`, button down/up verified, no target loss or uncertain input state.
- Native: 120/120 complete observations, 100 -> 83 -> 86 -> 89 -> 92 -> 95
  -> 98 -> 100. No unavailable observations.
- Fifteen validated advancing Lua frames include 100 -> 82 -> 88 -> 94 -> 100.
  Thirteen nearest-clock pairs are within 0.212 seconds; maximum absolute
  residual is 2 points. These are separately timed reads, not an exact spell-cost
  measurement or proof that the minimum Power was captured.
- As a separate offline cross-check, reconstructing at each Lua frame time only
  when surrounding native records/anchors/pointers agree gives 12/12 exact
  matches, including 88 and 94. This derived comparison does not replace the
  original native observations.
- Lua health remained 18208/18208; XYZ remained
  `(7441.4897460938, 863.57995605469, 2964.9299316406)`.
- Final click state: disarmed/idle, no held input, queue released.

`trial-02-capture/review/` retains every validated Lua frame, source hashes,
raw pair residuals and the clock-aligned cross-check. `trial-02-click/` retains
review, screenshots, action and release evidence. Trial 01 stopped at screenshot
review because noninteractive stdin was closed; no click was sent. Trial 02
used interactive review and completed.

## Full game restart and repeat

Joey exited normally and relaunched through Glyph, then confirmed world entry.
The existing controller journal independently recorded **zero `rift_x64`
processes at 01:07:34.599446 UTC**. The new process is PID **12076**, start UTC
ticks **639285736860316715**, with the same executable SHA. A later request
using the old PID/start returned exit 2 (`OpenProcess` error 87) and no report.

| Resolved object | Before exit | After relaunch |
|---|---|---|
| Player owner | `0x202BA8B1480` | `0x21EDD0606A0` |
| Unit component | `0x202F2E56870` | `0x21EA60CF730` |
| Resource wrapper | `0x202F2E57280` | `0x21E9EB74A30` |
| Resource handle | `0x202F2E568C0` | `0x21EA60CF780` |
| Resource record | `0x202CC590A80` | `0x21EEEF48260` |

The unchanged Power recipe resolved these fresh addresses without a Power scan.
Ten initial native reads completed at 100. The Lua heap had moved, so its old
capture scope returned no frames; one bounded 64 MiB typed-prefix search found
the new Lua scope at `0x16BA0000`. This was Lua transport reacquisition, not
native Power rediscovery. A fresh paired baseline gave another 10/10 native
reads at 100 and three advancing Lua frames at 100 (two near-time pairs exact).

A second reviewed Light's Balm click delivered and released at the same slot.
The new process produced **120/120 complete native observations**, including
100 -> 83 -> 86 -> 90 -> 94 -> 97 -> 100. Eighteen valid Lua frames include
100 -> 81 -> 87 -> 93 -> 99 -> 100. Sixteen nearest-clock pairs were within
0.186 seconds, with maximum residual 2. The separate stable-record calculation
at Lua clock times matched all **14/14** eligible frames exactly. Health and
XYZ remained unchanged. This establishes one observed same-build restart and
changed-state agreement; it does not establish arbitrary restarts, patches,
other characters/classes, VM boots or health semantics.

The temporary restart observer stopped when PowerShell treated the expected
missing-process stderr as terminating. Its empty stdout/stderr and no-report
state were recovered, but **they are not claimed as a completed absence audit**.
Independent, timestamped controller journal records provide the zero-process
proof. The subsequent observer began after the new process existed and honestly
records `absent=false`; it is not used to claim another restart. Originals and
hash-verified extracted journal lines are retained under `restart-proof/`.

The post-restart click and sampling completed, but final orchestration checks
failed: the control supervisor was still bound to the old game identity and
blocked cleanup as `target-identity-changed`. Button-up and STOP were independently
verified, with no held inputs. The existing agent reconnect path then rebound
V23 to the new game, performed fresh cleanup, and cleared the queue. An explicit
recovery script stopped at its preflight because recovery had already occurred;
it sent no restart request and edited no queue state.

The shared workflow preflight now compares the supervisor's bound epoch with
the current full guest/game identity **before allowing a run**. A saved replay
of the actual stale-binding status is rejected; a fresh live status passes.
Future game restarts require a verified controller reconnect before another
input test. This preserves the existing watchdog instead of weakening it.

## Verification and handoff

Full gate passed for the reader: **505 .NET tests (333 portable + 172 Live)**, **817 Python
passes and two skips**, Lua contracts, native publish/smoke, formatting and
606 existing relative links. The 18 added focused tests exercise arithmetic,
clamping, replacement-record resolution, partial reads, wrong types/resources,
sequence races, invalid time/value inputs and stale identity rejection.
Evidence: `artifacts/validation/20261026T005810Z-5aef2228/` and
`artifacts/power-locator-20261025-01/validation-02.log`.
The initial gate stopped on line-ending formatting; the corrected gate passed.

The additional preflight fix has three focused tests covering old-process
binding rejection, missing binding, and foreground-independent identity checks.
The final full gate passed: **505 .NET tests, 820 Python passes and two skips**,
Lua/C# contracts, native publish/smoke, formatting and 611 links. Evidence:
`artifacts/validation/20261026T011905Z-af3aa6d7/` and
`artifacts/power-locator-20261025-01/validation-final.log`.

Evidence export: `artifacts/exports/power-locator-and-restart-20261025-01/`.
It contains the original bounded captures, raw API/static findings, scripts,
source/test snapshots, click/release evidence, journal excerpt, comparisons,
limitations and a verified ZIP manifest. The full game binary and Ghidra project
remain in the working artifact directory rather than the export.

Final live state: V23 ready, supervisor bound to the current game identity,
guest disarmed/idle/no held input, resource unblocked and no pending requests.
The follow-up [normal data interface and catalog](power-data-interface.md) is now
implemented and live verified; no further broad Power scan is needed. Patch
recovery and health-change testing remain deferred.
