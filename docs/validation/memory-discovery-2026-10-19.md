# Memory discovery validation

Date: 2026-10-19. Evidence: `artifacts/memory-validation/`.
This validates the discovery tools, not native gameplay field semantics.

The final published `RiftReader2.Live.exe` is 74,074,531 bytes, SHA-256
`17A1C90E5EB5864F314DE9B6218DA6FB685A15E910E020B3CCE8029EBF63B9EC`.
The lab harness hashed the actual guest executable; the returned identity
matched the host publication. ISO files were byte-compared to their sources.

RIFT-Lab VM process 54820 remained in its existing epoch. RIFT PID 11620,
start UTC ticks `639279813293755454`, executable
`C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, SHA-256
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`,
main module `0x7FF6B6EE0000`, size 62,611,456. The private receiver retained
the guest result at `2026-10-19T05:25:40.300075Z`.
Retained receipt SHA-256:
`208BE529CB322F1A19F7193DD1499C9AC463468E79CA0776ABC6B13D656490DB`.

| Actual-client check | Result |
|---|---|
| `map-native` | Exit 0; 8,281 committed readable regions. Full map retained in guest output; transferred result records count and file hash. |
| `snapshot-native` header, repeat | Exit 0; 4,096 bytes each, exact identity and per-chunk hashes. |
| Header plus `0x7FFFFFFFF000` | Exit 3; header retained and unmapped bytes explicitly unavailable. |
| Wrong process start / wrong executable hash | Exit 2; no snapshot published. |
| Existing snapshot output | Exit 2; original SHA-256 preserved. |
| `follow-pointer` at main-module RVA `0x1B8`, offset zero | Exit 0; raw pointer equals observed module base; terminal bytes are `4D5A`. |
| Portable pattern search | Finds `4D 5A` at module base. |
| Portable uint64 search | Finds the observed module base in the header. |
| Portable comparison | No changed uint32 windows across the two header snapshots. |
| Portable pointer discovery | Finds root RVA `0x1B8` with `[0x0]`; no index/result truncation. |
| Portable search of partial snapshot | Retains the header hit and explicit unavailable-range coverage warnings. |

The RVA is the PE32+ ImageBase field, derived from the captured PE header,
and its loaded value was checked against module mapping metadata before the
live pointer test. It is a useful acquisition/resolution check, not a player
object, coordinate chain, or generally reusable gameplay offset.

The host reconstructed exact snapshot/follow report bytes from the receipt
and checked their file hashes. Offline commands loaded those actual reports
through the production strict loader. Their own outputs retain exact source
file hashes and query parameters. `receipt.json`, `header.json`, `repeat.json`,
`unreadable.json`, `follow.json`, and the four offline reports preserve the
evidence; request objects and exit codes are inside the receipt. Map requests
and complete map/report files remain in its recorded guest output directory.

Focused tests include real Windows allocated memory for multi-chunk reads and
two-hop resolution, exact-identity rejection, holes, partial bytes, tampered
hashes, output preservation, numeric precision, cross-chunk patterns, rebase
and failed-chain fixtures, work limits, cancellation, and terminal identity
invalidation. See [status](../status.md) for the final full-gate counts/path.
The combined gate passed 238 C# tests, 21 Python tests, 108 Lua assertions,
22 actual Lua/C# cases, and the existing published native smoke. Its published
executable hash exactly matched the RIFT-tested bundle above.

The unchanged V1 VM console, VMCLI wrapper, and private receiver served only
as lab infrastructure. The temporary harness ran from a DVD, then exited.
The original DVD was restored, the owned receiver was stopped, and RIFT was
left logged in. No V1 source, RIFT process memory, REA installation, or global
settings changed. The separate supervised movement trial is recorded in
[experiment validation](experiments-2026-10-19.md).

Limits: bounded sequential reads, main-module roots and aligned x64 pointers
only; selected-range discovery is not exhaustive. Large full-game scans were
not benchmarked. No new game/VM restart, update, crash, snapshot-restore,
loaded-image equality, or native field qualification claim is made for this
bundle. Earlier recovery records identify their own exact executable builds.
