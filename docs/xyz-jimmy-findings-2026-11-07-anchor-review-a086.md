# Jimmy RR2 stable-navigation-anchor review — November 7, 2026 EST

**Scope:** independent, read-only analysis of retained RR2 source and evidence. No guest/VM/game/controller/receiver access, game input, reload, bind, native capture, source edit, status edit or commit was performed. Saturday Discovery Effort remains the implementation/integration owner; this report is a separate review artifact. The repository was observed on AMD-DESKTOP, `C:\work\riftreader2`, branch `codex/modular-foundation`. Current XYZ source/test edits were already in progress and were left untouched.

## Verdict

**The current build has a practical, dynamically resolved player-to-position owner chain, but NOT a proven passive-fresh navigation source or a validated same-build full-game-restart locator.** Preserve the existing reader and make the next experiment discriminate a refreshed cache from a truly independent changing position source. Do not conduct broad scans or use the obsolete older-build pointer profile.

## Exact-build owner anchors

The following are *module-relative locating recipes*, not persisted absolute pointers. They apply to game executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8` only.

| Level | Current-build route | Qualification |
| --- | --- | --- |
| Game epoch | Fresh unique `rift_x64` PID/start, module base, module size, exact on-disk executable SHA | Enforced by existing source; loaded module bytes not independently hashed |
| Player key | `[module+0x33623E0]` player-system singleton, `QWORD(+0x360)` self key | Native parser/code path decoded; re-read each acquisition |
| Entity manager | `[module+0x33624A8]`, then manager `+0x50` identity table and bounded key/bucket lookup | Code-derived; observed in both labs on historical process epochs |
| Position owner | Unit entity `+0x18` selector vector; dynamic signed component-index metadata at `module+0x2F588A0`; entity `+0x78` component table | Existing reader resolves each sample and brackets anchors; historical index 34/slot 6 must not be hardcoded |
| Cached XYZ | Resolved position-component `+0x48/+0x4C/+0x50` float32 | Readable candidate; explicit refresh function makes passive freshness unknown |
| Cached rotation | Same component matrices `+0x60..+0x83` and `+0x94..+0xB7` | Structural Y-rotation descriptors, not accepted body-facing angles |
| Upstream source | Refresh `0x6996C0` may resolve through `0x612EE0/0x6126F0` to source `+0xF8/+0xFC/+0x100`; contiguous matrix at source `+0xD4..+0xF7` | Static candidate only; source type, player ownership and ability to advance without an API query unresolved |

The old build SHA `7C356C9D...`, player root `0x32E0200` and player XYZ `+0x320/+0x324/+0x328` do **not** apply to the current SHA. ASLR and heap pointers require fresh module rebasing and full chain resolution after every process restart. The existing `CurrentBuildPlayerLookup.Resolve` already bounds pointers and hash chains, re-reads owner anchors and rejects changes; consecutive equal reads are non-atomic and cannot exclude ABA.

**Root cause of the freshness uncertainty:** `Inspect.Unit.Detail` invokes `0x698460`, which invokes `0x6996C0`; that function may update the position component's XYZ cache. Thus an API-first/native-after agreement can be a circular cache-refresh effect. Source `+0xF8` is not yet a trusted world-position owner. The orientation refresh also has absent-provider/cached fallback; advancing a shared clock or observing a plausible matrix does not prove live facing. Do not take dimension-item Lua `yaw/pitch/roll` keys as avatar heading.

## Independently rechecked retained observations

- Lab1 retained current-build reader report: `artifacts/native-current-sampler-20261105/runs/lab1/16afd9a6486a450e92d174555e510fb6/samples.json`, SHA-256 `98AA5218CF7995CBEEB2D76A29C435A40275850DFE75BBA6409740917CA7E229`; summary SHA-256 `E98033BFECFB32B798686840CFF01D44B845853B0FE1BBDABC854BEC4F9B5864`.
- The **15/15** samples (6.997 s span; max read 90.6729 ms; max start gap 523.5209 ms) all reported XYZ `7450.3677, 864.3101, 2984.6113` for PID 6820/start ticks 639296903905448486. That proves acquisition cadence, not a moving or passively fresh source.
- This retained reader binary SHA `B8A725E6A9CE663C36CB836681ED660261B07FDA4118A0167262E92131B2373E` emitted **no per-observation unit key**. Its `summary.json` honestly says `unitIdentityStatus=unavailable-in-source-report`. Current *uncommitted* `CurrentBuildPositionSampleCommand.cs` source already contains per-row `UnitKey/UnitIdCandidate`; do not project those new fields backward onto the old binary/report. The Saturday lane owns publishing/integration of its changes.
- RR2R1 Lab1 live addon/reference acceptance previously passed **64/64** advancing native-reference comparisons, but receiver *continuous* freshness remains unverified. Lab2/physical loaded-source acceptance is pending. The earlier Lab2 fast-region sequence advanced while a whole-process scan stopped; full-scan stale is not proof that the scoped producer stopped. Historical 480-second passes and old nonces do not become current readiness.
- A separate RRE SC628 Lab2 API XYZ record is useful historical comparison, not a simultaneous same-player/current-epoch acceptance for this Lab1 sample. The RRE repository and its lab-window owner remain separate.

## Smallest causal test — design only; root-owned execution

1. **Offline preflight:** Keep the current-build read-only sampler. Preserve a per-observation exact source/report hash, process ID/start/build/module identity, resolved player key, component-selector route and start/end monotonic times. When new fields are integrated, ensure they are actually present in the *published hash-pinned binary/report*, rather than assuming current source equals the guest binary. Treat missing player/world/zone/nonce as explicit unavailable; no cached success.
2. **API-quiet native baseline:** In a newly authorized, fresh process/epoch and with current source/owner admitted, acquire native baseline samples **before** any deliberate `Inspect.Unit.Detail` query. Observe whether the owner's cached XYZ and any upstream source values advance on their own. Existing addon polling may itself invoke that API, so an interval is not truly API-quiet unless the root first proves the applicable producer/caller activity; do not stop/reload anything merely to create quiet.
3. **API-refresh control:** Deliberately take an independently recorded, same-player/nonce/epoch RR2R1 API sample and then native-after sample. If the cache moves only on this query while the upstream changes differently, label the cached path **API-influenced**, not passive native telemetry. Compare ordinary finite coordinates after the API's documented hundredth quantization and bound the acquisition skew.
4. **Causal motion discriminator:** Only in a separately admitted root-owned reviewed finite-motion window, capture native-before **ahead of the next API query**, one small movement or stationary turn with guaranteed STOP/key release, native-after-release **ahead of another API query**, and an independently advancing same-player API/UI or visual endpoint. Bracket exact PID/start/build/key/component and monotonic windows; do not use the stale prior Lab2 nonce. Movement must change the independently identified position source coherently; a stationary turn must alter a player-owned facing candidate while XYZ remains approximately constant. Reject gaps, owner switches, stale timestamps and unconfirmed key release.
5. **Durability gate:** Only after the above source meaning is supported, run a separately authorized complete RIFT exit and fresh process launch on the **same** exact SHA; reacquire module base, self key, manager, entity, selector and component without old absolute addresses. Demonstrate independent changed-state response again. A UI reload or reader restart is not this gate. Patch/update qualification remains deferred.

**Next useful step:** The owner should first use the existing exact-SHA lookup to produce a fresh *source-qualified* per-row identity/XYZ receipt and examine the cache refresh ordering. To escape the circularity, statically identify the canonical owner of `0x6126F0`'s resolved source and its writer, then use a narrow native-before/API/native-after discriminator—not a new scanner. Until then, navigation should consume these as candidate-only coordinates and must not claim autonomous feedback or body yaw.

## Sources inspected (current bytes)

- `src/RiftReader2.Live/CurrentBuildPlayerLookup.cs`: SHA-256 `80146294F907D13FD652D1301396737B87D71D61F1AA8D9CEB390F24A22C13E7`
- `src/RiftReader2.Live/CurrentBuildPositionSampleCommand.cs`: SHA-256 `6AD3660C6690BF2294DC283B58F9C43C4C6E2EDCE4D5128FFB1EB490C4C86B26`
- `src/RiftReader2.Live/CurrentBuildOrientationCandidateReader.cs`: SHA-256 `78B3A8E9919D988F0CEACA3E046A07063C649A75F04058D21EFE3EBF5D2ECDFC`
- `scripts/sample_current_native_xyz.py`: SHA-256 `8F5A71C2E942A327F17060AC634614A5D8D26BFCEA89AFBEDEE6F8B24BA1BE74`
- `docs/reference/native-current-coordinate-code-map.md`: SHA-256 `DA9AB7E2C34A30B2E80D6107873195FB8FD50A1ABB32746769ED34113431AF86`
- `docs/reference/current-native-position-sampling.md`: SHA-256 `32E5A8D10727F012055CC6B9AB2A2C868D910B1744A0FC95CD2356529249DB4E`
- `docs/validation/lab2-fast-vs-full-forensics-2026-11-05.md`: SHA-256 `A470E9471DCA63965519D57316F4318C777D284D058828315FA8D36BC63F12D3`
- `docs/reference/self-contained-api-reference.md`: SHA-256 `F1A09E85CDE5132F07461E82918312CFAF1D2A06EE96D334EE62DB54BD485BB2`

**Coordination:** This report has been written to the shared checkout only. It does not claim a direct cross-chat message, a live action, a successful motion test, code integration, or a Git commit.

## Continuation: API-quiet control is blocked by the RR2 baseline producer

**Source finding, not a runtime capture:** `addon/RiftReader2/main.lua` constructs the regular Producer with `intervalSeconds = 0.5` (line 4), invokes `producer:Update()` inside the unconditional update callback (line 113), and attaches that callback to `Event.System.Update.Begin` (lines 236-245). This is **independent of `live:SessionId()`**; the nonce gate applies to the separate RR2R1 reference producer (lines 54-59). `addon/RiftReader2/producer.lua` calls `acquire(self.Api)` after the normal game-clock interval (lines 230-238); `acquire` calls `Inspect.Unit.Detail` (lines 92-95, 117-143). `reference.lua` has the analogous detail call but its `UpdateCore` returns when no session ID (lines 228-231).

**Consequence:** An *unbound* RR2 reader is not an API-quiet condition while the ordinary addon producer is loaded and ticking. Source flow predicts a query approximately each 0.5 s of advancing frame time under healthy conditions; actual runtime invocations and other addons' API calls are not measured. Native cache freshness observed in such a session cannot be called addon-independent without controlling or observing the callers. Merely waiting, unbinding the RR2R1 nonce, or relying on a stationary sample is insufficient.

**Adjusted smallest test:** Root first establishes a supported, explicitly authorized way to know whether any `Inspect.Unit.Detail` producer is active in the observation window, including the ordinary RR2 producer and potentially other addons. If a genuinely query-quiet interval cannot be established without a newly authorized addon intervention, record **blocked: API-quiet control unavailable**; continue the existing read-only upstream source/writer trace without claiming passive freshness. Keep native-before / explicit API / native-after as an API-influence control regardless. Do not disable, reload or alter any addon from this review lane.

Additional current source fingerprints: `addon/RiftReader2/main.lua` SHA-256 `A0DA4E537DDC84CAC08E77FCEE708078FE8203670CDD439F2F422F73B668DE03`; `addon/RiftReader2/producer.lua` SHA-256 `BA565468BDA7FC054186D1BB1F15B504620565EEB448818451FFA346887DC779`; `addon/RiftReader2/reference.lua` SHA-256 `C4E0F8BE55DB7356948B0ABD1A07AB09F1B3EADF87ED4AAE8C130A37FB2738D7`.

## Continuation: branch-admitted upstream tracing, not a fixed resolver assumption

The retained exact-build code map reports that `0x6996C0` tests position-component `QWORD(+0x100)` and `BYTE(+0x108)`; when both are zero, the accessor can return without consulting the pose provider. Both were zero in historical Lab2 samples; optional provider selector indexes 22 and 46 were also `0xFF`. Consequently the `0x612EE0 → 0x6126F0 → source+0xF8` path is **conditional and may not be active for the currently observed self entity**. This qualifies the earlier proposed source trace; it must not be treated as the single canonical answer.

**Sharper next step:** With already-retained component bytes, classify the exact guard/selector branch for each sample and determine which paths are reachable; use the retained exact-PE code to trace **actual writers** to primary `component+0x48..+0x50` and secondary `+0x88..+0x90` for that branch. Only then propose a small fresh read that binds a candidate writer/source back to player key, component and process epoch. If guards are missing in a retained report, label branch **unavailable** rather than infer from a zero coordinate or assume the inactive resolver. No new live read or PE extraction was launched by this review.

## Continuation: original retained x64 instructions recovered and independently decoded

Read-only Workbridge job records were recovered with `status=passed`, `exitCode=0`, `outputTruncated=false`: `rr2-serialized-native-xyz-refresh-full-20261031-01`, `rr2-serialized-native-upstream-resolver-20261031-01`, `rr2-serialized-native-upstream-xyz-20261031-01` and `rr2-serialized-native-xyz-accessor-20261031-01`. Their retained byte slices were disassembled locally with GNU `objdump` from anonymous in-memory bytes. No installed PE reread, live game process, VM or controller operation was performed. The slices are partial functions, not an exhaustive writer search.

The independently decoded `0x6996C0` slice gives these **conditional cache writes**:

| Branch | Required entry/selector evidence | Explicit writes within retained slice |
| --- | --- | --- |
| Handle-present branch | `QWORD(positionComponent+0x100) != 0`; manager lookup `0x6A0040` and signed selector metadata at **module RVA `0x2F57918`** choose an upstream component; call `0x612EE0` | `0x699855` writes first two float32 lanes to `position+0x48`; `0x699859` writes third to `+0x50` only after inequality; `0x6998A4..0x6998B2` copy to secondary `+0x88..+0x90` |
| Alternate-flag branch | Handle zero, `BYTE(positionComponent+0x108) != 0`; owner entity `position+0x10`, same selector **module RVA `0x2F57918`**, component present and `0x6136B0` accepts; call `0x612B50` | `0x699991` writes first two float32 lanes to `position+0x48`, `0x699999` writes third to `+0x50`; `0x6999C7/0x6999D2` update secondary `+0x88/+0x90` |

That newly isolated **source-selector metadata RVA `0x2F57918` is distinct** from the canonical position-component selector `0x2F588A0`. The retained source bytes do not report its current runtime selector value or prove the selected upstream component is present in either lab. The second branch also calls pose/matrix helper `0x612960`; it cannot be interpreted as proven body facing. For the previously reported Lab2 `+0x100=0` and `+0x108=0`, these two depicted refresh branches are **ineligible**, so these instructions alone do not explain how position changes in that state. Other writers, engine update paths or historical state differences remain open. Do not elevate these conditional writes into a canonical producer claim.

**Precise follow-up for the root:** First check whether the current player component's branch guards and module selector `0x2F57918` can be resolved from already admitted source bytes. If unavailable, retain an explicit missing input. Use exact-build bounded static cross-references to seek **other writers of the active player-owned component's XYZ fields** before scheduling a new live capture. Any live discriminator must reacquire the self key, component owner, game SHA/process epoch and independent changed-state evidence; do not execute game getters or infer freshness from `Inspect.Unit.Detail` output.

## Continuation: current source-selector bytes missing from retained root requests

Independently inspected `artifacts/native-unit-manager/lab1/5a654fbadb324803a6bba83520329d46/roots-request.json` (SHA-256 `86D116A9EB90F5303C31FA67CE72DDE21260F2343C1B30F5FF04323F6A3F96C4`) and its captured `roots.json` (SHA-256 `1DD443923D8B44BBFF1D4FA4775EFF7F4667E57F517EC11F3EB5D5967175DC67`). The four explicitly captured root RVAs were `0x33624A8`, `0x33623E0`, `0x2F588A0` and `0x2F57850`. Lab2's analogous `roots.json` SHA is `99837EC442016EB9FC8C13AEFEE7064A3D4E29DB06064415969B608B910D4D64`. None of those 4-byte root ranges covers `0x2F57918`; no current value for the source selector can be inferred from them. A bounded text search of 1,832 ignored native-unit-manager JSON files found no explicit `2F57918` reference. That search does not rule out unnamed raw-byte coverage elsewhere.

**Minimal requested future observation (root-owned, no action implied here):** under a newly acquired exact game PID/start/build and player self-key, read just the source selector DWORD at **module+`0x2F57918`**, the player position component's branch fields `QWORD(+0x100)` and `BYTE(+0x108)`, and the applicable current entity/component selector table bytes. Bracket all with the established owner and process-epoch rereads and preserve the raw request/source hashes. If no branch admits a source component, return **unavailable**, then prioritize a source-hashed static trace of external writers to the player-owned cache. Do not use the historical position index `34` as a substitute for the missing source index, and do not initiate a lab operation from this report.

## Correction: source-selector bytes **are** preserved in broader module snapshots

The preceding section's missing-root value finding is limited to the *small roots-request.json captures*. A subsequent discovery located two separate, retained, exact-build module .data snapshots covering module RVA **0x2F56000** for 0xD000 bytes; this range includes source-selector DWORD **module+0x2F57918**. The broad snapshots were already saved, so no new game process read, capture, reload, VM or controller input was required. An in-memory read-only Python check verified each whole JSON snapshot SHA, raw chunk SHA, target PID/start epoch and the signed four-byte value.

| Lab and historical epoch | Retained module snapshot / SHA-256 | Source selector at RVA 0x2F57918 |
| --- | --- | --- |
| Lab1 PID **8164**, start **639290507142219120** | artifacts/native-module-roots/lab1/31698603c86a445b8736a2435caf6a92/snapshot.json — **8A42DF19375EBF6B139B61244C4B08909A9D986C67F7B5940BA7818D6EA10E91** | Signed index **46**; raw DWORD **0x0000002E** |
| Lab2 PID **7012**, start **639290507554340644** | artifacts/native-module-roots/lab2/6adb062aee0843c98c7ea804cb2c86cb/snapshot.json — **74651FA7937E7DB12CBCBC3E4605B2B795285F47E034386D4B139CB8A5F654C9** | Signed index **46**; raw DWORD **0x0000002E** |

Verified raw chunks: Lab1 start **0x7ff76c837000**, SHA **5A70B87E59E244A7525C44013734037984D528F5DA1F23672547EB7A72EE4B32**; Lab2 start **0x7ff67b967000**, SHA **50EAF00B4D90146227B85CB112178FBA67202E1F40EF2E8DEB98B20499C843C3**.

Independently checked the already-retained *self entity* component-selector bytes. Lab1 entity artifact artifacts/native-unit-manager/lab1/5a654fbadb324803a6bba83520329d46/entity.json has SHA **EA129236876631487F4AE3E937C3FF5931E20F0755EED6DD0C02811C5EAB088E**; Lab2 artifacts/native-unit-manager/lab2/a4e8474dbfef4a1490b7cee6655e46c8/entity.json has SHA **1DFB830739E6F305F6B62CCDA03AF9669EE65ECF3B79CA8C12597C92B6882B48**. In both entity vectors, index **22→0xFF**, **30→17**, **34→6**, **46→0xFF**. Read-only jobs **rr2-jimmy-retained-source-selector-20261108-01** and **rr2-jimmy-retained-self-slot46-20261108-01** passed with exit code 0.

**Interpretation, historical-epoch only:** Selector **34** finds the self entity's cached position component at slot **6**; the source selector **46** finds **no component on that self entity** (0xFF). This disfavors the *self-entity alternate-flag* source branch in those historical epochs and aligns with its previously observed +0x108=0. It does not rule out the *handle-present* branch resolving through a **different entity**, other engine write sites, or a changed runtime epoch. The currently running game selector, guard values, player-source owner and passive XYZ freshness remain **unverified**. Never hardcode historical 46, 34 or slot 6 into the standalone reader. Root's next static step is to reconcile the retained guard bytes and exact-build branch-compatible writers; only then request the smallest fresh, identity-bracketed live discriminator if justified.

**Coordination:** This is a review finding for Saturday Discovery Effort, not an implementation claim or command to act on the live game.

## Independent historical-guard provenance: both optional refresh branches gated off

A separate read-only Jimmy guard audit verified the full source JSON hashes, raw component chunks, process epoch, component address and pointer ownership, rather than relying only on the prose code map:

| Historical source | Lab1 (PID 8164, start 639290507142219120) | Lab2 (PID 7012, start 639290507554340644) |
| --- | --- | --- |
| Position component base | **0x23D011C0150** | **0x2187FE4F400** |
| component-values.json SHA-256 | **E5DBE57BBE80B9D6D03228630CBD5E96DF80975B5263D01CDD6B91FDA0B26971** | **FE34732A410CDF3098635F42563F8F5B43757A7AE4981783F8992C2ED6B41253** |
| Retained raw chunk SHA-256 | **26894F84F389118C2EC8CA972032ED00C956BE7AD7BFA4107708A41813C8AD6E** | **4B687DE14028B1616339315DECACDEA8CF2B66DBCC9B823E3D13FEF549C212CC** |
| component-pointers.json SHA-256 | **78ADA33C6E004C44901BA11DBAD47606FDA49D021E8E4370858387A463952B89** | **E5CC26585330815647360E5AC9A0578DDB92E32E14B738FBA670775E5FB82C59** |
| QWORD(component+0x100) | **0** | **0** |
| BYTE(component+0x108) | **0** | **0** |
| Raw component+0x100..+0x10F | **all 16 bytes zero** | **all 16 bytes zero** |

Paths: Lab1 artifacts/native-unit-manager/lab1/5a654fbadb324803a6bba83520329d46/{component-values.json,component-pointers.json}; Lab2 artifacts/native-unit-manager/lab2/a4e8474dbfef4a1490b7cee6655e46c8/{component-values.json,component-pointers.json}. Independent passed read-only jobs: **rr2-jimmy-guard-audit-component-values-20261108-01** and **rr2-jimmy-guard-pointer-provenance-20261108-01**. Both pointer reports' first position pointer equaled the independently captured component base.

**Branch admissibility for these two historical captures:** The handle-present writer group at 0x699855..0x6998B2 requires a nonzero +0x100 handle; the alternate-flag group at 0x699991..0x6999D2 requires nonzero +0x108. **Neither branch is eligible here.** These write sites cannot establish autonomous player XYZ freshness for the sampled state. No direct current-live guard capture or proof of all possible engine write paths follows from this result. The next code-trace should prioritize other writers or determine whether values are simply cached and stationary.

## Expanded guard cohort: 26/26 branch-ineligible retained captures

Independent read-only verification job **rr2-jimmy-guard-cohort-provenance-20261108-01** passed, exit code 0, with no truncated output. It examined all admitted complete 272-byte historical position-component captures under artifacts/native-unit-manager/lab{1,2}/*/component-values.json. The verification checked corresponding first component-pointer provenance, matching captured base, process PID/start, exact game executable SHA **1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8**, whole JSON SHA and raw chunk SHA. Incomplete captures were excluded rather than interpreted as zeros; no mismatches or parse exceptions were reported among 26 valid matches.

| Retained cohort | Valid captures | Distinct historical process epochs | QWORD(+0x100)=0 and BYTE(+0x108)=0 |
| --- | --- | --- | --- |
| Lab1 | **7** | 3: PID 8164 / 1952 / 11672 | **7/7** |
| Lab2 | **19** | 3: PID 7012 / 11572 / 9752 | **19/19** |
| **Total** | **26** | **6** | **26/26** |

Exact retained 0x6996C0 disassembly further constrains the result: at **0x6996E7**, zero QWORD(+0x100) jumps to **0x699923**, whose zero BYTE(+0x108) jumps to **0x699A2A** (epilogue), bypassing both known primary/secondary XYZ stores. Therefore **none of the two previously isolated conditional writer branches of 0x6996C0 are eligible for these 26 snapshots**. That does not prove a complete enumeration of all engine writers, and does not establish present-day guard state or any motion response. More work on the conditional upstream +0xF8 source is a poor immediate priority unless a newly observed admissible branch supplies an actual provider.

The code map (docs/reference/native-current-coordinate-code-map.md, SHA **DA9AB7E2C34A30B2E80D6107873195FB8FD50A1ABB32746769ED34113431AF86**) distinguishes nearby functions: **0x698460** reads the primary XYZ cache after optional refresh; **0x698480** writes a shared-clock timestamp at +0xD4, not XYZ; **0x687320** copies secondary cache into actor+0x3BC, and **0x688F20** writes a downstream render transform at +0xC4. These are **not proven upstream primary cache writers**. Potential actor/world composition through 0x613800→0x687320 uses secondary XYZ plus actor translation fields +0x4F8/+0x770; it is only a structural *alternative candidate*, not a player coordinate proof, and could reflect animation/render/model transforms. No same-player changing actor-field receipt has been admitted.

## Latest coordinator-owned native reader results (independently rechecked)

The newer *published* .NET reader at artifacts/native-xyz-unit-20261107/publish/RiftReader2.Live.exe is SHA-256 **BE252929D846AA0BB696D003116AB9D8ACAA23E5D411D68F913A92CD08919A5E**. Both Lab1 reports have game PID **6820**, start ticks **639296903905448486**, game exact SHA **1935A05C...**, module base **140700754903040**, and sampled unit **u035400012FA2D678** (lossless key 239816685251647096) on every row. The 5/5 sample source SHA **FC9DC02D1692BECA28ACF9F7F7A8B492D2AEC04A23FB87CC4CFF4495A4009772** (summary SHA **361104039C2726A5598F5D0E6404B6455CCDC44C29F0A01B15D3C3D6CDACBDA5**) spanned **2.108 s**, maximum start gap 533.3391 ms, max read 98.2754 ms. The 30/30 source SHA **254A4E86B80612A22957B46AE2E162FF9FA776779253115861B3AD2818B4E4AD** (summary SHA **5E5A1E79B0C2FE471B2E14696E770BED54B278705F2BA9F8A1811C7677042DFB**) spanned **19.387 s**, max start gap 778.9411 ms, max read 375.6047 ms. All **35** sampled rows had identical candidate XYZ **7450.3677, 864.3101, 2984.6113**. Read-only independent receipt verification jobs **rr2-jimmy-receipts-5-30-readonly-20261108-01** and **rr2-jimmy-raw-receipts-fields-20261108-01** passed, exit code 0.

These newer receipts supersede the earlier B8 reader's lack of a source-reported per-row key: **sampled owner identity is now verified in the emitted data**, though uninterrupted ownership, independent coordinate freshness, deliberate motion, reader restart and full-game restart remain unqualified. Existing raw rows have UTC/monotonic acquisition times, XYZ, unit identity and a player-component-chain-anchored label, but lack an independently verified API call timestamp/nonce, provider branch guards, and controlled visual changed-state. A next controlled receipt should carry explicit phase markers **native-before / deliberate API query / native-after**, matched player/process/session, and a true/false/unavailable **API-quiet qualifier**; ordinary RR2 addon Detail polling means quiet cannot be assumed.

## Smallest reader hardening and operator-documentation fix for root

- CurrentBuildPositionSampleCommand.cs (observed SHA **6AD3660C6690BF2294DC283B58F9C43C4C6E2EDCE4D5128FFB1EB490C4C86B26**) **already reads a full 0x110-byte position component** during owned XYZ sampling. The root can expose candidate QWORD(+0x100), BYTE(+0x108) branch diagnostics **without another process memory read**, while bracketing guard changes before branch claims. Keep metadata explicitly diagnostic, not a position-provider promotion.
- CurrentBuildPairedPositionCandidateReader.cs (read-only observed SHA prefix **94D3E177**) checks position component +0x10 reverse owner backlink to entity; the simple standalone sampler lacks this extra check. Consider verifying then applying the same invariant to reject a recycled component; this is hardening, not a demonstrated bug. Epoch and anchor rereads are already implemented, but non-atomic ABA is still possible.
- Operator-doc mismatch: docs/reference/current-native-position-sampling.md (SHA **32E5A8D10727F012055CC6B9AB2A2C868D910B1744A0FC95CD2356529249DB4E**) still describes the old **B8A725...** reader, while current Python script and docs/reference/current-native-xyz-tracking.md point to **BE252929...**. Root owns the small documentation update.
- Keep the full-RIFT-process-restart acceptance gate and changed-state player navigation proof distinct from a reader restart, a UI reload, or static 5/5 / 30/30 passing cadence.

**This Jimmy lane edited only its own shared findings report and performed no live input, source edit, status edit, commit, controller/reload/bind or new process/PE capture.**

## Retained actor/render candidate availability check

The independent writer reviewer searched retained artifact directory names (no dedicated actor/render evidence directory found) and bounded text references across approximately **27,004 artifact JSON files**; no explicit admitted actor-render pose candidate or actor+0x4F8/render+0xC4 report was found. One narrower search timed out, so the search is **not an exhaustive absence proof**. The two examined historical component-values reports each contain exactly **one 272-byte position-component chunk**, and cannot cover actor+0x4F8/+0x770 or render+0xC4. Accordingly the actor/world composition route is a **code-only, unmeasured candidate**; do not label it a backup live player-position source. If future work needs it, root must first establish a bounded same-player actor pointer/epoch and obtain an explicitly scoped sample under its own live-test authority.

**Final Jimmy lane summary:** Verified two-lab historical source selector 46; verified self slot46 unavailable; independently verified 26/26 historical branch guards off; decoded direct control-flow exit and downstream-only known render paths; independently verified current pinned reader's 5/5 and 30/30 static same-unit receipts. **Still blocked:** qualified independently fresh player XYZ and full RIFT restart durability. Shared findings written for Saturday Discovery coordinator to integrate; no Git commit by Jimmy.

## Independent review of root's in-progress refresh-branch candidate reader

This review inspected the root-owned **untracked and concurrently mutable** file src/RiftReader2.Live/CurrentBuildPositionRefreshBranchCandidateReader.cs at SHA **09C81AD304D241E8AFB11763BE5A617414E540764D526232E6959B705A212DE4**, with corresponding tests at SHA **EB3AA7D6B0F0BD0C74B90658546D97297C563FAD66FAE8F8BBAF263B500B198E**. It did not edit or execute that source.

**Positive:** The new reader uses dynamic source-selector RVA 0x2F57918; distinguishes +0x100 handle-present and +0x108 self-flag branches; checks component+0x10 player-entity backlink; brackets successful raw inputs and invokes lookup.VerifyUnchanged; and does not promote discovered upstream slots to confirmed, live world-position telemetry.

**Three low-cost review findings for the implementation owner:**

1. **Partial-input branch classification:** At lines 77-97 the reader presently requires all of handle/flag/source-selector values before classification. If a verified handle is nonzero, handle-branch admission is already known even if the flag is unreadable. If a verified handle is zero and verified flag is zero, **inactive-both** is already known even if source-selector metadata is unavailable. Prefer ordered, branch-specific evidence gates and targeted partial-read tests; never claim active when an actually required guard is missing.
2. **Owner mismatch observability:** A failed self-entity backlink check raises InvalidDataException but lines 62-75 swallow it into a generic unavailable record. It is fail-closed, but hides the difference between a stale/reused owner and an optional missing field. Return a distinct owner-mismatch reason or an explicit fail-closed validation error; do not reinterpret as a valid source.
3. **Lossless key at JSON boundary:** The candidate record's PlayerKey is a native unsigned 64-bit integer at line 10. Keep this representation internal, but publish a decimal **string** and canonical u-prefixed 16-digit uppercase hexadecimal unit ID if exposed in JSON/JS/API. Sampled player key **239816685251647096** exceeds JavaScript's exact integer range 2^53; an unquoted JSON number would risk silent identity corruption. The newer native XYZ reader already uses lossless string unit identity; align contracts. Add tests around >2^53.

The alternate-flag SourceComponent only establishes a selected self slot exists, **not** native helper 0x6136B0 admission, passive freshness, player-world meaning or a producer writer. The reader's current qualification text respects this. Test missing source slot 0xFF and owner-switch paths as useful follow-ups. All recommendations are review-only; no source edits or root tests run here.

## Independent read-only review of root's fast transport and paired/location candidates

All reviewed files below were **root-owned, in progress, and not edited by Jimmy**. Source fingerprint at inspection:

| File | SHA-256 |
| --- | --- |
| scripts/fresh_native_xyz.py | **2F0D0FA6BC07A6B67312759944BCCC0B491BBF77039319F79884F05B81842610** |
| tests/test_fresh_native_xyz.py | **A0F3C27F1B15F8BA02840A0988BE65AA0CC340271F2F0FAF51152FED122E91D8** |
| src/RiftReader2.Live/Control/ControlNativeXyz.cs | **7D5CEC192DB47ABEF970BAEC592EB63F83C5E385D81AB6A33CC5D58F560144C1** |
| docs/reference/native-current-xyz-fast-transport.md | **903AEE46CD01388462EC5BEF4CD6CC108A903644561D4BFB66E6F7632C082F9A** |
| src/RiftReader2.Live/CurrentBuildPairedPositionCandidateReader.cs | **94D3E1772C3DD44C981B6C857FAEF4537E20342ED6C04CCE95EABAA771C78F89** |
| src/RiftReader2.Live/CurrentBuildLocationContextCandidateReader.cs | **79DDBFED66B5EE2CD0CCC92C4F315587C3ACF9B2DE4867A1BE05954559E94121** |

**Fast transport strengths:** It correlates unique command UUIDs to response queues and the guest guards duplicate sequence/IDs. There is no identified wire-level cross-request response bug. Game process PID/start/exe SHA are pinned per query, tests exist, and the docs honestly say one-shot candidate-only/offline tested.

**Fast transport tracking gates before navigation consumers:**

1. Host validate_response_time currently admits guest observed/acquisition timestamps within about **±5 seconds** of its request/response boundaries (fresh_native_xyz.py lines42-53). That can accommodate cross-machine clock skew but is **not** an end-to-end low-age coordinate guarantee. Existing tests cover gross one-minute staleness and inverted times, not near-window replay. Require an explicit age/skew policy for tracking, a monotonic guest clock or server-correlated sample sequence, and boundary/replay tests; do not call a successful request fresh on time tolerance alone.
2. A successful call matches its current PID/start/SHA but **does not pin the preceding player key, zone, nonce or world instance across calls**. The expected-zone option intentionally fails closed for now (fresh_native_xyz.py lines105-106). A navigator must reject a unit change or unknown/discontinuous zone transition before connecting two points into one motion path. Tracking continuity is a higher-level invariant, separate from proper wire request/response pairing.
3. Guest agent capability advertises a protocol version and instance ID but no exact deployed **reader/agent executable SHA** (fast Python lines130-151; ControlAgent.cs inspected lines309-320). The game SHA is pinned and post-serialization receipt SHA exists, but a future actual-deployment acceptance needs a source/binary build attestation to avoid assuming offline tests match the running guest. Avoid claiming sustained 2 Hz or passive freshness from offline transport tests alone.

**Paired position reader:** Re-reads self and target cached position-component +0x48 values sequentially in one process/epoch with owner/link checks and bounded local elapsed acquisition, but the selected target may be a guarded fallback key rather than a confirmed UI-selected target; no explicit self-target distinctness gate, world or zone. Two cached position reads are **not independent evidence of cache freshness**, and elapsed time covers intermediate target/vitals work. Candidate-only/atomic=false is the correct current status.

**Location context reader:** Combines self cached XYZ, typed health-owner +0x150 zone key and optional type0073/TLS-based zone ID under player/process/thread/owner checks. It has no independently established world-instance ID, absolute cross-field skew bound, or final XYZ reread after optional longer TLS zone search; location and zone can therefore represent different instants. A historical Lab2 zone candidate matched an older API baseline, but not a simultaneous changed-state, full-restart or independent-position proof. Continue treating it as candidate context rather than a waypoint gate.

**Recommendation to Saturday owner:** Keep all three root lanes progressing as *candidate-level telemetry*, introduce separate per-track identity/zone/age and deployment-provenance gates, and only promote a movement source after same-player changed XYZ with an independently recorded endpoint and a full-game-restart requalification. No live transport or game operation was performed in this review.
