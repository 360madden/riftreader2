# Deployed XYZ sampler: normal RIFT restart, October 25

**Result: one normal same-build RIFT process restart and automatic coordinate reacquisition passed.** The unchanged deployed sampler found the new process and owner using the existing profile, without an XYZ discovery scan or a saved absolute owner address. Independently advancing Lua frames agreed with the native coordinates within **0.0025 game units per axis**. This establishes the observed restart case; patch recovery and semantic field-catalog qualification remain separate.

The user explicitly requested a normal RIFT restart, sampler reacquisition, Lua comparison and evidence preservation. All timestamps below are UTC. Original evidence is under ignored `artifacts/update-recovery-20261023-01/xyz-restart-oct25-01/` (abbreviated `E`). Repository started clean at `0b3f3e5`, branch `codex/modular-foundation`. See the [preceding guest deployment and movement trial](native-xyz-sampler-live-2026-10-25.md).

## Exact process and unchanged deployment

| Property | Before | After |
| --- | --- | --- |
| RIFT PID | 6940 | 9704 |
| Start UTC ticks | 639284177321390013 | 639285237698112372 |
| New process start | Historical epoch above | 2026-10-25T11:16:09.8112372Z |
| Main-module base | `0x7FF6EBDA0000` | `0x7FF6EBDA0000` |
| Resolved owner | `0x211D37C0010` | `0x1D610AC0010` |

The on-disk RIFT executable SHA remained **7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD**. Equal module bases do not imply the same process; the PID/start identity and owner bytes changed and the old request was explicitly rejected.

The existing guest installation `C:\RIFT_TRANSFER\RR2-XYZ-oct25-02\` was reused. Before and after restart, guest hash checks accepted the same **74,349,475-byte** executable SHA **5CA4A6EA9B8904C4987315AA2AE287B3F32B4BB8ED27F5BA951D4D704682C07B**, and profile SHA **FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8**. No reader/profile replacement, offset change, debugger, injection or process-memory write was performed.

The recipe remained main-module RVA `0x32E0200`, one dereference, 816 terminal owner bytes, float32 XYZ at `+0x320/+0x324/+0x328`. The sampler discovered the fresh PID and resolved the recipe itself; manually pinned PID/start values were used only for independent capture requests and transfer admission.

## Normal exit, absence and relaunch

1. Fresh authenticated preflight found V19 ready, same RIFT/build and VM, no sampled held inputs, guest disarmed/idle and game foreground. A verified same-VM-epoch V20 successor was prepared before V19's normal shutdown. V19 exited at **11:06:39.215659**; queue quarantine and exclusive maintenance ownership were checked around every subsequent console action.
2. Before exit, the deployed reader's inspection and **3/3** sample baseline completed with exit **0**. Exact native identity and samples are retained as `before-identity.json` and `before-samples.json` in the guest archive.
3. The normal in-game **Exit Game** control accepted at about **11:11:33**, showing its logout countdown. The countdown completed and the Windows desktop/Glyph appeared. The first menu click had only dismissed the menu; it was not treated as exit proof. A screenshot-only follow-up encountered a static-desktop second-frame timeout; its first frame was preserved, and later observations used one fresh frame for no-input checks. No process kill, VM reboot or concurrent controller was used.
4. At **11:14:07.973286**, the guest recorded **zero** `rift_x64` processes. The deployed sampler returned **exit 2**, wrote a retained error, and published **no position report**. See original `absence-proof.json`, `absent.stdout.txt` and `absent.stderr.txt`.
5. Glyph's existing **Play** control launched RIFT. The already selected **Atank** character entered the world through its normal Play control, with no credential entry or settings change. Routine post-login panels were dismissed. The addon counters restarted and subsequently advanced.
6. The unchanged deployed sampler completed **5/5** reads, **exit 0**, around **11:19:34**, using new PID **9704** and owner **`0x1D610AC0010`**. A separate `follow-pointer` request pinned to old PID **6940** returned **exit 2**, retained its error, and published **no report**. See `after-identity.json`, `after-samples.json`, `old-epoch-proof.json` and the exact old request/error originals.

The new process's position was stable around **(7460.762, 863.81055, 2976.62)**. No movement pulse or gameplay automation was performed during this restart validation.

## Fresh Lua source and independent native agreement

Two existing `scout-copy-typed-native` invocations, each bounded to **512 MiB / 30 seconds**, ran only to obtain the independent Lua reference. XYZ reacquisition had already passed. Both stopped with **`partial / byte-budget-exceeded`**, preserving that coverage limit, and each saved **three complete 28 KiB snapshot originals** from the new process. The scan/copy intervals were **11:23:34.607635–11:23:35.233859** and **11:26:52.989449–11:26:53.461827**. No old-process Lua heap address was required.

The unchanged archive validators checked input requests, index references, exact process/bundle identity, saved snapshot bytes and per-chunk SHA-256. The unchanged strict C# `inspect-typed-wire` inspected every cross-run pairing: **9/9** returned **`advanced-in-covered-scope`** with complete source snapshots. Every diagnostic is retained in `E/comparisons/`; the highest advancing frame clocks selected `a2-b4.json`:

- Same player **`u035400012FA2D207`**.
- Lua sequence **733 → 1125**, frame clock **444.04052734375 → 642.37261962891**.
- Selected wire addresses **`0xA74D7C0` → `0xA95FF00`**, applicable only to new PID/start epoch.
- Stable Lua XYZ **(7460.759765625, 863.80999755859, 2976.6198730469)**.

Three raw pointer originals were retained. The final unchanged `review_current_pointer_xyz.py` comparison uses **`pointer-2.json` and `pointer-3.json`**, acquired at **11:28:04.150275** and **11:28:13.165606**. The first earlier pointer original remains available; it was not relabelled or overwritten. Both selected raw reads contain native XYZ **(7460.76220703125, 863.810546875, 2976.6201171875)** and validate the root and 816 owner bytes against the new exact process identity.

| Axis | Native minus Lua |
| --- | --- |
| X | +0.0024414062 |
| Y | +0.0005493164 |
| Z | +0.0002441406 |

Native reads followed the selected Lua snapshot acquisition by **71.106** and **80.122 seconds**. An explicit acceptance assertion required both absolute lags to remain within **180 seconds**, in addition to the existing **0.02-unit** per-axis gate. Result: **`candidate-compatible` / `candidate-only-not-synchronized`**. The original reviewer remains conservative about semantics and synchronization.

A further independent **3/3** `sample-position` run completed with exit **0** beside these captures, preserving `verified-samples.json` and NDJSON. Each sample agreed with Lua within **0.00224 units per axis**; acquisition lag was **87.501–88.813 seconds**. The compact feed uses float32 JSON formatting, whereas the raw-pointer comparison above decodes the exact retained float32 bytes. Neither output is substituted for the other.

## Exact evidence and replay

The **111,260-byte** guest ZIP was declared by a one-use exact-peer/process/bundle SHA-and-length receiver, then uploaded through a separate SHA-bound receiver. Both ran independently as signed-in session-2 `pythonw.exe`, `inJob=false`, and exited after their one use. Original received ZIP SHA:

`67F7736A8FC30EF0149CFB4C45FFF156446F712400FE0741C920248DF388F85E`

Bounded safe extraction preserved original bytes under `E/originals/restart-oct25-01/`. `E/recovery-proof.json` records every original filename, byte length and SHA, both process identities, changed owner, absence/rejection proof and independent run checks. `E/restart-validation-summary.json` records all nine diagnostics, selection, source advancement, exact comparison lags and sampler checks.

| Evidence relative to E | SHA-256 |
| --- | --- |
| `originals/restart-oct25-01/after-samples.json` | `9F3CA49C19E78CCE81C10CEFDFF18FDC78D2DDB9BDABBCD03756097A0B3B5FF2` |
| `originals/restart-oct25-01/verified-samples.json` | `06EBF70EFAE3DAD219A6AF870FB0578C4F45ED130861EF6E773A060CE95F9B76` |
| `originals/restart-oct25-01/pointer-2.json` | `9C2B7B5C07CB845CA9F7885D8CB30D020AC0991773E36C85EBA6A9A0213E52E6` |
| `originals/restart-oct25-01/pointer-3.json` | `468B80CF43C9CA4DCF50334B77AB0FACC84EA8428A1976CE326C6A6EA72342E6` |
| `comparisons/a2-b4.json` | `9E5672F8A79EF77B6CE62A22ABD5F6A507D5AC1166F7940B6F28BF648BB162DA` |
| `position-review.json` | `4CB7490A6D06B758E7F3E22BD8E27DDDF915A9C9449B562F57F434982FC662CD` |
| `restart-validation-summary.json` | `18345ACADDD4B0E5C3ADC522A97B5058DF0B0445F34548796E9FE571EDFF036A` |

Replay with the unchanged [typed inspector](../reference/typed-wire-snapshot.md) on the original selected snapshots, then [native field reviewer](../reference/native-field-evidence.md) on the two selected pointer originals, new-epoch request and pinned typed comparison, using fresh output paths. Operational command plans passed Windows PowerShell AST-only parsing; per-command hashes, before/after screenshots, VM identities and one-use claim/upload receipts remain in `E`. No original report was trimmed or synthesized to obtain a positive result.

Both selected typed and native reviews were replayed into new files and matched the original output bytes exactly; see `E/replay-proof.json`. `E/evidence-manifest.json` pins the ZIP, transfer receipts, recovered-original manifest, comparison/replay summaries, final controller observation and gate result by actual byte length and SHA-256.

## Repository verification

The fresh **PowerShell 7.6.8 full repository gate exited 0 at 2026-10-25T11:36:43Z**: **450 .NET tests** (311 core + 139 Live), **669 Python**, **108 Lua** lifecycle/encoder checks, **22 actual Lua-to-C# cases**, locked restore, zero-warning Release build, published native synthetic smoke, deterministic replay, formatting and **518 relative documentation links**. Gate evidence: `artifacts/validation/20261025T113542Z-6f8b2b3c`, plus `E/full-gate.log` and `E/full-gate-result.json`. This restart pass changed tracked documentation only; production code, tests, guest binary and profile were unchanged.

## Restored state and limits

After actual upload verification and visibly closing the guest shell, independent **V20 PID 56804**, signed-in session **2**, `inJob=false`, restored sole VM-console ownership. Authenticated status found **ready/connected**, running supervisor/initial cleanup verified, RIFT PID **9704** foreground, guest **disarmed/not busy**, **no held inputs**, canonical queue free with cleanup receipt and transfer port **8765 closed**. The receiver instance survived, while the controller's derived target epoch changed from `nav-ae70fe3095bcd31e90e33d18162fcf31f05ea0330a20097fd59610cd181ee1f1` to `nav-a0de63540a969dc1ffb5a2e71c85017fa3a99d444a35044bf3143f5895e6b065`. VMware PID **38044**, process start and VM log epoch remained unchanged: this was a game restart, not a VM restart.

The result covers one normal exit, an absent-game rejection, relaunch/world entry, unchanged-profile reacquisition and independent same-player Lua agreement in the new process. It does not establish patch survival, arbitrary future restart reliability, menu/loading-state semantics, synchronized clocks or field-catalog promotion. The post-restart sampler was tested after world entry. Use the saved recipe for this exact build; refresh process/owner/controller identity on every later run and fail closed on a changed executable SHA. Patch-specific profile/rediscovery work remains a separate task.
