# Lab 1 feedback reliability and controller recovery — October 30, 2026

Observed window UTC 19:45:43 to 19:53:43; controller restored around 19:56 UTC. Previous verified milestone commit 74d4259.

**Verdict: Lab 1 controller/agent/queue ready; 480-second feedback reliability NOT QUALIFIED. No movement trial was run.**

| Measurement | Observed result |
| --- | --- |
| Window and polls | 480 seconds; 951 polls |
| Strict valid polls / distinct receipts | 928 / 297 |
| Freshness misses / duplicate polls | 23 / 631 |
| Scan elapsed milliseconds median / p95 / max | 1032 / 1534 / 2089 |
| Capture age milliseconds median / p95 / max | 816 / 1587 / 1997 |
| Delivery skew milliseconds median / p95 / max | 2.98 / 7.63 / 13.34 |
| Worst observed no-new-receipt gap | **5.043 sec (FAIL, target 4.5 sec)** |
| Second too-long gap | **4.542 sec (FAIL)** |
| Observed planar drift / player epoch changes | 0 / none |
| Runtime input sent by observer | None |

The worst gap was 19:51:12.0475 to 19:51:17.0901 UTC; receiver outer sequence jumped 544 to 547, while bounding scans took ~1.04 seconds each. Second gap was 19:46:33.4227 to 19:46:37.9642, outer sequence 365 to 368, with bounding scans ~1.03 seconds each. A third 3.03-second gap had ~2.08-second bounding scans. 47 between-receipt gaps exceeded 2 seconds. The +3 sequence jumps mean the existing polling data does NOT prove whether the reader, receiver or monitoring process caused the latency. A stricter timestamped diagnostic is required; do not loosen the movement 4.5s freshness bound.

Exact source pin was Lab1 reader PID8120, new nonce 67717fe706df4aec92bb2e3828b0d61c, game PID9928 and its build hash. Same sampled player u035400012FA2D207, addon epoch1, and measured XYZ 7405.48974609375 / 863.5799560546875 / 2931.35986328125 throughout the window. These coordinates belong ONLY to that specific game/reader epoch and must never become a future preset waypoint. Evidence retained under ignored artifacts/two-lab-resume-20261030/phase2-lab1-observation-8min-01.json. Workbridge job rr2-phase2-lab1-eight-minute-observation-1030-01 ended exit 2 with status not-qualified.

**Controller recovery separate from feedback:** Lab1 guest VMX under RIFT-Lab-1 PID11164, guest control agent PID3852 Session1. Rechecked actual VM identity, nine runtime source hashes, private host config hash, existing SQLite queue vm:rift-lab-1 blocked with holder absent, and absent host ports. Fresh plan host-lab1-03/plan.json launched detached via WMI Create to Windows Session2 pythonw.exe PID51076 (inJob=false). Strict PinnedHost.status(require_armed=False) PASSED: authenticated guest connected, RIFT PID9928 foreground, console reservation held, coordination ready resource vm:rift-lab-1, armed false, busy false, no held desktop inputs, recoveryRequired false. New advancing Lab1 strict feed after host startup passed (outer 750->751, addon 7286->7290). SQLite after recovery: Lab1 unblocked no holder, Lab2 blocked no holder. Host ready receipt in ignored host-lab1-03/ready-gate.json.

**Lab 2:** Game PID7220; independently started reader PID7828 but no selected source. A reviewed rebind command was rejected because addon not bound. Last read-only capture showed a changed character position after earlier hostile combat and loot modal; no further chat or movement input was sent. Host Lab2 plan host-lab2-03/plan.json is prepared but intentionally not started. Controller API refused.

**Next:** Determine source timestamps, receiver sequence jumps, poll duration and freshness misses with >=250-ms read-only sampling; repeat full 8-minute reliability gate after an evidence-backed correction. Lab2 requires a newly reviewed safe stationary scene and fresh currently active nonce before correct bind; otherwise defer. Do not start movement until source, host, exclusive queue, terrain and disarm gates pass. No outstanding cloud Codex jobs were started for this milestone; separately dispatched ordinary ChatGPT telemetry worker report is not yet available.

Existing movement limits remain 15-second finite arm, 12-second action, 150-ms pulse, 900-ms total keyhold, six actions, radius six, cross-track 0.5, vertical 1.5, arrival 0.3 and advancing stationary confirmation. This checkpoint accepts host readiness only, not movement.
