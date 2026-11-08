# Current-build position component vptr bridge — retained two-lab discovery

**Evidence time:** 2026-11-08 06:51 UTC (01:51 EST). **Scope:** offline read-only replay of historical current-build Lab1/Lab2 snapshots; no new native/VM/game read. **Authoritative checkout:** `C:\work\riftreader2` on AMD-DESKTOP.

## Result

Across **49/49** successful, source-hash-verified **272-byte position-component chunks** spanning **seven historical process epochs**, the first little-endian QWORD was exactly `moduleBase + 0x26B4FB0`. As a distinct component-class control, **18/18** successful, source-hash-verified **72-byte health chunks** yielded `moduleBase + 0x26AFBA0`. Both apply ONLY to executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.

This directly bridges the previously selector-resolved position-component object to the **candidate .rdata dispatch-table** at RVA `0x26B4FB0` in retained epochs; the health/control vptr is different. The Ghidra V8 routine `0x698170` **allocates and initializes an object** of 0x118 bytes with this vptr; it is a **factory/clone-like allocator candidate**, NOT proven an in-place constructor or virtual constructor. The method-index meaning of `+0x90` (which contains its address in .rdata) remains unknown.

| Cohort | Matching vptr RVA | Verified chunks | Explicit matching `review.components` owner |
|---|---|---:|---:|
| Position component, 272 bytes | `0x26B4FB0` | **49/49** | **42/49** |
| Health component, 72 bytes (negative control) | `0x26AFBA0` | **18/18** | **17/18** |

**Verification precision:** Every reported chunk passed successful-read, exact byte-count, Base64 decode and declared raw-byte SHA-256; all 49 reports had status complete and matched the pinned executable SHA. **48/49** full `component-values.json` file SHA-256 values were independently checked against their sibling `review.json` `evidence` digest, with matching PID/start/executable/module identity. The one Lab2 `6391975fd6ff4781afcbd924eeadc4b2` directory lacks `review.json`; its full JSON SHA was computed as `D9E93F32E7DEE3B0D42EB376F1025F5923F7F86CF9DD75F859509E8D04C62B56`, but has no sibling expected digest. Seven position and one health chunks lacked a directly comparable `review.components` key/review; do **not** claim their owner pointer was freshly revalidated by this replay. No owner mismatch was observed among keys available.

## Two exact examples

| Lab historical epoch | Position component | Module base | Captured vptr (module+RVA) | Source hashes |
|---|---|---|---|---|
| Lab1 PID 8164, start ticks `639290507142219120` | `0x23D011C0150` | `0x7FF7698E0000` | `0x7FF76BF94FB0` | JSON `E5DBE57BBE80B9D6D03228630CBD5E96DF80975B5263D01CDD6B91FDA0B26971`; raw chunk `26894F84F389118C2EC8CA972032ED00C956BE7AD7BFA4107708A41813C8AD6E` |
| Lab2 PID 7012, start ticks `639290507554340644` | `0x2187FE4F400` | `0x7FF678A10000` | `0x7FF67B0C4FB0` | JSON `FE34732A410CDF3098635F42563F8F5B43757A7AE4981783F8992C2ED6B41253`; raw chunk `4B687DE14028B1616339315DECACDEA8CF2B66DBCC9B823E3D13FEF549C212CC` |

Both anchors have sibling source-hashed owner reviews: Lab1 `B24487B1857502D0D6DA3688A99AEB7344B46478B6B1D26D05D9FCC18035CF32`; Lab2 `761BCC15D1F66E7EFB18EFA13F42DBC995D8E39D8BEDA7517D5E61E1BD72D114`. The historical self-key/selector component-chain and 49-chunk cohorts were previously documented in `docs/reference/current-native-xyz-writer-evidence.md`, source SHA `B29C08A611C74A452270274C0FCFDAA85B8BF389DA894720771AD075BEB968D8`.

## Exact static corroboration and reproducibility

- Retained V8 Ghidra pseudocode `artifacts/rea/ghidra-v8-pseudocode.txt` SHA `D2EDA069932B441F59520CE51C3904B21FF84AD92E088EAC333F50E5ACDC7961` shows the 0x118-byte allocator sets vptr to `0x26B4FB0`; its slot0 thunk resolves a **generic `Entity::Component`** static type descriptor, not a player-specific class name.
- `docs/handoff-2026-11-08-constructor-vtable-bridge-0643z.md` SHA `B356F8C9262B5E60F76CC7E5899FCB6FC9C526E31047351F720865C268199BF0` records the exact imported-Ghidra .rdata table bytes. That imported SHA guard was **not a fresh installed-PE rehash**.
- Host-only one-off Python replay via Workbridge command IDs `rr2-xyzprov-owner-vptr-twoepoch-20261108-01` (two anchors), `rr2-xyzprov-vtable-cohort-20261108-01` (49/18 raw cohort) and final `rr2-xyzprov-vtable-cohort-fullhash-20261108-02` (48 full JSON expected SHA/identity matches and explicit review-pointer count), all **PASS/exit 0**. The audit was sent as inline Python `-c`, not a saved versioned script; no separate script file SHA is claimed. Historical raw files under `artifacts/native-unit-manager/lab{1,2}/*/component-values.json` were unmodified.

Historical epochs: Lab1 `1952/639294190379863806`, `7164/639294897866244204`, `8164/639290507142219120`, `11672/639296016581575957`; Lab2 `7012/639290507554340644`, `9752/639294897826627677`, `11572/639293038821710082`.

## Practical next action and limits

Use `moduleBase + 0x26B4FB0` as a **read-only secondary vptr identity candidate** beside the existing fresh self-key, entity table, selector, component backlink and repeated anchors. Require exact build and process epoch, and report mismatch/unavailable rather than guessing a different type or zero. The historical matching vptr does **not** establish current-process instance/owner, active allocator/callback invocation, exclusive native-read access, passive XYZ freshness, changed-state movement, world frame or full-game restart durability. No new deployments or lab/controller input were performed.

## Exact installed PE instruction corroboration (2026-11-08 06:54 UTC)

The host-only offline byte extraction read the installed `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe` (**60,493,640 bytes**) and required a fresh full-file SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` before mapping fixed executable windows. Workbridge job `rr2-agent-xref-exact-pe-vptr-raw-review-20261108-01` **PASS/exit 0**, untruncated with `RR2_EXACT_PE_VPTR_BOUNDED_COMPLETE`; examined only `0x698170..0x69826F` (256 bytes) and `0x697F20..0x697F9F` (128 bytes), with no live or file writes.

| Role | LEA RVA / bytes | Resolved static VA | Following store RVA / bytes |
|---|---|---|---|
| Factory/clone-like allocator | `0x698199` / `48 8D 05 10 CE 01 02` | `0x1426B4FB0` | `0x6981A0` / `48 89 03` — `MOV [RBX],RAX` |
| Deleting destructor, derived vptr | `0x697F2A` / `48 8D 05 7F D0 01 02` | `0x1426B4FB0` | `0x697F34` / `48 89 01` — `MOV [RCX],RAX` (after `MOV RBX,RCX`) |
| Deleting destructor, base vptr switch | `0x697F4E` / `48 8D 05 6B 67 01 02` | `0x1426AE6C0` | `0x697F55` / `48 89 03` — `MOV [RBX],RAX` |

These exact RIP-relative LEA-plus-store instruction bytes independently corroborate the decompiler's vptr initialization/base switch and the historical component-header cohort. They **do not** prove slot-18 dispatch, a conventional/virtual constructor, a current-process owner, or fresh XYZ. The byte extraction was inline `Python -c`, not a committed script; it is a fresh installed-PE rehash, unlike imported Ghidra SHA metadata.
