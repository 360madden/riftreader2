# RR2 current-build native XYZ writer-route continuation

**Timestamp:** 2026-11-07 23:41 EST (host tools ran 2026-11-08 UTC)
**Project:** `C:\work\riftreader2`
**Branch:** `codex/modular-foundation`
**Verified host:** AMD-DESKTOP via Workbridge 0.16.4-dev
**Scope:** exact-build static native writer/source analysis only

## Executive result

The exact-build function `0x6996C0` has now been CFG-decoded and decompiled
with Ghidra 12.1.2. Its two primary XYZ-cache update routes are understood at
the static-code level:

1. **Handle route:** position-component `QWORD(+0x100) != 0`; resolve that
   handle through `0x6A0040`; apply source selector RVA `0x2F57918` to the
   returned entity; obtain XYZ through `0x612EE0`; conditionally write
   primary cache `+0x48/+0x4C/+0x50`.
2. **Alternate-provider route:** `QWORD(+0x100) == 0` and
   `BYTE(+0x108) != 0`; resolve source selector `0x2F57918` from the owner
   entity; require `0x6136B0`; obtain primary/secondary vectors through
   `0x612B50`; write the primary and secondary cache fields.

The exact `0x6136B0` predicate is:
`*(int *)(*(QWORD *)(candidate+0x48)+0x24) >= 0` AND
`QWORD(candidate+0x58) != 0`.

**This is static evidence, not proof of live branch admission or writer execution.**
The 49/49 historical position-component cohort had `+0x100=0` and
`+0x108=0`, so neither known update route was eligible in those historical
captures. Historical module-root snapshots also show source selector index 46
at `0x2F57918` with SELF slot 46 absent. Do not promote those historical
observations to current runtime state.

## Important source distinction

`0x612EE0` is a getter, not the primary cache writer. It first tries
`0x6126F0`; only on success does it read the returned conditional source
object at `+0xF8/+0x100` and add an actor offset. On failure it falls back
through position selector `0x2F588A0` to the cached component XYZ returned by
`0x698460`.

`0x6126F0` searches a component collection for a matching key and uses actor
selector `0x2F58490` plus `0x67BFB0` to obtain the conditional source object.
Therefore `source+0xF8/+0x100` is NOT a universal player-world owner.

`0x612B50` is a provider adapter that returns three floats to its caller; it
does not itself write the position-component cache. `0x6996C0` owns the
identified cache stores.

Bounded adjacent routines were also inspected:

- `0x698460`, `0x6983F0`, `0x698410`, `0x698440` call `0x6996C0`
  and return pointers to cache/matrix/transform subfields.
- `0x698EC0` writes matrix/derived fields at `+0x60..+0x80` and
  `+0xF0/+0xF4`, not primary XYZ.
- `0x613800` and `0x698910` are actor/transform consumers.
- `0x687320` writes actor translation at `actor+0x3BC/+0x3C0/+0x3C4`;
  those are downstream actor coordinates, not the player position component.
- `0x612960` constructs a quaternion-derived matrix, not XYZ.

The bounded call graph does not constitute an exhaustive whole-image search for
every external store to the same component offsets. No second destination-matched
external writer has been verified yet.

## Exact-build evidence and artifacts

Executable SHA256:
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.

- Ghidra project: `artifacts/rea/RiftNativeFocusedV2`.
- Main pseudocode export:
  `artifacts/rea/ghidra-v5-pseudocode.txt`,
  SHA256 `78ad0d1edb84eba9dcf309911c0117df17369f1ea0b85230608e1f248fea30b1`.
- Helper pseudocode export:
  `artifacts/rea/ghidra-v6-pseudocode.txt`,
  SHA256 `2cb270ce303de75afab4e9721b80c2313988945d9ee32a53763bbacd0c42a35b`.
- V5 script SHA256:
  `2efe875c51b4f05fe3147694591973af93a3ae45c04f70cd7d2a47c127fc60d8`.
- V6 script SHA256:
  `4b8cc0cebf86a61c01dd00f0230c076772c31a6ff433209d7417aeef9b955989`.
- Ghidra job IDs:
  `rr2-ghidra-focused-native-v5-process-20261108-a089`,
  `rr2-ghidra-focused-native-v6-process-20261108-a089`,
  `rr2-ghidra-native-callsite-dump-20261108-a089`.
- Instruction-level callsite export:
  `artifacts/rea/ghidra-v7-callsite-instructions.txt`, SHA256
  `ca66aca8543b4e2f0b70f7669025c0d3fe419c4a0864a7ae9832ac625e1ac530`.
  It confirms the exact register flow from `0x6996C0` through
  `0x6A0040`, `0x612EE0`, `0x6126F0`, and the fallback
  `0x698460 -> 0x6996C0`. The fallback can re-enter the updater on the
  selected position component; equality with the outer component and recursion
  depth are not established.
- Original eight-window CFG extraction: 669 instructions / 2,614 instruction
  bytes; all eight explicit Ghidra function-body updates succeeded.
- Exact source report updated:
  `docs/reference/current-native-xyz-writer-evidence.md`.
- Read-only branch candidate reader v2 now samples the exact `0x6136B0`
  predicate and source backlink; output contract /2.
- Focused branch tests: 42/42 passed. Full Release .NET10 suite:
  1303/1303 passed (923 Live + 380 Core).

All of this work was static against the installed executable. No RIFT process
memory read, VM/game operation, controller, input, addon edit, reload, deployment
or restart occurred.

## Read-only branch-candidate reader v2 — 23:41 EST

The exact `0x6136B0` predicate is now sampled by
`CurrentBuildPositionRefreshBranchCandidateReader` on the flag branch only.
It also verifies the selected self-source component backlink to the player
entity. The candidate output preserves context pointer hex, signed nested
value, provider presence, `sourceGuardStatus` and nullable
`sourceGuardEligible`. The handle branch is marked not-applicable; flag zero
is ineligible without further guard reads; missing nested inputs remain
unavailable. A true result is still only a static guard candidate, not proof
the callback or writer executes.

The sample JSON contract was advanced to
`native-current-position-refresh-branch-candidate/2`. Focused tests:
**42/42 PASS**. Full Release .NET10 suite: **1303/1303 PASS**
(923 Live + 380 Core). The full run used the already restored assets; no
tracked package-lock changes were made.

## Current worktree caution

A separate commit advanced the branch during this continuation:
`ad5903cebaa850846206819943e16e30c0338e2d`
(`docs(rr2): pin two-lab control state, release hashes and pending native gates`,
23:34 EST). It included the earlier two-lab readiness/launcher changes; those
are now part of HEAD and were not staged by this continuation.

Current intended checkpoint files are the writer-evidence note, `docs/status.md`,
the branch-candidate reader and sample command, their two focused test files,
and this handoff. An unrelated untracked
`scripts/project_current_native_energy_variants.py` remains present; do not
stage it.

## Next practical work

1. Continue **bounded, destination-matched static tracing** for any store outside
   `0x6996C0` that demonstrably writes the SAME player position component
   `+0x48/+0x4C/+0x50`. Reuse the existing exact-build Ghidra project and
   pseudocode exports; do not repeat broad discovery without a concrete reason.
2. Keep the branch-candidate reader v2 as a read-only evidence tool. Its
   `sourceGuardEligible=true` means only that the sampled `0x6136B0` predicate
   passes; it does not prove `0x6996C0` called the predicate or stored XYZ.
   Keep handle and flag branch statuses distinct.
3. **Do not perform a live native read yet.** The latest two-lab readiness packet
   says neither guest advertises `nativeXyzVersion` or
   `nativeReadLeaseVersion`; it also says Greeting Jimmy has not explicitly
   relinquished a live reader. Operationally ready/disarmed controllers and a
   clean RR2 queue do not prove foreign-reader quiescence. Require explicit
   cooperative release or exclusive native-read admission first.
4. Keep passive freshness, independently changed state, full-game exit/relaunch
   durability, body heading and universal world-coordinate semantics separate
   and explicitly unqualified until each has its own evidence.

**Coordinator remains responsible for all live lab operations.** Continue useful
offline work while live admission/quiescence is unavailable.
