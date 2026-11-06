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

Finish `0x1290458`'s selector/ID-to-reference branch with the cooldown worker;
then add an isolated bounded *ability record/vector candidate inspector* using
existing exact-build memory-session and identity guards. Require the outer type
fingerprint, bounded/aligned begin/end, slot limit, nullable child handling and
owner/header rereads; emit raw IDs/types with unavailable reasons. Expose costs
only after statically reconstructing the selected child's producer and its
separate player context, with retained typed input fixtures. A decoder for only
`+0x6D0` would be useful after ownership is resolved; a fake module-rooted live
cost reader now would conceal the missing conditional lookup.
