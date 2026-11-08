# RR2 RTTI/source windows — bounded static result (2026-11-08 06:38 UTC)

**Outcome:** Exact current-build retained Ghidra bytes show a slot-0 **jump thunk**, an initially zeroed image-data region, and ASCII `Entity::Component\0`. These support **generic component infrastructure** investigation, not a qualified player owner, live component instance, location source, or XYZ retrieval.

## Verified source and execution

- Host-only script: `artifacts/rea/rtti-source-windows-review2/Rr2RttiSourceWindowsExport.java`, SHA-256 `a252db67bcfd6843fbed4b4931eaf7221e5922dbb0abe48b208afc76187d7b55`.
- Retained project: `artifacts/rea/RiftNativeFocusedV2`, program `rift_x64.exe`, image base `0x140000000`. Imported executable SHA-256 **metadata** `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`; **not a fresh executable-file or live rehash**.
- Job: `rr2-rtti-source-windows-20261108-root-02`, PASS **exit 0**, finished 2026-11-08 06:38:40 UTC and printed `RR2_RTTI_WINDOWS_COMPLETE`. Existing Ghidra project was `-readOnly -noanalysis -max-cpu 1`.
- Strict scope: four fixed 128-byte initialized windows (**512 bytes total**); at most four existing incoming and four outgoing refs per anchor; no pointer dereferencing, analysis, code/data creation, memory writes, live reads, or recursive traversal.

| Anchor RVA | Retained evidence | Qualification boundary |
|---|---|---|
| `0x5A9990` (`.text`) | Function symbol `thunk_FUN_14125f0f8`, bytes start `E96357CB00`; existing unconditional jump to RVA `0x125F0F8` | Resolved **thunk destination**, not method semantic or active dispatch |
| `0x125F0F8` (`.text`) | Destination function `FUN_14125f0f8`; one incoming unconditional jump from slot-0 thunk; also one retained DATA ref from `0x1436BAAE4` | Function identity observed, purpose/owner unknown; DATA ref is not demonstrated code invocation |
| `0x33DBB60` (`.data`) | Whole 128-byte retained image window is `00`; initialized writable image section | Initial **file/image bytes only**; **not evidence of current-process null/absent singleton** |
| `0x2774E20` (`.rdata`) | Raw ASCII `Entity::Component\0`; exact bytes `456E746974793A3A436F6D706F6E656E` then `7400` | Candidate generic component descriptor; not player-specific RTTI or a live instance |

This extends the earlier slot evidence in `handoff-2026-11-08-position-slot-context-0632z.md`: a table-like raw `.rdata` layout and a slot-0 thunk are consistent with **candidate** object/dispatch plumbing but do not establish the table's type, method behavior, reachability, source freshness or owner.

**QA:** An earlier review-1 script compile-error run has preserved logs and **is not evidence**. Another attempted invocation returned process exit 0 without the required completion marker and was **not accepted as a successful export**. Only the corrected review-2 job above qualifies.

**Next bounded static question:** inspect retained code *at the known thunk destination* and existing nearby type-descriptor references with exact caps to distinguish generic registration/destruction logic from a position source. No guest, controller, VM or RIFT process was touched.
