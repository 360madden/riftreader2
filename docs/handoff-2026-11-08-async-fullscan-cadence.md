# RR2 — async reader two-lab handoff (2026-11-08, 09:45 EST)

Branch `codex/modular-foundation` on **AMD-DESKTOP**, checkout `C:\work\riftreader2`; the LEGION laptop is a separate machine. **No movement/combat/reload/reboot**; each managed controller was restored and independently verified ready, disarmed, idle and holding no input.

## Verified change

- `src/RiftReader2.Live/Program.cs` implements one target+nonce-pinned background full-memory scan, while a single main writer continues fresh scoped or explicitly unavailable receipts. Full scan retry-start and completion times are captured on the worker. Identity changes and shutdown cancel+await worker. 10-second anchor expiry unchanged. Program SHA256 `6C5B95249DB3B07B87DA272DE72E14B4A8DCF8EAE7D1FC68BDAAF66F4E23D4EC`.
- Published binary `artifacts/live-reliability-20261108-01/publish-async-fullscan-01/RiftReader2.Live.exe` SHA256 `ADBA0EC7047AB056934D52ADFB3F70E657C5C0D251F67A92EF756F413D8646AF`, 118,019,936 bytes. Live tests **992/992**, Core tests **380/380**, independent static review passed. The 256KiB scanner chunk experiment worsened live scan stability; reverted to **64KiB** before publishing.

## Both-lab live results

| Test | Lab1 RIFT PID 6820, 6GiB scan | Lab2 RIFT PID 10612, 4GiB scan |
|---|---:|---:|
| 60s received frames / max gap | 82 / 1.026 s | 75 / 1.012 s |
| 90s received frames / max gap | 126 / 1.073 s | 108 / 1.441 s |
| >4.5 s gaps, skipped sequences (90s) | 0 / 0 | 0 / 0 |
| HTTP200 in both samples | 208/208 | 183/183 |
| Scoped fresh 60s + 90s | 42 + 56 | 65 + 94 |
| 90s full-scan failures | 14 read-failed; 13 time-budget | 0 |
| End-of-session | terminal seq889, 14:44:07Z | terminal seq809, 14:44:17Z |

Source nonces `c5977e2a618a45788360766be30b3797` (Lab1 reader PID3036) and `f68c28b2675a4a6a877d06011d3d0ba8` (Lab2 reader PID1992) **expired; never reuse**. Both binds were screenshot-reviewed and acknowledged in game. All receipt samples had `gameReady=false`: no native XYZ anchor or movement gate established.

## Immediate next actions

1. Preserve the accepted async reader refactor; investigate Lab1's 6GiB scanner errors/time-budget separately from publication cadence.
2. Receiver journal migration is queued; `scripts/ensure_receiver.py` pins receiver source hash, so update the pin only alongside audited receiver code, then do a **controlled managed receiver restart with no active readers**. Never bypass the pinned source gate.
3. Use a sequence-preserving observer and new ≥1200s bounded readers in both labs for the strict 480s source-freshness gate; prior Lab2 attempt failed due latest-only sampled seq963→967 4.515s gap, not proven HTTP outage. Preserve strict 4.5s threshold and fail-closed movement gate.

Machine-readable companion: `docs/handoff-2026-11-08-async-fullscan-cadence.json`.
