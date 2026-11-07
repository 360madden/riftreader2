# Ability ownership and cost lookup — November 6, 2026

Status: **static locating evidence only**. No live process, game input, getter
invocation, memory write, restart, or ability value comparison in this package.
This closes the cost-vector stride and stack-context source gaps in the
[client map](native-current-client-code-map.md), and identifies one common missing
owner edge with cooldown research. It does not deliver a live ability reader.

## Exact retained source and method

Source: `artifacts/lab2-rift-exe-20261027-01-copy.exe`, 60,493,640 bytes,
SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
The entire file was freshly hashed; its `.text` mapping came from the existing
`scripts/find_native_api_xrefs.py` PE parser. All addresses below are RVAs.
Bounded original byte slices were read without importing or executing the PE.
New instruction descriptions below are manual AMD64 decoding of explicit byte
anchors; a new independent disassembler/whole-function CFG check was unavailable.
The REA `inspect_with_objdump(section_headers)` attempt returned
`capability_unavailable / ERR_REA_WINDOWS_NATIVE`; no setup changes or retries.
Existing independently decoded field-builder evidence remains in the client map.

## Bounded locating recipe and its precise missing edge

1. Native marshaller entry `0x995E10` obtains a 32-bit ability-like key in `R12D`
   through its argument parsing branches. At `0x995ECB`, `E8 30 8C BB FF` calls
   `0x54EB00`, with `RCX=&[RSP+0x58]` and `EDX=R12D`. This is the source of
   the previously unexplained cost-builder stack reference.
2. `0x54EB00` loads a context from **module+0x33624C8** at `0x54EB0E`
   (`48 8B 1D B3 39 E1 02`). It has lazy construction branches, which passive
   readers must never invoke. At `0x54EBF7..0x54EC07`, it passes the context,
   a temporary reference destination and the original ID to **`0x1274AD8`**.
3. `0x1274AD8` loads registry **module+0x3372C18**, obtains the context's
   **16-bit selector at +0x40**, and passes selector plus the 32-bit ID to
   **`0x129043C`** (call `0x1274B16`). That wrapper dereferences its registry
   handle and delegates to **`0x1290458`**. The latter's conditional collection
   selection is shared with cooldown research and remains the precise missing
   module/context-to-record edge: do not flatten it to `owner+0x200`.
   Correction to the older map: call `0x1290448` has bytes `E8 0B 00 00 00`,
   targeting **`0x1290458`**; `0x129045C` lies inside its first instruction
   (`48 89 5C 24 18`, beginning at `0x1290458`).
4. At `0x54EC0D`, helper **`0x18A3750`** converts the returned reference into
   the caller's stack reference. This helper copies `[RDX]` into `[RCX]`, adds a
   reference and calls **`0x127303C`**, accepting only **type fingerprint `0x0051`**
   (`66 83 F8 51` at `0x18A3788`); otherwise it releases/zeros the output.
   This is the expected *outer ability record type* for this marshaller route,
   separate from child cost types `0x1E29/0x1E2A/0x1E2C` and resource types
   `0x072A/0x072B`. It has not been checked on a captured ability record.
5. The marshaller then calls `0x49FAB0` at `0x995EE4` with the ID and the
   address of that stack reference. Its effect is not fully decoded, so a
   passive reader must not assume the reference is immutable afterward.
   Separately, `0x995EF1/0x995EF9` call `0x49A020/0x49A440` to obtain `RSI`,
   the context subsequently supplied to cost producers. Thus the ability
   record and player-sensitive cost-calculation context are distinct inputs.
6. The cost loop takes **record+0x6D0** as its reference-vector header. The
   header's **+0/+8** are begin/end pointers; each slot is an **8-byte reference**:
   load `[RBX]` at `0x9967F0`, then **`ADD RBX,8` at `0x996CD6`**
   (`48 83 C3 08`), compare against end, and branch back to `0x9967F0`.
   Cost production is not a direct read of a literal player cost member.

The immediate useful passive recipe is therefore:
`existing context slot -> registry(selector, ability ID) -> type 0x0051 record
-> +0x6D0 vector -> 8-byte child references -> cost-type dispatch`.
It stops at the conditional registry lookup until collection/key ownership is
reconstructed. It must also account for `0x49FAB0` and the separate cost context
before claiming the actual player-adjusted cost. No current player-owned ability
record, known/spellbook membership, ID meaning or cost number was observed.

## Focused checks and retained-byte fingerprints

Fresh full-file SHA matched. Direct relative-call targets were recomputed from
signed little-endian `rel32` at the listed call sites, including the corrected
`0x1290448 -> 0x1290458` edge; byte anchors were read
through the PE section mapping. Useful bounded slice hashes (end exclusive):

| RVA range | SHA-256 |
| --- | --- |
| `0x995E60..0x996000` | `ff9c40bd7091390228070d7e56634d8f98b30cb4168bdee312b37d0d9c331845` |
| `0x996640..0x996850` | `9020ecfc220679269191e905b6048f50ba012a1890974f8bdc7d3c62611940b9` |
| `0x996900..0x996E10` | `2fdb323193bcbf02520fbae091ff3e08607e166ff4ee41687133e36e166553bd` |
| `0x54EB00..0x54EBD0` | `8d00f7783d2215e6e3517974a6cec0a317f8bfa2e070b13d2139c9919eea3cfa` |
| `0x54EBD0..0x54ECB0` | `7cd5dd49f3860fa558363c96bcbf755e7070435331aaf2ec3bea2c14fb43b42c` |
| `0x1274AD8..0x1274BA0` | `d60165fa440e66587321aa9d780e71e3695039167adc04a3d9c4f797c6b9ccfc` |
| `0x18A3750..0x18A37C0` | `f59b8ad4479ebbc91cb9fad608fcce9311424be9eeca35939c1fdd3e5932bf5b` |

## Next useful code opportunity

### Verified native record sampler — November7 10:26 Eastern

`sample-current-ability-records` now reconstructs requested cached records in
one exact-build read-only acquisition. It checks complete thread/TEB/TLS
coverage, unanimous collection selection, cache key/holder/record bindings,
initialized type descriptors, both child references and final process identity.
It invokes no native getter, initializer or refcount operation.

```powershell
python scripts/sample_current_native_ability_records.py --lab lab2 --key 0x2DE2D844 --key 0x3C5AEC64
```

The per-SHA experimental reader is117327712 bytes, SHA256
`F4148B838AF694EF95FD46DE76859CE9DF55194A9FE8BE1DF74FC2F8F0BCE80F`.
It does not replace existing workflow/owner bundles. Contract:
`native-current-ability-records-candidate-sample/1`.

The type0x0051 object profile is vtable0x28A08C0/getter0x1899BF0;
initialized descriptor0x344A6B0 has vtable0x28A9C38/slot+8 target0x18C06C0.
Type0x1E17 child profile is vtable0x27F24F8/getter0x170C5D0;
descriptor0x3417970 has vtable0x2802E40/slot+8 target0x17361E0. All are
module RVAs on the pinned SHA1935A05C... build. Neither lazy path is called.
Full IDs use the native DWORD as high32 and the low32 sum of the two verified
child-key hash terms. Null children contribute zero; unreadable or unverified
children do not get silently converted to zero.

Lab2 `artifacts/native-ability-records-20261107/runs/lab2/ecdc2a67f0ef40cea773301a594e8ee9/`
captured8 type-verified records in28.394ms. All8 full IDs matched both the
Python typed capture and the independently retained historical API strings.
Raw report SHA `0AB0C3C14E7440B8252A7E80425217E6B067BACFAE68C150E1D53342D5C19AEF`.

Lab1 `artifacts/native-ability-records-20261107/runs/lab1/88e3f30410724fdd866f5c72ad658164/`
captured all122 requested native map keys as typed records/full IDs in39.111ms.
The player-map samples before and after had identical identity, context, keys
and primary/secondary raw float bytes.43 records had a nonzero API List filter
byte; this reconstructs the code path's eligible candidates, not independently
observed learned membership. Correlation receipt:
`artifacts/native-ability-records-20261107/lab1-bracketed-73168d2fb24f4a44b0597f5cba1121ba.json`.
Seven focused .NET tests and five host-validator/launch tests passed. The bulk
launch uses a SHA-checked numeric data file and shared directory prefix to stay
within the4096-character guest encoded-command limit, without changing policy.

Cache misses remain cache-only; current-language names, same-build independent
API List comparison, changed-state/freshness and restart qualification remain
open. No game input, reload, restart, owner transition or active-bundle change.

### Fast current localization candidates — November7, 10:57 Eastern

The single-process `sample-current-localization --pid N --start-ticks N
--keys CSV --output PATH` command captured8 requested localization keys onLab2
in11.406ms. Three returned typed text candidates:1071143829=`Ascended Resurrection`,
507994655=`Toggle Ranged Attack`,489178066=`Track Fish`. The other five were
cache misses; no absence or fallback conclusion follows. Mode1/locale1,
provider/record/child initialized fingerprints, tree/text ownership and consumed
bytes were verified, followed by process revalidation. This is current text for
those keys, not independent API agreement, ability ownership or restart proof.

Receipt: `artifacts/native-localization-20261107/runs/lab2/11be9198a5874f8cbcdc276daa597e30/samples.json`,
SHA256`2DD767F27C87500C5601FDD80488BCCB66F81E4AC62B9285F7D05B5C6C54B60A`.
Separate reader117368672 bytes,
SHA256`7B44F193F9B47A57E2F18AE7219FB9AF4B4252E1ABBC5812B3ABD2609946F4F9`.
Artifact launcher: `python artifacts/native-localization-20261107/launch_localization.py
--lab lab2 --key 1071143829`. Five focused native checks passed. No input,
fallback invocation, initialization, active-reader replacement or owner transition.

### Actual localization provider — November7, 10:50 Eastern

The default-provider refusal was correct but did not describe the active route.
Lab2's fresh bracketed pointer capture verified wrapper vtable RVA`0x26C1EA8`
and first method`0x7D3230`, matching the explicit heap-provider constructor.
Receipt: `artifacts/discovery-20261107-cast/lab2/654cf6947b9e4dca9f1d25f75ecc325c/summary.json`.
PID9752/start639294897826627677, exact SHA1935A05C...; repeated chain, vtable
and method bytes matched, with final identity inspection. No provider was called.

This provider reads inner=`[wrapper+8]`, map header at inner+28. Lookup uses
ONE native key-hash round, DWORD node+8, holder=`[node+10]`, result=`[holder+18]`.
This is distinct from the selector/composite-key dataset cache. Its bounded
hot-cache misses cannot establish missing translations; backing lookup remains
unresolved. The lazy default-provider global being null does not invalidate
this separately observed override. Selector84 was never established.

Passive exact-build result type1E1B profile: object vtable295DC10,
slot+40 getter1A4FAF0; initialized descriptor3484000, vtable2963030,
slot+8 getter1A779E0, low1685CA XOR9BD1=1E1B. Text type1E1D:
object vtable2804120/getter173C790; initialized descriptor3420930,
vtable2820340/getter177CE30, low1680A8 XOR9EB5=1E1D. All numbers are
module RVAs except type arithmetic. Require initialized descriptors and stable
ownership before interpreting locale-tree or text bytes. Current-language names
remain pending a successful fresh typed capture.

The first keyed override-cache attempt (`lab2/cef05ca73abd48dcb0ef10e85596b0fd/`
under the same artifact root) retained a PARTIAL result, no names, after eight
guest snapshot calls. Offline replay verified real changes at both requested
24-byte hash heads and four chain nodes between initial and final reads, rather
than a read-size bookkeeping mismatch. This establishes acquisition changes,
not their cause. A one-process native reader is the next route; preserve the
anchor checks rather than accepting mixed cache generations.

The Lab1 current122-record receipt has14 exact full-ID correlations to the55
historical named API rows; all14 are within the43 nonzero+0xC9-filter records.
There are zero high-word-only matches. Source hashes and all rows are retained
in `artifacts/native-ability-records-20261107/lab1-historical-correlation.json`.
The historical build differs, so these do not establish current names or learned
membership.

### November7 continuation

The shared registry selection and a complete raw cache inventory are now
[observed on Lab2](native-cooldown-static-followup-2026-11-06.md#accepted-raw-cache-inventory--november-7).
Selector83 matched380 cache keys,379 non-null records, with exact process and
owner/selection/content checks. This does not establish type0x0051, learned
membership, player-adjusted cost, or a name for those records.

The public-ID formatter is narrowed: successful `0x1357250` resolution truncates
its low accumulator via `mov edi,edi` at `0x13574AE`, then adds inputDWORD<<32.
`0xA17E00` emits `A%016llX`, so its high word reproduces the input key without
carry. Historical named IDs remain cross-build search seeds, not current names.
The current name route follows record+0x8E0 to a type0x1E17 child; child+0x18
is a localization key and child+0x20 a NUL-terminated UTF16 fallback pointer.
Both type fingerprints and active localization must still be established before
calling raw fallback text the API name. Trace:
`artifacts/discovery-20261107-cast/ability-reference-followup.md`.

Finish `0x1290458`'s selector/ID-to-reference branch with the cooldown worker;
then add an isolated bounded *ability record/vector candidate inspector* using
existing exact-build memory-session and identity guards. Require the outer type
fingerprint, bounded/aligned begin/end, slot limit, nullable child handling and
owner/header rereads; emit raw IDs/types with unavailable reasons. Expose costs
only after statically reconstructing the selected child's producer and its
separate player context, with retained typed input fixtures. A decoder for only
`+0x6D0` would be useful after ownership is resolved; a fake module-rooted live
cost reader now would conceal the missing conditional lookup.
