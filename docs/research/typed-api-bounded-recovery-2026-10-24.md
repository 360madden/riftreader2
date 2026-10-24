# Typed Lua API readback recovery — bounded-scanning evidence and decision

Date: October 24, 2026 (America/New_York). This is **source/history research and an experiment design**, not a new live typed API observation or guest deployment. V1 files were inspected **read-only**. Current V2 coordinator is V10, authenticated and live; the game binary identity still matches the archived samples, but PID/start have changed.

## Observed blocker and exact mechanism

The last guest readback diagnostic on October 23 used the already installed typed-aware observer `C:\RIFT_TRANSFER\GuestReadback\GuestObserver\RiftReader.GuestObserver.exe`. It identified the then-current RIFT game but returned `readback.status=blocked`, `readback.reason=scan-byte-budget-exceeded`; therefore it published no `typedApi` payload. See [guest blocker](../validation/rift-typed-readback-blocker-2026-10-23.md). This observation predates the October 24 game PID **6940**; **current typed-readback status has not been remeasured**.

Read-only inspection of V1 (not a code-change request for V1):

- `C:\rift modding\RiftReader\reader\RiftReader.Reader\GuestReadback\GuestReadbackContracts.cs`, SHA-256 `DF3F3FF0CA303C55CB0F1A6F0A68688203A560DEB4AB48C7A2E947DE996B4339`: default byte budget **4 GiB**, time budget **10 s**, chunk **1 MiB**, typed enabled only by opt-in.
- `GuestReadbackService.cs`, SHA-256 `D849BDD036A392AB7F22AB50AAC4774F48CDACB3D436270BFED3743B962C791F`: `ScanMemoryCore` enumerates *all* committed/readable/private regions sequentially; `ScanRegion` aborts when `ByteBudget - bytesRead <= 0`. Crucially, `Capture` checks `pass.Complete` **before** calling `TypedApiFreshnessTracker.Evaluate`. The blocked result proves only the broad pass ran out of budget; it does **not** prove absence of `RRAPIVAL` frames.
- `TypedApiMemoryExtractor.cs`, SHA-256 `13C420D325C800E891D84F031835C052C543D155851AA8E97C439DC42C31EC02`: looks for **UTF-8** `RRAPIVAL`, strict `|RRAPIVALEND` publication suffix, maximum wire length **8,214 bytes** and bounded overlap.
- `TypedApiSnapshotParser.cs`, SHA-256 `8A5F5AC58C5DC1C7FC550FB11F8866094FA3FFACECF7D8BA2A1A61F162D87C41`: exact schema/version allowlist; `RRAPIVAL2|` accepts `RiftReaderApiProbe` addon **0.6.0**, typed position, health/resource, combat/zone fields; malformed and duplicate-key payloads fail closed.
- `TypedApiFreshnessTracker.cs`, SHA-256 `FCDFA405A2F064CFF06573DACC2A22DB4E9A78603E13540A409DA4B964CAB484`: ranks complete candidate frames by frame time before sequence, rejects malformed/conflicting latest frames, warms on first observation, and requires independently advancing frame time **and** sequence thereafter. It accommodates a UI-reload generation change, but treats stale/backward time conservatively.
- Producer `addon/RiftReaderApiProbe/validation.lua`, SHA-256 `618CA4443986E8C683CBEE51C92D0992296E125E4BA387AF3C99F86B2E1853FF`: updates `RiftReaderApiProbe_ValidationWire` with `RRAPIVAL2|` + JSON + suffix on an intended **0.50 s** refresh. The Lua source uses `Inspect.Unit.Lookup` and `Inspect.Unit.Detail`; unavailable values have explicit status, not synthesized zeros.

## Independent historical positive evidence

V1 retained a genuine successful two-sample live gate in

`C:\rift modding\RiftReader\.riftreader-local\typed-acquisition\delivery-restored.json`

file SHA-256 `9B50C6F1E23FC998DF51739DDBEA177BBA7B8C3ED259385F1ADA92BA853CA5A5`. Historical **October 16**, game PID **3776**, same on-disk executable SHA-256 `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`:

| Sample | Typed status | Selected address | Candidates | Sequence | Frame clock |
|---|---|---|---:|---:|---:|
| First | fresh | `0x3D3189F0` | 5 | 5603 | 5302.787109375 |
| Second | fresh | `0x3D2BD3B0` | 3 | 5608 | 5305.595703125 |

Both reported schema 2/addon 0.6.0, full `coordX/Y/Z` and health resources. The first and second full acquisition windows were roughly **636 ms** and **716 ms**, respectively. The second reference advanced time and sequence. **The selected heap address changed within one process without a restart**, while multiple candidate copies existed. These addresses are examples of heap mobility and cannot be imported into a new PID as locators. The archived reference values are independent Lua output, **not proof of today's PID 6940 coordinates**.

## Decision and minimal next experiment

Prioritize a **small, process-epoch-bound typed-wire scout** using existing V2 `RiftReader2.Live.exe` read-only map/snapshot capability and the already proven V1 typed-wire parser/freshness contract for comparison. No new control framework, alternate HTTP listener or broad memory dump. Do **not** blindly increase the global V1 4 GiB budget or modify V1 source.

1. Reconfirm exact VM and RIFT PID/start/SHA plus V10 supervisor/queue state. If a guest execution channel is required, obtain true coordinator STOP/release and exclusive console ownership; use the tested direct guest PowerShell approach, then restore a fresh pinned host. Prepared V11 is valid **only** in the current VM process epoch.
2. Acquire a bounded read-only `map-native` report for the exact *current* RIFT process. Record region count, committed/private/readable byte coverage, and region sizes. Use archived positive addresses and game memory layout only as **prioritization hints**, never raw cross-epoch read addresses.
3. Select explicitly bounded regions/windows, preserving unmapped/unreadable holes. Search for complete `RRAPIVAL2|` frames with sufficient overlap, strict size and suffix, source-version/parser validation, and candidate multiplicity accounting. Retain actual bytes/file hashes with exact build/start identity. Candidate selection must reject conflicting newest complete frames, malformed copies, stale frame time, wrong addon/player identity, and truncated ranges. If the selected scope is incomplete, **label uniqueness as scope-limited**; do not make a global uniqueness claim.
4. Collect at least two independent samples separated sufficiently for the 0.5 s producer refresh. Require advancing source sequence and `Inspect.Time.Frame`, stable game process/character identity and fresh host/guest receipts. An unchanged or unavailable value is not a fabricated zero.
5. Only then run the existing exact-epoch `follow-pointer` candidate root `0x32E0200`, decode owner float32 at `+0x320/+0x324/+0x328`, and compare numerically with fresh Lua XYZ of the same process. Preserve timestamps/deltas and any contradictions. Do not automatically promote to a qualified field or infer update survival from same binary hash.

**Required tests before guest use:** complete frame across chunk edges; malformed/duplicate JSON; stale copies; newest-frame conflict; no frame in covered scope; partial/unreadable regions; wrong PID/start/build; observed heap relocation; source sequence/time reset; no-overwrite evidence publication; read-only/no input. Mark any unscanned/private coverage explicitly.

Current outcome: **root cause reproduced by code inspection; historical positive wire behavior independently anchored; bounded recovery approach selected for implementation/testing.** Current-epoch typed acquisition and same-epoch Lua/native XYZ correlation remain pending. Reusing the live V10 screenshot is useful visual evidence but does not satisfy the typed API gate.
