# LLM-coordinated RIFT addon synchronization

Decision: Joey, 2026-11-05. The active LLM is the coordinator during a requested
work session. No new background synchronization service, scheduler, always-on
coordinator or unreviewed three-way mirroring.

## Operator intent and safety

- Three active research producers: physical PC, RIFT-Lab-1 and RIFT-Lab-2.
- Preserve machine-specific SavedVariables, telemetry, logs, screenshots,
  experimental addon edits and test evidence. Collect under origin-labelled
  folders rather than overwriting any other machine's live profile.
- Addon code deployment is a separate, reviewed operation. Compare source
  hashes, differences and machine identity before replacing files.
- **Ask Joey and wait for his answer before any RIFT /reloadui, client/game
  restart, Windows session reboot, VMware guest reboot, or helper recovery
  that would restart a client.** File transfers alone do not reload Lua.
- Do not change Windows SMB/firewall/network profiles, VMware HGFS settings
  or the running Workbridge service incidentally. No OneDrive-backed
  synchronization is assumed reliable.

## Immediately working: RiftReader2 package

From `C:\work\riftreader2`, use the installed `C:\Python314\python.exe`:

```powershell
C:\Python314\python.exe scripts\addon_sync.py check --target all
# Only if differences are reviewed and deployment is wanted:
C:\Python314\python.exe scripts\addon_sync.py sync --target pc
C:\Python314\python.exe scripts\addon_sync.py sync --target lab1
C:\Python314\python.exe scripts\addon_sync.py sync --target lab2
C:\Python314\python.exe scripts\addon_sync.py verify --target all
```

The existing tool uses verified VMware Guest Operations through LabCodex,
fresh VM-specific cached credential checks, SHA-256 comparison, staged file
backup and OneDrive file-pinning checks. It sends no game input and never
restarts a guest or reloads RIFT. See `docs/workflows/addon-sync.md`.

**Scope:** This tool manages the six-file `RiftReader2` Lua package only.
It is not yet a generic sync command for RRECollector or the other AddOns
folders. Do not represent a full-machine sync as completed. Before expanding,
inventory package files on all three machines and select the proper source,
destination and per-addon installation contract. For RRECollector, its TOC
must be copied last and its independent package/hash gates must pass.

## Fresh host/guest verification

- Date: 2026-11-05; Workbridge version 0.16.4-dev.
- `check --target all`: exit 0; PC, Lab-1, Lab-2 each passed with no issues
  or updated files. Evidence:
  `artifacts/addon-sync/20261105T170435Z-101fc25c/`.
- `verify --target all`: exit 0; same three targets passed. Evidence:
  `artifacts/addon-sync/20261105T170636Z-95af9d27/`.
- No game, Windows, VM or Workbridge restart/reload.
- File parity is verified; running Lua functionality was not tested.
- VMware HGFS was found disabled in both VM configurations; existing direct
  LabCodex Guest Operations are currently sufficient for this package.
- The physical AddOns folder has 48 entries including disabled folders and
  archives. Do not blindly mirror that full tree.

## Passive three-machine AddOns inventory

Run on demand from `C:\work\riftreader2`:

```powershell
C:\Python314\python.exe scripts\rift_addon_inventory.py --target all
```

This is a metadata-only, one-level inspection, not a sync command. It reads
addon folder names and immediate TOC names, lengths, modification times and
Offline/reparse flags; it never opens Lua/TOC contents, copies addon code,
modifies SavedVariables, reloads a game or restarts a client. Guest reports
are copied from separate guest-local folders using existing LabCodex sessions.
Cloud-backed reparse directories are inspected only if Windows' built-in
`fsutil reparsepoint query` confirms a Microsoft Cloud Files tag and the
folder is pinned and not Offline. Unknown junctions/mountpoints are skipped;
unknown reparse roots fail closed. A cloud tag alone does not prove a file is
locally hydrated. No administrative elevation, network/share reconfiguration,
or OneDrive sync trigger is attempted.

Exit codes: `0` = every target inventoried completely; `3` = tools ran but
at least one target is incomplete (inspect warnings); `2` = one or more
failed targets. A successful inventory proves metadata coverage only.
The report includes machine identity, original root, UTC time, reparse flags,
per-target warnings, and separate raw report paths.

**2026-11-05 live result:** PC, Lab-1 and Lab-2 each returned 48 top-level
entries, `success=true`, `complete=true`, no Offline TOCs, and no differences
in directory/file names or TOC name/length metadata. Eight addons had TOC
timestamp differences: AnotherClock, ApiAtlas, ApiAtlasConsumer, luapad,
RiftApiCollector, RiftReader2, RiftReader2Casting and RRECollector.
Latest three-machine tag-guarded check: exit `0`, all three complete,
48/48/48 entries, no name differences or warnings. Evidence:
`artifacts/addon-inventory/20261105T174204Z-b127ec41/`.
Earlier metadata and timing comparison:
`artifacts/addon-inventory/20261105T172552Z-00c81069/`.
Offline inventory unit tests: **17/17 passed** on 2026-11-05; the existing
addon sync tests separately passed **7/7** (24/24 total).

The command also emits a `tocComparison` with machine coverage and
case-insensitive per-addon TOC drift, distinguishing missing TOCs, bytes,
modified UTC time, Offline and reparse flags. Partially inspected/failed
targets are explicitly excluded; `conclusive=false` means fewer than two
complete inventories were available. Analysis of the saved three-machine
reports identified **seven subsecond-only timestamp differences**
(`modifiedUtcSubsecond`, low significance) and **one whole-second/date
TOC timestamp difference** (`modifiedUtc`: RRECollector, physical PC
versus both VMware labs). There was no TOC filename or byte-size drift.
These signals do not establish which Lua files differ; neither timestamp
class determines which machine is authoritative. RRECollector deployment is
being handled separately. No deployment is implied.
Matching metadata is **not** proof of identical Lua files or loaded behavior.

## Future LLM run sequence

1. Read this playbook, the relevant addon source repository's instructions,
   current target inventory, status, and prior receipts.
2. Inspect every machine's matching addon code and evidence **read-only**.
   Keep each machine's findings and conflicting edits independent.
3. If a supported package has drift, review differences, preserve backups,
   deploy selected files only, then independently verify source hashes.
4. Stop before any required client/VM/game/UI restart and request Joey's
   explicit approval. Record unverified runtime load status until tested.
5. Report per-machine status and exact command receipts; commit only scoped
   source/documentation milestones without touching unrelated work.

