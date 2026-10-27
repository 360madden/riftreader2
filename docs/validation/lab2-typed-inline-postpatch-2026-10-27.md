# Post-patch typed Lua API recovery — RIFT-Lab-2, 2026-10-27

**Outcome: VERIFIED in covered scope.** On the new October 27 RIFT executable, two independent live read-only native memory scans each saved two complete copies of RIFT API Probe typed frames. All four cross-run comparisons passed the unchanged strict offline `inspect-typed-wire` gate as `advanced-in-covered-scope`. This establishes a **current-build advancing Lua API source**, not native XYZ, Power, movement, or durable pointers.

## Exact Lab-2 scope

- VM: `RIFT-Lab-2` only, VMX `C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx`; no Lab-1 entry, guest game input, reboot, memory write, or module injection.
- Live game: `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, PID **11900**, UTC start ticks **639286946776156559**, SHA-256 **`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`**. Game was still alive with unchanged process-start ticks after both acquisitions.
- Guest reader (new non-overwriting filename): `C:\RIFT_TRANSFER\RiftReader2Live\RiftReader2.Lab2Patch20261027.exe`; 117,037,408 bytes; SHA-256 **`2CC9C42B51394C6B8429E4DFF4BD57FBA321302C01879ED98414859951F888B4`**.
- Both requests used `scout-copy-typed-native`, current build's exact-target identity gate, `startAddress=0x10000`, **512 MiB / 30 s**, **32,768 max enumerated regions**, 128 markers, eight immediate-copy candidates. These are **partial bounded scans**, not whole-process absence or completeness claims.

## Original acquisition and SHA-linked transfer

| Run | UTC interval | Markers / full 28,672-byte copies | Index SHA-256 | Host ZIP SHA-256 |
| --- | --- | --- | --- | --- |
| `04` | 13:25:29.023–13:25:29.697 | 3 / 2 | `CC9F18459006883EC723DA137E716B4E6BD67161635548E68486B343DBADF608` | `60F5DC5BA04FDFC4F10FAE10EC868F0F1FFBD44034E8088142FB8DDC336B933E` |
| `05` | 13:26:24.016–13:26:24.566 | 3 / 2 | `B94943EAB44909930C9C5EF7786DF9D9F4410B191A0BB778F6D1C22A82B6CF4A` | `E30F6AAD0703C7EA8F1DF2F7879664579EDBDDBD29C9FD76E8A99FFFE53C0A5A` |

- Both indexes reported `status=partial`, `reason=byte-budget-exceeded`, **536,870,912 examined bytes**, and no holes in the examined scope. The first run retained one declined marker whose following byte was not an opening brace. Partial is expected at the declared 512 MiB cap.
- Exact guest `run1.zip` and `run2.zip` were copied to ignored host paths `artifacts/lab2-typed-20261027-04-run1.zip` (32,558 bytes) and `artifacts/lab2-typed-20261027-05-run2.zip` (33,679 bytes). Independent host SHA-256 comparisons matched guest receipts.
- The host archive verifier checked each ZIP's `index.json` SHA, schema, request SHA, exact target PID/start/SHA, all referenced candidate request and snapshot SHA-256 values, distinct run times, and safe member names. Extracted originals and four separately SHA-pinned inspector reports reside under `artifacts/lab2-typed-20261027-06-crossrun/`.
- Initial earlier scout attempt with `maxRegionCount=8192` exited without published index and reported `Readable memory region count exceeds the requested limit of 8192 after applying the requested type filter`. Retrying with the **supported** 32,768 maximum yielded the positive scans. This was an enumeration limit, not evidence of missing API frames.

## Strict offline source qualification

| Before (run 04) | After (run 05) | Strict result |
| --- | --- | --- |
| snapshot 01 seq 14436 | snapshot 01 seq 14545 | `advanced-in-covered-scope` |
| snapshot 01 seq 14436 | snapshot 02 seq 14546 | `advanced-in-covered-scope` |
| snapshot 02 seq 14437 | snapshot 01 seq 14545 | `advanced-in-covered-scope` |
| snapshot 02 seq 14437 | snapshot 02 seq 14546 | `advanced-in-covered-scope` |

- Best before/after pair (`capture-01` → `capture-02`): `Inspect.Time.Frame` **9650.2841796875 → 9705.7080078125** (+55.423828125), sequence **14436 → 14546**, stable `playerUnitId` **`u035400012DFEB5BC`**, distinct full producer-wire SHA values, zero coverage warnings.
- API-source player position was unchanged across all four pairs: **X 7160.759765625, Y 821.2099609375, Z 3156.1499023438**. This is evidence of available, advancing **Lua-sourced** coordinates for one apparently stationary player, not a verified native XYZ memory locator or a controlled movement test.
- The strict loader checked each snapshot's full covered segments and chunk hashes; no malformed complete or incomplete candidate fragments were present in selected snapshots. Inspector process exit 0 alone does not constitute positive semantics; its embedded `status` above does.

## Guest Lua producer inventory (installation evidence)

- The game's user-profile Documents folder is OneDrive redirected: `OneDrive\Documents\RIFT\Interface\Addons`. The four present enabled-looking directories include `RiftReader2`, `RiftReader2Casting`, `RiftReaderApiProbe`, and `RiftMeter`; mere presence does not guarantee enabled/in-world loading.
- `RiftReader2` TOC: **0.1.0**, Environment **4.4**, startup `wire.lua`, `producer.lua`, `live.lua`, `main.lua`; all files present and individually hashed.
- `RiftReader2Casting` TOC: **0.2.0**, Environment **4.4**, startup `model.lua`, `main.lua`, character SavedVariable `RiftReader2CastingEvidence`; both files present and individually hashed.
- `RiftReaderApiProbe` TOC: **0.6.0**, Environment **4.4**, startup `main.lua`, `readiness.lua`, `validation.lua`, `capabilities.lua`. Installed `validation.lua` SHA-256 **`618CA4443986E8C683CBEE51C92D0992296E125E4BA387AF3C99F86B2E1853FF`** matches the previously documented producer. The verified typed frames supply separate, stronger runtime source evidence.
- Probe TOC and file inventory original is retained under ignored `artifacts/lab2-patch-addon-manifests-20261027-02.json`. No addon deployments or edits occurred in this check.

## Next work and limits

1. Use these qualified current-build Lua XYZ numbers to seed the **existing** bounded read-only `scout-values-native` float32 candidate search, with the **new exact build SHA and process epoch**. A scalar hit or adjacent memory pattern remains candidate-only.
2. To identify native player XYZ, require close-in-time rereads and a separately observed position change across multiple axes; reject unrelated copies, stale cache, and static memory. Never import the prior executable's RVA `0x32E0200`, old `+0x320/+0x324/+0x328` offsets, or old position/power profiles.
3. A live GUI capture/control path on Lab-2 remains unverified. The installed `vmrun -interactive` option is a potential **separate** diagnostic to assess without modifying game state.
4. Patch resilience, game restart recovery, native resource fields, pathfinding and casting were **not** proved by these snapshots. Preserve exact original ZIP/index/capture hashes for later verification.
