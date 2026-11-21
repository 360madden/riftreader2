# Physical RIFT 1179 — recovering the advancing Lua Telemetry scope

**2026-11-21, 08:23–08:35 EST · AMD-DESKTOP · physical RIFT PID 37676**
**Source build:** `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`
**Process start ticks:** `639308565554559088`

## Result

- A fresh, no-input native six-source acquisition succeeded on the new process:
  20 raw stat candidates, 18,208/18,208 candidate HP, XYZ `(6037.733, 832.36426, 3142.4585)`, and matching native Silverwood zone-ID endpoints. Source: ignored `artifacts/physical-state-20261121-0829-p37676/summary.json` (SHA-256 `1AE5DCFDEF2B7FE028D6F0DC0630ABC69AC5EDAA7F9BD2CC7C816A8050FA4463F`).
- The initial `--auto-scope` survey starting at `0x13000000` found **zero frame markers** across 227,999,744 readable bytes. This was an address-coverage failure, not a native-reader failure or a demonstrated stopped publisher. Source: ignored `artifacts/physical-telemetry-target-20261121-0831-p37676/scope-survey.json`.
- Bounded read-only inspection found Telemetry frame markers in a *different* low address range, approximately `0x05000000–0x09E00000`. A two-scope survey from `0x5000000` found valid candidates in both `0x5000000` and `0x9000000`, but its old highest-single-generation heuristic selected `0x5000000`. The ensuing two passes had 11 and 6 frame occurrences with **no newly advancing generation**, correctly exiting 2. Source: ignored `artifacts/physical-telemetry-target-20261121-0833-p37676/summary.json` (SHA-256 `C7B50FFD7E48E1BEE2A95857827768E24EA9A28E6010F33A4F85CC921A6F0FA6`).
- Explicitly selecting `0x9000000` then yielded **50+48** Lua frame occurrences, **53 unique** source sequences, fresh pass-2 source progression, matching native/Lua zone candidates and a successful independent target replay (exit 0). All 53 observed Lua target frames were `none`; both native endpoints reported raw target getter zero. This is a **compatible no-target baseline candidate**, not an A→B→A result or independent no-target proof. Source: ignored `artifacts/physical-telemetry-target-20261121-0835-p37676/summary.json` (SHA-256 `1DD049671AECB761358866C9883F1F44A9115274A139CD4C4871109C6EDC9593`).

## Narrow code fix

`scripts/capture_physical_telemetry_zone.py` now re-observes **competing** valid survey scopes after a bounded delay, preferring newly advanced sequences with the same publisher session and epoch instead of blindly choosing the highest retained sequence. The optional probe is still **survey-only**, and the original exact-process native brackets, two newly acquired Lua passes, source hashes, independent replay, and fail-closed result gates remain authoritative.

Added synthetic regression cases for a stale higher-sequence scope versus an actively advancing lower-sequence scope, and for two static competing scopes. **93/93 focused offline tests passed** across the auto-scope, capture, zone replay, and target replay suites.

**Physical follow-up after the patch:** Starting the same two-scope survey at `0x5000000` selected `0x9000000` using `selectionBasis=advancing-same-session-survey-candidate` and correctly marked the `0x5000000` region as nonadvancing in the survey. The subsequent full acquisition yielded 49+49 saved frames without new source progression; it **exited 2 / unqualified**, as required. Source: ignored `artifacts/physical-telemetry-target-20261121-0837-p37676-progression/summary.json` (SHA-256 `9F05D8DB24928342650DF7914B98C87AFE920C8F3FDBA270E529F8E8B7AB0DB4`).

## Remaining work

The search **origin is still explicit and process-dependent**; this patch improves choosing between discovered scopes but does *not* scan arbitrary mapped regions automatically. Implement a bounded readable-private-region locator rather than carrying a heap address to the next process. A valid A→B→A requires an actual observed target change and newly advancing frames; none occurred here. No game input, focus change, game restart, Lua reload, client memory write, or sibling repository change was made.
