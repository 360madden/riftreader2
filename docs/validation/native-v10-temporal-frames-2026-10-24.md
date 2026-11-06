# V10 RIFT-Lab-1 temporal native-frame QA — October 24, 2026

This continues [the first verified V10 native capture](native-v10-foreground-capture-2026-10-24.md). Scope: **read-only visual evidence**, no gameplay keys, movement, ARM, VM console action, or process memory read.

## Identity-bound captures and queue cleanup

All three captures used the same exact authenticated coordinator V10 (host process PID **8168**, Windows session 2) against VM `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx` (VMware PID **38044**, log epoch `2026-10-24T05:41:51.833Z`). Guest machine **DESKTOP-8632QPL**, game PID **6940**, process start ticks **639284177321390013**, executable SHA-256 **`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`**, window `0x8017C`, RIFT foreground.

| Frame | Captured UTC (host metadata) | Capture ID | BMP SHA-256 |
|---|---|---|---|
| 01 | 12:21:15.854 | `545c9c2b4a2f4e269a58a149c722677a` | `28297FAFD77F2D5E7433CBEABB5EA91B326F5CA382B6C51929AB9385032918E3` |
| 02 | 12:52:10.387 | `0077c1431bf44d14a2a8c232a21f741a` | `8E802BA3ABCC1A6BC228869833C5B68A8994CF972B3F2B8EBAD0C2E92A8F9515` |
| 03 | 12:53:36.967 | `70e47edc39e944558e963cf727fe5e9c` | `662F3C2F138D9F6B0B35DAA4D4EAA8DD39A2C10E1F9E30C07DAC2581CE76BC1A` |

Each image is a verified complete **1211 × 686**, **32-bit BGRA, top-down** BMP of **3,323,038 bytes**. The BMP height field is **-686** by convention; comparisons normalize storage orientation and ignore the unused fourth channel. Unique capture IDs, host capture instants and hashes differ.

One queued Track B request per capture: `rr2-v10-scout-20261024-01`, `-02`, `-03`. Before each newer capture, the script required the exact live host/VM process identities, fresh connected supervisor with `initialCleanupVerified=true`, correct game PID/foreground, disarmed/no held input, and canonical queue free/unheld with a cleanup receipt and no pending work. Each protected capture used its own private lease and was finished **succeeded** only after image/metadata/target/hash validation. Normal supervisor STOP/release cleanup returned the queue to free/unheld; V10 remained ready and guest disarmed. No manual authority reset or second console acquisition occurred.

Untracked evidence (do **not** add BMP, private host artifact paths, or one-use scripts to Git):
`artifacts/recovery-20261024-02/native-v10-scout-capture-{01,02,03}/` containing `image.bmp` and `capture.json`. Read-only comparisons are under that same ignored recovery root.

## Reproducible offline difference test

Added `scripts/compare_native_frames.py`, a standard-library-only comparison tool with exact file SHA-256, strict bounds/header validation, support for top-down/bottom-up 32-bit BMP storage, region-of-interest (ROI) selection and exclusive no-overwrite JSON output. It **does not** access the game, attempt object classification or infer movement. **6/6 focused tests** passed: orientation/alpha handling, exact ROI differences, malformed BMP rejection, bounds/duplicates, dimension mismatch and output preservation. Its suite and the same-epoch handover suite are now included in `scripts/validate.ps1`.

Example from `C:\work\riftreader2` (use unique output path):

```powershell
C:\Python314\python.exe scripts/compare_native_frames.py --before artifacts/recovery-20261024-02/native-v10-scout-capture-02/image.bmp --after artifacts/recovery-20261024-02/native-v10-scout-capture-03/image.bmp --roi world=180,60,880,500 --roi hud=0,540,1211,686 --roi minimap=900,0,1211,220 --output artifacts/recovery-20261024-02/native-v10-frame-diff-02-03.json
```

| Pair / elapsed | Whole frame changed | World ROI changed | HUD ROI changed | Minimap ROI changed |
|---|---:|---:|---:|---:|
| 01→02 / ~30m55s | **73.5576%**, mean RGB delta 6.5892 | 77.9153%, delta 5.8412 | 69.6175%, delta 9.9583 | 55.5203%, delta 1.7196 |
| 02→03 / ~86.6s | **39.2586%**, mean RGB delta 2.1652 | 42.1977%, delta 0.5093 | 41.9635%, delta 3.0591 | 15.6972%, delta 0.4176 |

The **world ROI** is pixel rectangle `x=180..879, y=60..499` (308,000 pixels). The other ROIs are defined by the command above. All percentages count pixels whose **any B/G/R channel** differs; mean deltas average absolute per-channel differences on a 0–255 scale. They are deterministic from the pinned BMP bytes. Evidence output:
`native-v10-frame-diff-01-02.json` and `native-v10-frame-diff-02-03.json` (ignored local artifacts).

## Interpretation and next acceptance

The authenticated screenshot pipeline returned **distinct frame bytes and capture IDs** from the *same* game/VM epochs, with measurable central-world differences even over an approximately 87-second idle interval. This strengthens the freshness/temporal-baseline evidence needed to evaluate visual navigation later, but does **not** establish that the character moved, camera moved, a world object was recognized, or collision geometry changed. Ambient animation, rendering noise, UI motion and other effects remain plausible causes of pixel changes. It is not an optical-flow, segmentation or object-detection benchmark.

Next visual-navigation experiment should be bounded and independently reviewed: select a stable world ROI and HUD mask, inspect actual image content, separate animation-induced noise from controlled motion, and require queue/foreground/STOP-release acceptance for any future movement trial. **Typed Lua readback recovery remains a separate core discovery blocker** as documented in [the bounded typed-scanning research](../research/typed-api-bounded-recovery-2026-10-24.md).
