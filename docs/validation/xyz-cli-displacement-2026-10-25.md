# XYZ displacement through VMware CLI, October 25

**Live result: `candidate-motion-consistent`.** The existing corrected guest
reader collected native XYZ and independent Lua snapshots before and after
Joey's manually reported movement. Native displacement was **2.0381402162 game
units**; Lua displacement was **2.0319611259**. No automated game input was sent.

| Measurement | Native | Lua |
| --- | --- | --- |
| Before X | 7444.22119140625 | 7444.2197265625 |
| Before Y | 863.5908203125 | 863.58996582031 |
| Before Z | 2973.241943359375 | 2973.2399902344 |
| After X | 7442.19482421875 | 7442.1997070312 |
| After Y | 863.5908203125 | 863.58996582031 |
| After Z | 2973.460693359375 | 2973.4599609375 |
| Delta X | -2.0263671875 | -2.0200195313 |
| Delta Y | 0 | 0 |
| Delta Z | 0.21875 | 0.2199707031 |

Maximum endpoint disagreement was **0.0048828124 units per axis**, below the
existing 0.02 gate. Maximum displacement disagreement was **0.0063476562 units
per axis**, below the existing 0.04 gate. Native/Lua acquisition separation was
**0.319 seconds before and 0.302 seconds after**. All three sampler readings at
each endpoint were stable; raw pointer bytes supplied the precise values above.

## What actually ran

- Installed Workstation **26.0.0 build-25388281**: authenticated `vmrun`
  `runProgramInGuest` and `copyFileFromGuestToHost` both succeeded. The existing
  guest install `C:\RIFT_TRANSFER\RR2-XYZ-Interface-oct25-02` was reused, with
  reader/profile hashes checked before each phase. No new deployment or media
  change was needed.
- RIFT **PID 1224**, start ticks **639285359295548343**, executable SHA
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`;
  owner `0x202BA8B1480`. Both phases used the same exact process/build.
- Before samples: **17:12:28–17:12:30 UTC**; after samples:
  **17:32:15–17:32:17 UTC**. These are endpoint observations, not a continuously
  monitored twenty-minute trajectory. The user confirmed "Moved and stopped";
  movement duration, path and key-release timing were not independently measured.
- Each bounded Lua scout stopped at its 512 MiB scan budget, explicitly
  `partial / byte-budget-exceeded`, and retained two complete 28 KiB snapshots.
  All four cross-phase snapshot comparisons passed `advanced-in-covered-scope`.
  The selected newest pair advances sequence **18038 → 20376**, same player
  `u035400012FA2D207`. The same-phase baseline diagnostic correctly rejected
  reversed source sequence and is retained, not presented as an advancing pair.
- Both returned ZIPs matched guest-declared SHA/length; all **34 extracted files**
  matched the exact member sets and per-file hashes. The unchanged
  `review_native_motion_pair.py` accepted the selected pair with its default gates.
- The temporary guest credential session exited normally. Guest credentials
  were not saved. V21 remained the sole console owner; final authenticated status
  at **17:33:11 UTC** showed the same game/VM, ready/connected controller, guest
  disarmed/idle, and no sampled held inputs. No console handover was necessary
  for these noninteractive guest commands and file copies.

Originals, transfer receipts, all comparisons, the rejected baseline diagnostic,
and `motion-review.json` are retained under
`artifacts/validation/xyz-displacement-cli-20261025-01/`.
Portable evidence: `artifacts/exports/xyz-cli-displacement-20261025-01.zip`.

This proves the observed same-build displacement agreement and CLI collection
path. It does not prove continuous tracking, speed, input causation, wall-clock
source freshness, a new restart case or patch recovery. Patch recovery and direct
in-game Computer Use remain deferred. Next practical use: reuse this CLI
collection path for another bounded observation; avoid rebuilding transfer tools.
