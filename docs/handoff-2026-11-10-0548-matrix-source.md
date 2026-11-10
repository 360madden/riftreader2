# RR2 short handoff — 2026-11-10 05:48 EST

## Verified environment and scope
- Workbridge target: **AMD-DESKTOP**, authoritative checkout `C:\work\riftreader2`, branch `codex/modular-foundation`.
- The RIFT game was reported offline. **No live key input or controller mutation performed.** Lab2 controller remains in an uncertain identity/release state; no stage/restart/STOP-clear until ownership and release are verified.
- Preserve unrelated untracked peer files: `scripts/project_current_native_energy_variants.py`, `scripts/rank_native_anchor_candidates.py`, `tests/test_rank_native_anchor_candidates.py`.
- Current exact RIFT x64 EXE SHA: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. All addresses below are RVAs for that build.

## This block: committed/pushed milestones
1. `18c7bf5` documents the matrix setter `0x6869D0` (36-byte `RDX` source to actor `RCX+0x3EC..0x40C`, tail jump to compositor `0x688F20`) and a second likely initializer at `0x6754D2..0x6754F4`.
2. `fa03256` identifies direct call `0x5DD412` and source-builder `0x11439D0`; fixes C# `analyze-turn-probe --help` to show `primary|secondary|actor|model` and adds a regression test. **11/11 targeted .NET tests passed**. Both commits pushed to origin.
3. AMD-DESKTOP PATH/Pillow verified: `where python` resolves `C:\Python314\python.exe` before WindowsApps alias; `C:\Python314\python.exe` imports Pillow **13.0.0** cleanly. No PATH changes needed.

## Useful static source chain
- `0x5DD3CE` neighborhood obtains the component through selector metadata at `module+0x2F58490` (historical slot17).
- `0x5DD3EC..0x5DD405` passes three floats (`[rbx+0x88]`, `[rsp+0x44]`, `[rsp+0x40]`) to matrix builder `0x11439D0`; builder creates 3 rotation-style 3×3 matrices and multiplies via `0x676B40` twice.
- `0x826A70` computes two stack scalars using object `+0x378` and `+0x88`, with arithmetic/clamping; direct units and axis identities are unknown.
- `0x5DD40A..0x5DD412` sends built 36-byte matrix to setter `0x6869D0`, then compositor `0x688F20` uses `(actor+0x398) × (actor+0x3EC)` to write render `+0xA0`.
- Full file-backed text direct E8/E9 scan identified this one independently decoded call; preferred-VA absolute pointer search in file-backed rdata/data found none. This is not a proof of no indirect callers.
- Enclosing `.pdata` function `0x5DD160..0x5DD446` sets `RBX=RCX` at `0x5DD18D`. This incoming entity-associated object (entity pointer at +0x10) holds scalar `+0x88`. It conditionally copies `+0x8C` to target `+0x90` then smooths/clamps `+0x88` toward `+0x90` using `+0x94`; source object class and camera-vs-actor significance remain unknown.
- **Do not claim body-heading** from these fields yet; current values may be cached, and there has been no controlled A-turn visual/heading correlation. Joey explicitly permits cached/scaffolding sources while prototyping if appropriately labeled.

## Next practical work
1. Offline trace `RBX` ownership and `+0x88` scalar to distinguish actor-vs-camera, ideally a stable direct candidate to read. Keep static scope bounded.
2. When game/controller recovers: bracket one short A turn with fresh pre/post actor and model candidates, an exact controller key-down/up receipt, and hash-pinned screenshots. Mark user typing as contamination. Release/STOP must be unambiguously verified.
3. Run `analyze-turn-probe --matrix actor` and/or `--matrix model`, plus `scripts/compare_turn_frames.py`; treat outputs as candidate evidence for prototype behavior. Preserve the hybrid Lua addon + external .NET 10 C# reader/controller architecture until native-only can replace it on evidence.
4. Existing offline release available but **not deployed**: `artifacts/native-actor-pose-release-20261110-0536/publish/RiftReader2.Live.exe`, SHA `1A3BA9D3CDAF163C59DE0E75A2E3B007190F0F37B80CBFCBCB488B9F9C5DA9EA`. Release tests previously 1032/1032.

Reference: `docs/reference/native-current-coordinate-code-map.md`. Avoid broad anti-cheat speculation. Stay results-first.
