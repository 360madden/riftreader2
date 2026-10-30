# Two-lab current controller and reader recovery — 2026-10-30

Checkpoint near 20:23 UTC. Branch codex/modular-foundation. Work scope: current VMware/game/source/host identity, startup, strict feedback and no-input diagnostics. **No movement pulse or gameplay automation executed.**

## Runtime state (time-scoped, not durable identities)

| Check | Lab 1 | Lab 2 |
| --- | --- | --- |
| VMware PID, VNC | 11164, 5905 | 35784, 5962 |
| RIFT PID | 9928 | 7220 |
| Game SHA256 | 1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8 | same |
| Receiver PID / host-only port | 24588 / 49813 | 28860 / 49923 |
| Reader PID / new nonce | 8120 / 67717fe706df4aec92bb2e3828b0d61c | 7828 / c45cc9c512fd4e678eabeb0608c210ff |
| Reader configured expiry UTC | 20:36:30 | 20:38:24 |
| Addon binding and source selection | Bound / selected, 9 candidate matches | Bound / selected, 10 candidate matches |
| Strict pin / two advancing samples | Accepted | Accepted |
| Detached host PID | 51076 | 57852 |
| Host session, inside Workbridge job | Session2 / no | Session2 / no |
| Guest agent, RIFT foreground | Connected / verified | Connected / verified |
| Host coordination and held keys | ready, disarmed, no keys | ready, disarmed, no keys |
| Long-window telemetry | NOT qualified | 8-minute sample running at checkpoint |
| Movement accepted | None | None |

Game start ticks Lab1 639289678898789677, Lab2 639289682244523224. Current source reader SHA256 322241A454A4685F75964F8DA4576A435DAA98D208CB4502D77B29D26390E268. Both host-only receiver TCP ports and specific owners were checked. Both hosts were started from fresh unique identity- and nine-source-hash-pinned plans, not reused launch plans. Both exact guest machine identities, queue resources (vm:rift-lab-1 and vm:rift-lab-2), disarm, busy=false, recoveryRequired=false, and desktopInputsDown=[] passed strict PinnedHost status. SQLite queue preserved: both resources unblocked with no lease holder. All guest logons performed fresh VM-specific cached credential check.

## Lab 2 reviewed binding and feedback

An early /rr2guide rebind failed with an in-client "Bind a reader before rebinding" response. A hostile/loot scene blocked subsequent input until fresh screenshots proved a stationary, noncombat state. One reviewed Enter cleared AFK and opened chat; a new screenshot showed empty focused caret; a second prepared Enter was deliberately not executed. A separately reviewed /rr2guide bind lab2 c45cc9c512fd4e678eabeb0608c210ff sent and released correctly. The live game chat returned "RiftReader2: Bound lab2: manual feedback only." Receiver then selected ten matches and HTTP200/fresh, strict source pin accepted, and independent advancing samples passed before and after host restart (outer1690->1691, then1755->1756, unchanged game/player/epoch). Runtime evidence in ignored artifacts/two-lab-resume-20261030/phase2-lab2-bindcorrect-01, phase2-lab2-source-pin-01.json, phase2-lab2-feed-ready-after-host-01.json, host-lab2-03/ready-gate.json. Lab 2 full 480-second no-input window started under job rr2-phase2-lab2-eight-minute-observation-1030-01 around20:19:56Z, not yet complete in this checkpoint.

## Lab 1 second 480-second diagnostic: FAIL

A second full read-only forensic sample (job rr2-phase2-lab1-gate-forensics-8min-1030-01) produced 252 distinct outer receipts. Strict gate accepted245, rejected one initially stale receipt, one incomplete scan and five warming observations (reason observation-gap-requires-warmup). The longest between-accepted gap was 16.214 sec (outer1318->1323); another was 6.972 sec. During consecutive warming samples full memory scans took approximately 3565, 2176, 2242, 2215ms while selection remained selected and candidate source sequence advanced. This reproduces intermittent source freshness loss and confirms the stale-data gate is correctly withholding data. Do NOT relax five-second freshness or 4.5-second movement feedback deadline.

**New optimization mismatch discovered:** The currently active reader executable was published 2026-10-29 21:56:52 UTC, before tracked fast candidate-region source commits 4e91cac, 451fed5, fc9dd49 added Oct29 23:15–23:43 EDT (Oct30 03:15–03:43 UTC). Consequently this running binary necessarily predates the faster scan implementation; source history and build timestamp support this independently. Recent receipts contain no fastObservation or fastObservationDiagnostic blocks, consistent with older build. Tests under tests/RiftReader2.Live.Tests/FastObservationSessionTests.cs cover fail-closed region cap and source identity. The newer source has NOT yet been built, deployed or shown to solve this live failure.

## Next steps

1. Complete Lab2 ongoing full eight-minute observation, honestly recording failure or pass and strict maximum gap. Avoid heavy shared-host builds during its timing window.
2. Build/publish a newly source-pinned reader from current checkout with full normal local validation, inspect its SHA, positive and negative fast-region tests and new binaries, preserving older artifacts.
3. Before deployment, confirm game/VM/reader/receiver identity, guest cached credentials per attempt, reader expiry, no duplicate live reader, and exact host console mutex ownership. Changing reader may require reviewed addon rebind and host graceful handoff.
4. Repeat independent sustained full/fast source qualification after deploy. Do not perform movement until all fixed-window freshness, scenery, lease, disarm and release checks pass. Movement remains restricted to reviewed 15-second finite arm, 12-second motion, <=150ms individual pulse, <=900ms total hold, <=6 actions, <=6 units radius, <=0.5 cross-track, <=1.5 vertical drift, <=0.3 planar arrival and independent stationary advancing confirmation.
5. A separate ChatGPT desktop Chat read-only telemetry reviewer was dispatched with maximum agents requested, but its report has not yet been received; do not claim results or agent count.

Runtime evidence retained under ignored artifacts/two-lab-resume-20261030. This is a readiness/research checkpoint, not movement acceptance.
