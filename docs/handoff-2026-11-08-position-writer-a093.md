# A093: bounded primary/secondary writer distinction

Evidence date: 2026-11-08 UTC. Static-only, existing Ghidra project; no live process,
VM, input, controller, deployment, or restart evidence.

## Result

No direct store to the primary position-component triplet +0x48/+0x4C/+0x50 was
found in the complete bounded CFGs of 0x699DD0 or 0x699A50. This excludes direct
stores in these two bodies, not side effects of unexamined callees or all writers.

- **0x699DD0 is a secondary-cache updater.** It reads primary +0x48/+0x4C/+0x50,
  and either copies primary to secondary +0x88/+0x8C/+0x90 or conditionally
  interpolates lanes 0 and 2 toward primary. The final lane-1 store copies
  primary +0x4C to secondary +0x8C. No world-axis or freshness semantics follow.
  Stores: 0x699FBE/0x699FC6/0x699FCE (secondary interpolation),
  0x69A00E/0x69A016 (secondary copy), 0x69A05D (lane 1).
  CFG: 154 instructions / 681 bytes, completeWithinWindow=true; decompile success.
- **0x699A50 updates the secondary matrix/transform.** Direct component stores
  are +0x94..+0xB4 and +0xF4, not primary XYZ. It copies matrix +0x60..+0x80
  or computes scalar adjustments before passing component+0x94 to 0x11439D0.
  CFG: 188 instructions / 887 bytes, completeWithinWindow=true; decompile success.
- **0x6988D0 callsite confirms same object/scalar for both helpers.**
  RCX is saved to RSI at 0x6988E4. Caller XMM2 is moved into XMM1 before
  0x6988F5 -> 0x699DD0; XMM6 preserves that scalar, then RCX=RSI and
  XMM1=XMM6 before 0x698903 -> 0x699A50.
  The original 64-byte slice decoded 17 instructions / 62 bytes and stopped
  at 0x69890E. A separate source-hashed raw-tail export now confirms:
  0x69890B: 48 8B CE = MOV RCX,RSI;
  0x69890E: 40 0A FB = OR DIL,BL;
  0x698911: E8 AA 0D 00 00 = CALL 0x6996C0.
  The relative target is 0x698911 + 5 + 0xDAA = 0x6996C0; the intervening OR
  does not change RCX. Thus the third call uses the SAME component.
  Its scalar argument is not asserted. This confirms static call order
  0x699DD0 -> 0x699A50 -> 0x6996C0, not runtime invocation.

## Unexamined effects and next concrete targets

Both helpers pass the component to 0x699610; 0x699DD0 also passes it to
0x59F140. These callees are not proven side-effect-free. The secondary update
path additionally calls selector-derived objects through virtual +0x30/+0x38/
+0x50/+0xD8, 0x5E91C0, 0x78A290, 0x6988A0, and an imported square-root call.
0x699A50 calls 0x1143570, 0x1144B70, 0x574A20, 0x5F37E0, 0x250489F,
0x698AC0, and 0x11439D0. Pointer arguments identify matrix/stack/other-component
routes but do not establish all transitive writes.

Next independent primary-writer candidate: **0x6990D0**, called at 0x6984E2 by
the position-component method 0x6984C0 (retained V8 evidence). Alternatively,
bound 0x699610/0x59F140 to resolve their direct component side effects.

The raw-tail follow-up is complete: **[0x69890B,0x698930)**, 37 bytes.
The original A093 end-exclusive 0x698910 falls INSIDE the three-byte OR at
0x69890E; 0x698910 is its ModRM byte, not a valid start for this flow.
The prior V6 fragment at 0x698910 may additionally conflict with decoding.
These bytes resolve the missing call, but do not prove which decoder condition
caused the original DECODE_FAILED. No existing instructions were cleared by
this review, and no broader function completeness is claimed.

## Exact provenance

- Source: artifacts/rea/ghidra-writer-targets-a093.txt
- Source SHA256: 39b7b04934aacce9abc93ea5f5331197f8d3d2dceedf3230224fa02b1a9bf2fe
- Source size: 28,698 bytes; 685 lines; completion marker present.
- Imported executable SHA256:
  1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8
- Identity scope: imported Ghidra program metadata, not a fresh installed-PE rehash.
- Image base: 0x140000000; language: x86:LE:64:default.
- Exporter: artifacts/rea/Rr2PositionWriterTargetsA093.java
- Exporter SHA256: 9d9d1e2d6032eac59ff09995f1378b758a9df392e31cb15ae81f558f59d704b5
- Root job: rr2-root-ghidra-writer-targets-a093-20261108-01; passed/exit0;
  2026-11-08T05:02:45.191Z to 05:02:53.986Z; output not truncated.
- Job receipt explicitly reports processing the project file read-only.
- Raw-tail source: artifacts/rea/position-callsite-tail-review1/headless.log,
  lines 43-57; log SHA256:
  8675af7098b1bd9e03911f36d36a22e5f3106414d9b597cf2bc85ecd28ce4f96.
- Raw-tail 37-byte SHA256 (not the log-file hash):
  D2D8C532BBBE6FF8FC0364E8A0995FD2EFB9AAD2F9ED323614011F8C97CFE85D.
- Raw-tail root job: rr2-root-ghidra-position-callsite-tail-20261108-01;
  passed/exit0, output not truncated, read-only project; same imported executable SHA.

Source ranges: 10-32 callsite; 34-393 matrix updater; 397-680 secondary updater.
Returned completion and completeWithinWindow markers are bounded-analysis status,
not live execution, passive freshness, full-game restart, or qualification.
