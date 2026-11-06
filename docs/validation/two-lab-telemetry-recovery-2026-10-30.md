# RiftReader2 — Two-lab telemetry recovery, milestone 1 (2026-10-30)

Recorded about 19:45 UTC / 15:45 EDT. Branch: codex/modular-foundation. Starting HEAD f6bcaee. This milestone covers current guest/reader identities, reviewed nonce operations, strict source qualification, and fail-closed handling. It does NOT establish live movement success.

| Gate | RIFT-Lab-1 | RIFT-Lab-2 |
| --- | --- | --- |
| VMX | C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx | C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx |
| VM PID | 11164 | 35784 |
| Game PID / exact UTC start ticks | 9928 / 639289678898789677 | 7220 / 639289682244523224 |
| Game executable SHA256 | 1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8 | Same hash |
| Existing receiver owner | PID 24588, private 192.168.56.1:49813 | PID 28860, private 192.168.56.1:49923 |
| New live reader | PID 8120 | PID 7828 |
| New reader nonce | 67717fe706df4aec92bb2e3828b0d61c | c45cc9c512fd4e678eabeb0608c210ff |
| Nominal reader expiry (UTC) | 20:36:30 | 20:38:24 |
| Addon command | Reviewed bind sent/released | Reviewed rebind sent/released but refused: "Bind a reader before rebinding." |
| Source selected | Yes, nine matches | No, pending correct bind |
| Strict source pin and advancing receipts | PASSED | Not yet qualified |
| Movement performed | No | No |

Both read-only guest process probes found RIFT running. Fresh authenticated checks, including the required per-attempt cached guest credential lookup, acquired exact build and process identities. The exact receiver PID/start/image matched saved receipts. A Windows Get-NetTCPConnection query misleadingly returned no listeners; independent direct TCP connects to the two exact private addresses and strict receiver owner lookup PASSED. Do NOT terminate or duplicate the receivers based on that inaccurate query.

The previous host controllers were intentionally stopped for exclusive console maintenance. Their operator APIs remain unavailable; both VM resources in the existing SQLite queue had no holder. The queue was not reset. The selected reader executable SHA256 was 322241A454A4685F75964F8DA4576A435DAA98D208CB4502D77B29D26390E268 for both new 60-minute runs. Reader startup sent no game input.

Lab 1's fresh game screenshot established foreground RIFT, closed chat, and no blocking panel. The reviewed Enter-only command opened empty chat; the separately reviewed /rr2guide bind lab1 67717fe706df4aec92bb2e3828b0d61c completed with input released. A receiver read then showed selected with nine matching candidates. The tracked build_live_source_pin.py accepted the exact source (riftReader2 / whole-readable-private / nonce-bound-complete-process-scan/1). The existing wait_feed_ready.py accepted two strictly advancing samples: outer seq 155 -> 156, addon seq 5381 -> 5384, same addon epoch and player. A read-only three-second observation smoke test passed with two advancing receipts and zero X/Z drift. An eight-minute window started under Workbridge job rr2-phase2-lab1-eight-minute-observation-1030-01; its final result is NOT yet known at this checkpoint.

Lab 2's rejected rebind was confirmed in the fresh after-screen chat response. The subsequent separate open-chat preflight screenshot showed Sinister Devil hostile target/health bars and combat cues. Its planned input was NOT executed. A new /rr2guide bind lab2 c45cc9c512fd4e678eabeb0608c210ff can only be reviewed after a fresh safe game-screen check, current nonce/reader health, no owner contention, and no danger. If the reader expired, a new one must be launched instead.

Ignored runtime evidence within artifacts/two-lab-resume-20261030:
- fresh-lab1-game-identity-1030-01.json and fresh-lab2-game-identity-1030-01.json
- phase2-live-reader-lab1-01/summary.json and phase2-live-reader-lab2-01/summary.json
- phase2-lab1-openchat-01/, phase2-lab1-bind-01/, phase2-lab1-source-pin-01.json, phase2-lab1-feed-ready-01.json
- phase2-lab2-rebind-01/after-screen.png and phase2-lab2-openchat-02/review-screen.png
- phase2-window-observer.py and phase2-lab1-observation-smoke-01.json; expected later final phase2-lab1-observation-8min-01.json

Next: finish the eight-minute read-only Lab-1 window and analyze honest gaps/latency; capture Lab-2 screen again before any input; fix Lab-2 bind only if safe and same reader is alive; then verify a new strict source pin. Rebuild each host with a newly identity/hash-pinned and separately owned persistent controller plan, no duplicate hosts or queue reset. Motion may start only after both host/guest agents, independent feedback, terrain, lease, disarm and exact release gates pass. Preserve 15-second finite arm, 12-second motion, <=150ms per pulse, <=900ms cumulative key hold, six actions, six-unit radius, <=0.5 cross-track, <=1.5 vertical drift, <=0.3 arrival tolerance and advancing stationary confirmation. No input was authorized in this milestone beyond reviewed addon chat commands.
