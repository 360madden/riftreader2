# Movement handoff - 2026-10-29

## Resume here

Work in `C:\work\riftreader2`, branch `codex/modular-foundation`. The OneDrive
Riftreader2 folder is not the authoritative Git checkout. This handoff records
the completed two-hour trial and the next experiment; it does not start another
trial. Use the [saved resume prompt](movement-resume-prompt-2026-10-29.md) when
ready to continue. Read [AGENTS.md](../../AGENTS.md), [status](../status.md), and
this handoff first, then open only the source/evidence needed for the next step.

**Engineering result is partial.** Lab-1 achieved one nearby waypoint with
independent feedback after each action. Its repeat failed. Lab-2 achieved an
S-only calibration but no waypoint arrival. Reliable movement on both labs is
not established. The immediate priority is live qualification of the buffer
optimization already implemented in `2d38866`, not a new controller or scheduler.

Repository baseline before this documentation update was `aa7d303`, clean.
The trial ended at approximately 22:04Z; cleanup was verified at 22:02:53Z.
Runtime facts below are **last-observed history**, not current process authority.
This handoff preparation did not query or change the running guests.

## What is proved

| Item | Evidence and limit |
| --- | --- |
| Lab-1 calibration | [Run 06](../../artifacts/two-lab-movement-20261029/lab1-calibration-run-06/result.json): W/Q independently measured under reader03. |
| Lab-1 waypoint | [Goal run 05](../../artifacts/two-lab-movement-20261029/lab1-goal-run-05/result.json): two feedback-driven actions, 147 ms total hold, distance 0.642776 -> 0.450967 -> 0.118824; STOP/disarm, then a distinct advancing stationary confirmation. |
| Lab-1 repeat | Goal run 06 sent one released Q pulse, then failed because usable feedback missed the 4.5-second deadline. No accepted repeat. |
| Lab-2 calibration | [Run 07](../../artifacts/two-lab-movement-20261029/lab2-calibration-run-07/result.json): S150 ms displaced 0.662102 planar units and -0.419983 vertically. Explicitly one-dimensional. Earlier Q/E observations did not establish usable lateral movement. |
| Lab-2 goals | Both goal runs failed before ARM on stale/unavailable feedback; neither sent movement. |
| Acquisition problem | [Diagnosis](../../artifacts/two-lab-movement-20261029/lab2-reader03-reliability-diagnosis-20261029T214700Z.md): a 56.7-second no-fresh interval; Win32 299 partial-copy failures, 6-9.4-second scans, and a later 10-second timeout. Short fresh streaks did not predict a successful armed window. |
| Cleanup | [Aggregate 02](../../artifacts/two-lab-movement-20261029/final-cleanup-02/summary.json), referencing actual `final-cleanup-01/readers/` proofs. Both temporary readers ended; both receiver processes/listeners are absent. Lab-1 receiver's termination cause was not observed. |

Full evidence and failed attempts are in the
[trial report](../validation/automated-movement-two-lab-2026-10-29.md).
Generated artifacts are ignored by Git and local to this PC; do not assume a
fresh clone contains them. Missing historical evidence is a limitation, not a
reason to manufacture replacement receipts.

## Code and build checkpoint

| Commit | Change |
| --- | --- |
| `0e2af08` | Bounded feedback controller and reviewed movement sessions. |
| `d382173` | One complete-scan retry on Win32 299; bounded feedback waits. |
| `369303c` | Source-clock validation across actual acquisition intervals. |
| `2235569` | Fresh pre-arm wait and explicit S-only 1-D mode. |
| `1a07583` | Early receipt may be a barrier only; later receipt remains strict. STOP precedes released arrival confirmation. |
| `2d38866` | Reuse accumulator scratch storage instead of allocating per chunk. |
| `aa7d303` | Trial outcome, limitations and final cleanup record. |

Relevant modules are [movement_controller.py](../../scripts/movement_controller.py),
[movement_feedback.py](../../scripts/movement_feedback.py),
[run_movement_session.py](../../scripts/run_movement_session.py),
[WindowsMemoryScanner.cs](../../src/RiftReader2.Live/WindowsMemoryScanner.cs), and
[EnvelopeCandidateAccumulator.cs](../../src/RiftReader2.Live/EnvelopeCandidateAccumulator.cs).

The optimized published binary is:

`C:\work\riftreader2\artifacts\validation\20261029T215649Z-6e2ed889\native-published\RiftReader2.Live.exe`

SHA-256: `322241A454A4685F75964F8DA4576A435DAA98D208CB4502D77B29D26390E268`.
Its full gate passed **551 .NET tests** (366 core + 185 Live), **1,068 Python
tests run** (1,066 passed, two skipped), native/Lua/contracts/format checks and
781 relative links. It was **not deployed to either VM**.

All final live trials used reader SHA
`33A21D0B32BD1C3978CABDFE7EC9C43A0413DB3B4B0654C3BBF8516EAD07F71B`.
The [isolated benchmark](../../artifacts/two-lab-movement-20261029/accumulator-microbenchmark/README.md)
measured roughly 303 MB allocation per 256 MiB of scanned input in the old
accumulator, versus effectively zero repeated allocation with scratch reuse.
This is not a measured whole-scanner speedup or proof of the cause of Win32 299.
Rehash the selected binary before deployment; if source changed, build/test the
new source and record its new hash rather than retaining this expected value.

## Last-observed lab and connection state

Both RIFT processes, VMs, managed game-control agents and native control hosts
were preserved. [Final host status](../../artifacts/two-lab-movement-20261029/root-final-host-status.json)
reported connected/ready, disarmed, not busy, no held inputs and no recovery.
Movement leases were released. Persistent host console ownership is expected;
it is distinct from a movement-session queue lease.

| Lab | VMX / console | Game at cleanup | Private control configuration |
| --- | --- | --- | --- |
| Lab-1 | `C:\rift modding\vms\rift-lab\rift-lab.vmx`, VNC 5905 | RIFT-LAB-1; PID 6876; start ticks 639288974836522510 | `artifacts/control-fleet-live/lab1/host.json` |
| Lab-2 | `C:\rift modding\vms\rift-lab-2\rift-lab.vmx`, VNC 5962 | RIFT-LAB-2; PID 4200; start ticks 639288974754421524 | `artifacts/control-fleet-live/lab2/host.json` |

Both last-observed game executables had SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
Read current status and guest identity before using any of these values. Guest
PIDs must be checked inside their guest, never with main-PC `Get-Process`.
Use exact .NET start ticks; rounded CIM timestamps are insufficient.

Existing host plans were `artifacts/two-lab-movement-20261029/host-lab1-03/plan.json`
and `host-lab2-02/plan.json`. Validate them against current host state before use.
The queue is `artifacts/native-coordination-live/queue.sqlite3`, with resources
`vm:rift-lab-1` and `vm:rift-lab-2`. Idle guest connections reconnect after a
120-second read timeout; this can briefly quarantine one resource. Require its
normal reconciliation to finish; do not bypass a blocked queue.

Native Codex connections and cached guest credentials already exist. Reuse them;
do not re-pair, copy auth files, install SSH, or change startup settings as
incidental setup. Use [lab-codex.md](lab-codex.md) for guest read-only jobs.
Guest agents can measure local process/load state and review source snapshots;
the main coordinator alone owns game input. Existing
[VM snapshots](lab-snapshots.md) are recovery references, not instructions to
revert either VM.

## Reusable bootstrap, without stale identities

1. Recheck Git status, current hosts, VM/game/build identity and exclusive input
   ownership. Status CLI: `C:\Python314\python.exe scripts/control_client.py
   --config artifacts/control-fleet-live/lab1/host.json status` (repeat for lab2).
   Preserve working hosts and managed agents unless a verified conflict requires
   their normal graceful shutdown/restart flow.
2. Start separate observation receivers before launching readers. The already
   authorized, unchanged receiver exists at
   `C:\rift modding\RiftReader\tools\riftreader_workflow\guest_observation_receiver.py`;
   SHA-256 `C7EF8F7685611D7B497FB2A43333BEA44DA9FF4E19AAB98A1F38F12B67A13AE5`.
   It accepts `--config PRIVATE_CONFIG --output NEW_OUTPUT`. Existing private
   templates are `.local/two-lab-movement/lab1-receiver.json` and lab2 equivalent,
   ports 49813/49923 at 192.168.56.1. Keep tokens private. Use hidden background
   launch, new output directories and new PID/start/image/listener ownership
   receipts. The receiver is reused operationally; do not modify V1 source.
3. Reuse `artifacts/two-lab-hour-20261029/reader_launcher.py`. Its inspected
   arguments include `--lab`, `--expected-game-pid`, `--expected-game-start-ticks`,
   `--expected-game-sha256`, `--reader`, `--reader-sha256`, `--receiver-config`,
   `--duration-seconds`, `--poll-interval-milliseconds`, and fresh `--output`.
   It requires an already-running receiver and cached credentials. Use bounded
   durations and the previous 250 ms poll setting for a comparable first trial.
4. A new reader produces a new nonce. The ended reader's addon binding cannot
   simply be overwritten: use the existing reviewed console route for
   `/reloadui`, wait for reload, then `/rr2guide bind LAB NEW_NONCE`. This binds
   live and guidance channels. Recheck foreground/chat/panels in a fresh capture.
   The standalone console helper conflicts with a native host's console mutex;
   use the established graceful ownership handoff and revalidate afterward.
5. Build a NEW source pin with
   `artifacts/two-lab-hour-20261029/guidance_inputs.py source-pin` from the NEW
   reader summary, VM identity and fresh receipt. The optional read-only
   `artifacts/two-lab-movement-20261029/wait_feed_ready.py` waits outside the
   movement lease/capture for two advancing fresh receipts; it does not prove
   sustained availability. Adapt the journal's source paths and deadline for
   this run; its previous deadline was 22:00Z and has passed.
6. **Calibrate both labs again.** A different reader instance/hash/nonce makes
   every previous calibration profile unusable for live input. Old vectors,
   coordinates, alpha factors and screenshots are historical references only.
   The 1-D runner also binds the start to its calibration endpoint within 0.10
   planar units; a subsequent moved start needs a new applicable calibration.

Use the tracked runner's `prepare` and `run-reviewed` commands. The default is
2-D with two measured keys; explicit 1-D is `--dimension 1d --keys s`.
`artifacts/two-lab-movement-20261029/review_movement.py` is convenience glue only
after actual screenshot inspection, not automatic approval. Prepare, emit/view
the capture and retain its ID together, then execute promptly: the lease TTL is
30 seconds and the capture age bound is 45 seconds. Do not repeat the rejected
60-second lease experiment or wait out a long recovery while holding a capture.

## Next experiment and success standard

The saved prompt proposes an eight-minute fixed no-input observation window on
both optimized readers, followed by two consecutive accepted nearby trials per
lab when the feedback path supports them. These are **new proposed acceptance
targets**, not prior results or universal reliability guarantees. Keep all
failed attempts in the denominator and retain outages, warming and missed
journal sequences. Separate startup warmup from the fixed observation window.

Freshness comes first. Lab-1 is the W/Q reference; Lab-2 needs explicit S-only
qualification unless new measurements establish another direction. If repeated
failures reproduce the acquisition problem, investigate that problem rather
than repeatedly preparing movement until one attempt happens to pass. Prefer
the smallest supported fix. A tracked-region fast path is a later option: Lua
strings relocate, and a range-only scan cannot prove absence of conflicting
envelopes elsewhere. It is not already implemented or qualified.

Keep existing limits: 15-second finite arm, 12-second motion phase, <=150 ms per
pulse, <=900 ms total hold, <=6 actions, <=6-unit radius, 0.50 cross-track guard,
1.5 vertical drift guard and 0.30 arrival tolerance. Require at least two actual
action-feedback iterations, STOP with verified release, and one advancing
no-input confirmation within three seconds. No silent rearm, stale-feedback
substitution, unmeasured inverse key, general pathfinding or combat expansion.
Direct ChatGPT Computer Use in RIFT and patch recovery remain deferred.

Run focused checks for changes, then the repository gate when code changes:
`pwsh -NoProfile -File scripts/validate.ps1`. Keep heavy builds/tests outside
timing-sensitive live measurements. Documentation-only updates need link and
whitespace validation, not the full suite. Commit coherent changes promptly.
Finish with exact-owned reader/receiver cleanup, preserved useful hosts and
agents, independent result review and a concise evidence-linked report.

Do not rerun old cleanup scripts unchanged: their hard-coded process identities
belong to ended processes. On Windows, a terminated process object can remain
openable; query failure alone is not proof of exit. Reuse the corrected
terminal-check technique, with fresh identities, and hash terminal files after
writers have ended.
