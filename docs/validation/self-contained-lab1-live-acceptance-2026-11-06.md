# Lab 1 self-contained RR2R1 live acceptance — 2026-11-06

**Result: PASS for the RR2-owned Lua/API reference on Lab 1.** This is a
bounded source/transport acceptance, **not** a qualification of native field
semantics, changed-state movement, sustained freshness, or game-restart recovery.
The old `RiftReader` checkout and `RiftReaderApiProbe` were not used by the
current acquisition or inspectors.

## Deployment and exact live identity

- Reviewed seven-file `addon/RiftReader2` package version `0.2.0` matched the
  installed Lab 1 source hashes before acceptance and again afterward. The
  post-acceptance check passed with zero issues or updates:
  `artifacts/addon-sync/20261106T235511Z-622e7872/lab1-result.json`.
- The old `RiftReaderApiProbe/RiftAddon.toc` was independently absent in both
  guest installation paths before reload, with the disabled copy present and
  SHA-256 `71FF7C66626C1740B22DEA8AACFAAED20CBE1C83AF69DB73A42ADC352276269C`.
  The pre-reload two-guest verification is recorded by Workbridge job
  `rr2-old-probe-disabled-verify-20261106-a`. Lab 2 **disk parity is not live
  acceptance**, because Lab 2 did not receive a UI reload or nonce bind.
- Lab 1 RIFT executable SHA-256:
  `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`;
  game PID `11672`, start ticks `639296016581575957`; VM PID `48444`, VNC
  port `5905`, VM log epoch `2026-11-05T15:31:05.498Z`. Process and VM
  identities matched before and after both reviewed commands.

## Controlled reload and bind

1. Verified the managed controller was idle and its navigation resource had
   no holder or pending requests. Released the **exact** controller generation
   via its `stop.request`, verified process exit and the console mutex free.
   The first focus-only title-bar click left Windows Terminal covering RIFT;
   a newly reviewed Terminal minimize click exposed the game. No app closed.
2. Used screenshot-hash-bound, under-60-second console reviews to open empty
   RIFT chat and send **one** `/reloadui`. Input and key release succeeded at
   `2026-11-06T23:42:47Z`; a retained screenshot showed the game UI loading at
   46%, confirming a real UI reload without a game process restart:
   `artifacts/standalone-acceptance/lab1-reload-command-review-20261106-b/`.
3. After loading, closed LuaPadModern's startup window and hid the RR2 Casting
   panel with independently screenshot-reviewed clicks. Reopened clean chat
   using the reviewed console helper, then sent
   `/rr2guide bind lab1 2281d2f18781169f119abfd88c584aeb` at
   `2026-11-06T23:49:05Z` with verified key release. The RIFT chat visibly
   acknowledged: `RiftReader2: Bound lab1; manual feedback only.` Evidence:
   `artifacts/standalone-acceptance/lab1-bind-rr2r1-20261106-b/`.
4. Restored the on-demand managed controller. Final status: host connected,
   coordination ready, exclusive console held, guest disarmed/idle, zero desktop
   inputs down, and exact RIFT foreground true. No VM or game restart.

## Independent two-run reference acceptance

- Reader: RR2-owned published `RiftReader2.Live.exe`, 117,270,368 bytes,
  reviewed SHA-256
  `1A97D39BB0769E450B80E9EE0D802447713195AA682C0858CEB6F96F114319F6`.
  The source contains `RR2R1|`; the old deployed reader binary was rejected
  as a current reference prerequisite.
- `scripts/capture_current_typed_reference.py` scanned **twice** with the
  explicit `RR2R1|` marker and fresh nonce, eight saved snapshots per run.
  The original archive's SHA-256 was verified, and both runs were recovered
  unchanged. No game input was sent during acquisition. Evidence:
  `artifacts/native-current-reference/runs/lab1/cc85d8178cdd4c6ba944caf23cae240d/`.
- Strict `.NET` inspection through `scripts.assess_typed_wire_runs`:
  **64/64 cross-run pairings advanced within a declared 15-second window**,
  zero blocked or unavailable. Selected pair `capture-03-to-capture-07.json`:
  player `u035400012FA2D678`, protocol `RR2R1`, addon `RiftReader2` version
  `0.2.0`, matching nonce/epoch `1`/process/build, sequence **413 → 431**,
  source frame time **4297.927734375 → 4307.123046875** (+9.1953125),
  selected snapshot gap **9.474637 s**, run-envelope gap **8.760116 s**.
  Evidence: `artifacts/validation/rr2r1-lab1-live-assessment-20261106-b/summary.json`.
- Independent Python `inspect_typed_resource.py` on the selected snapshots
  verified the same nonce, player and epoch. Mana and maximum both reported
  **3980/3980** in both runs; the player `power` field correctly remained
  `unavailable`. Its reports are `mana_before.json`, `mana_after.json`, and
  `power_after.json` in that same assessment directory. The selected RR2R1
  player fields also reported HP **9010/9010** and stationary XYZ
  `(7450.2998046875, 864.3099975585938, 2984.559814453125)`.

## Scope and follow-up

**Established:** Lab 1 can load the RR2-owned addon with the legacy probe's
manifest disabled, bind a fresh RR2 nonce, capture advancing RR2R1 source
frames, and inspect them strictly using RR2-owned .NET and Python consumers.
The independent suite does **not** establish live semantic qualification of
native HP/Mana/XYZ, changed-state responsiveness, 480-second continuity, or
recovery after a full RIFT process restart.

**Still pending:** Physical PC and Lab 2 require separate loaded-addon/live
acceptance; no Lab 2 game input or reload was performed. Do not remove or
delete legacy historical evidence. Existing old XYZ live workflow's implicit
legacy-protocol route was independently retired in commit `f034fc4`; its
native movement profile remains obsolete for the current game build. No RRE
or REA source was changed. The experimental remote receiver-pin branch must
not be merged into the Windows tree: the installed Windows receiver source
hash already matches its correct existing runtime pin.
