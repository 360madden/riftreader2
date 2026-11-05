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

