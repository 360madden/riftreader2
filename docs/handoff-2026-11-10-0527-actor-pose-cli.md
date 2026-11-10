# RR2 handoff — 2026-11-10, 05:27 EST

**Host/branch:** AMD-DESKTOP (Workbridge identity confirmed), `C:\work\riftreader2`, `codex/modular-foundation`. RIFT reported offline. No game input, controller changes, or live read attempts during this continuation.

## Practical development now pushed

- `9088e62` current-build, owner-pinned native actor/model/render pose reader (candidate only).
- `ad92cf4` exact 64-bit actor/position addresses emitted as decimal strings.
- `baabb70` authenticated `/api/native-actor-pose` endpoint, disarmed native-read lease.
- `8063fb6` HTTP authentication/lease refusal tests.
- `7ff03b9` on-demand `scripts/fresh_native_actor_pose.py` with raw evidence/hash retention.
- `6a8ef1a` optional `--fields actor-pose` in standard Lab2 `scripts/read_native_telemetry.py` (default stays position+vitals). Reads must share pinned game/VM/agent/player ownership. Python 38/38 focused tests passed.
- `52320d0` `.NET 10` `analyze-turn-probe --matrix actor|model` consumes two *raw* actor-pose reports and the A-key down/up receipt. Existing `primary|secondary` behavior retained. Full .NET CLI test project 414/414 passed.
- `7497afc` immutable, SHA-pinned before/after screenshot comparison via `scripts/compare_turn_frames.py`, with side-by-side preview; 42/42 relevant Python tests passed.

All listed commits pushed to `origin/codex/modular-foundation`. Existing unrelated untracked energy/anchor files preserved.

**New offline release, not deployed:** `artifacts/native-actor-pose-release-20261110-0536/publish/RiftReader2.Live.exe`, 118,064,992 bytes, SHA-256 `1A3BA9D3CDAF163C59DE0E75A2E3B007190F0F37B80CBFCBCB488B9F9C5DA9EA`. Built after 1032/1032 `RiftReader2.Live.Tests` passed. Any staging remains blocked on verified controller/queue ownership cleanup.

## What works when the live lane is ready

1. From `C:\work\riftreader2`, with a live authenticated/pinned/idle Lab2 agent:
   `C:\Python314\python.exe scripts\read_native_telemetry.py --lab lab2 --expected-host AMD-DESKTOP --fields actor-pose`.
   It retains a raw `samples.json` under ignored `artifacts/native-current-actor-pose-agent/runs/lab2/`.
2. Capture **before** actor-pose raw report + screenshot. Conduct one uncontaminated 75–125 ms A pulse through the existing authorized controller, retain verified down/up/release receipt, and then capture **after** raw report + screenshot.
3. Run `dotnet run --project src/RiftReader2.Cli -- analyze-turn-probe --before <before-samples.json> --after <after-samples.json> --receipt <action-receipt.json> --matrix actor --uncontaminated true` (or `--matrix model`). This computes *candidate* delta/rate and optional bounded next pulse; it does not send input or assert body-facing. Never mark uncontaminated if Joey was typing during the interval.

## Live blocker — do not auto-clear

Lab2 managed controller task PID 14220 had live source/receipt drift (`managed-runtime-changed`), disconnected guest, and blocked canonical nav queue with **no cleanup receipt**. Watchdog `session-identity-changed` logged `emergencyStopVerified=false`. No safe offline queue-release proof: do not kill/restart controller, bypass identity, clear queue or inject input. When game returns, require authenticated pinned guest and verified STOP/release/owner cleanup or operator-reviewed orderly reconciliation.

**Static-heading next lead (not a qualified field):** current SHA 1935A05C actor renderer consumer RVA `0x688F20` multiplies `actor+0x398` × `actor+0x3EC`. The setter for `actor+0x3EC` is not yet identified; inspect its exact-build dataflow/callers rooted near `0x613800` rather than transplanting V1's old yaw RVA. No new full scan was started.

**Not claimed:** live actor-turn success, independently validated body heading, screenshot pair, passive freshness of underlying matrix, or release of the stuck queue. Historical yaw location must not be transplanted to current executable SHA. Keep actor/model angles provisional until corroborated.
