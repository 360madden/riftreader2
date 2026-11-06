# Native Mana candidate — November 6, 2026

Status: **kind-3 owner, raw record and exact-build static type path identified;
live descriptor fingerprint and independent semantics remain unqualified.**

The bounded read-only Lab-1 probe completed without game input against PID
`7164`, start ticks `639294897866244204`, executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
The stable kind-3 record reported base/max `3980/3980`, rate `9807`, matching
record/wrapper revisions `8/8`, wrapper clock `74064.5703125`, and game clock
`74292.7421875`. Its record vtable RVA was `0x2A6ACD8`; vtable slot `+0x40`
held descriptor getter RVA `0x1CCB460`. Original requests, responses, hashes and
post-read anchor checks are retained under
`artifacts/native-unit-manager/lab1/cbaa7a4fcc0941ef967a7a2fb211ae0a/`.

Bounded iced-x86 decoding of the independently SHA-pinned PE established this
static path:

```text
record vtable                 0x2A6ACD8
descriptor getter (+0x40)     0x1CCB460 -> 0x1CEAFB0
descriptor singleton global  0x34D8990
descriptor vtable            0x2A7C418
type getter (+0x08)           0x1CF9F10
type helper                   0x1CF08E0
seed / xor                    0x110A1FCA / 0xA839
derived low16 type            (0xAF13 ^ 0xA839) = 0x072A
```

This independently explains the expected `0x072A` check in resolver
`0x1CDC680`; it is distinct from Energy type `0x072B`. The live probe did not
yet read and bracket the descriptor global or its type-getter slot, so the path
is static evidence rather than a passed live fingerprint.

The current-value getter at RVA `0x133DD10` uses record rate `+0x18`, base
`+0x1C`, revision `+0x20`, maximum `+0x24`, wrapper revision `+0x1C`, and
wrapper clock `+0x24`. It applies float32 rate scaling with the exact constant
`-0.009999999776482582`, elapsed game time, truncation to signed int32, then
clamps to `0..maximum`. `scripts/native_mana_candidate.py` replays only the
ordinary finite domain and refuses output unless its caller supplies the exact
build, kind 3, and separately verified type `0x072A`. Six focused tests cover
ordinary regeneration/drain, float32 rounding, type separation, build/revision
gates, unsafe domains and input immutability.

The observed `3980/3980` is a raw/calculated candidate, not independently
synchronized Lua/UI truth. No changed Mana state, passive freshness, continuity,
full-game restart durability, loaded-module hash, or cross-lab reproduction was
established. The live descriptor slots must pass exact-process bracketing before
the candidate is integrated into the shared vitals reader; semantic promotion
still requires an independent same-player reference across a real Mana change.

## Prepared live fingerprint probe

`scripts/probe_native_mana_descriptor.py` is ready for a coordinator-scheduled,
serialized Lab-1 run. It composes two complete existing kind-3 owner probes around
two reads of only three eight-byte module-relative slots: record-vtable getter,
descriptor singleton, and descriptor-vtable type getter. It requires the same
PID/start/SHA, native player ID, resource wrapper/reference/record, vtable/getter
and record/wrapper revisions before and after. Both descriptor snapshots must be
byte-identical and match the exact static path above. The result retains the
probe/workflow hashes, each descriptor request/response hash, and both full owner
review hashes. It does not invoke a native getter or write game memory.

All three phases must also retain the exact collected VMware identity, reader
SHA, workflow SHA and owner-probe source SHA. The Mana orchestrator and owner
probe sources are hashed before the first phase and rechecked between phases and
immediately before publication. Source drift fails the operation. Operation
initiation deadlines are independent and explicit: 240 seconds for each owner
phase and 120 seconds for the descriptor phase. Each deadline is checked before
starting another operation; an operation already admitted may finish under its
own bounded guest timeout. These are neither hard phase wall-time limits nor one
overall deadline.

Before scheduled execution, focused fingerprint tests covered the positive
`0x072A` path, corruption or omission of every live slot,
process/player/record/revision changes, Energy/type substitution, invalid module
identities, VM/source/workflow drift, and initiation-deadline terminology. The
live result below then passed the prepared check.

## Live descriptor result

The reviewed probe subsequently **passed** on Lab-1 without game input, reload,
native getter invocation or process-memory write. It retained the same VMware
identity, game PID `7164`, process-start ticks `639294897866244204`, executable
SHA `1935A05C...4BE8`, module base/size, player
`u035400012FA2D678`, wrapper/reference/record addresses, vtable/getter and
record/wrapper revisions across the owner-before, descriptor and owner-after
phases. Both owner reviews report `sourceStableAtPublish=true`; their raw Mana
base/max remained `3980/3980`.

The live slots exactly matched the static path and produced type code **`0x072A`**:

```text
record vtable                 0x2A6ACD8
descriptor getter             0x1CCB460
descriptor singleton global  0x34D8990
descriptor vtable            0x2A7C418
type getter                   0x1CF9F10
```

Retained evidence:

- owner before: `artifacts/native-unit-manager/lab1/b9a28c82c5f246b794c3671e4239e0b5/`
- descriptor: `artifacts/native-mana-descriptor/lab1/fc51c5628dd44b869c0743ae1ce2551f/`
- owner after: `artifacts/native-unit-manager/lab1/031feb8237c343dcb07217fc6d5fdedf/`
- final descriptor review SHA-256:
  `5AE1379D0DCD9EF6200CBBBFC4D6524EE819D84C4BCF8EF1574CDD67DB7F31CF`

This promotes the current exact-process record from an untyped kind-3 record to
a **type-checked raw Mana candidate**. It does not establish independently
synchronized Lua/UI semantics, changed-state correspondence, passive freshness,
continuity, cross-lab compatibility or full-game restart durability. The value
must remain candidate-only until those separate gates pass.
