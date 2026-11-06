# Addon synchronization — three RIFT installations

The Git-tracked `addon/RiftReader2/` directory is the authoritative Lua addon.
The game loads installed files, **not** files from the Git checkout. The version
label in `RiftAddon.toc` is not a reliable deployed-build identifier; use SHA-256.

## Commands (main Windows PC, from `C:\work\riftreader2`)

```powershell
C:\Python314\python.exe scripts\addon_sync.py check --target all
C:\Python314\python.exe scripts\addon_sync.py sync --target lab2
C:\Python314\python.exe scripts\addon_sync.py sync --target all
C:\Python314\python.exe scripts\addon_sync.py verify --target all
```

Use `--target pc|lab1|lab2|all`. The `--pc-folder PATH` option is for a
different local RIFT Documents location. Targets are processed independently,
and an error on one does not suppress the others. A nonzero exit code means at
least one selected installation is not verified consistent.

## Installation and guarantees

- **PC:** Current Windows user's `OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2`.
- **Lab 1/2:** Each guest's `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2`.
  VMware access is through `LabCodex._session` and `GuestSession`, rechecking
  that VM's own cached credentials for every login. No cloud Codex CLI call.
- All six `RiftAddon.toc`, `wire.lua`, `producer.lua`, `live.lua`,
  `guidance.lua`, and `main.lua` files must match the exact source hashes.
  The manifest enforces load order: `guidance.lua` before `main.lua`.
- `check` and `verify` first inspect Offline, Pinned, Unpinned,
  RecallOnOpen and RecallOnDataAccess flags. They skip hashing files explicitly
  flagged for cloud recall and report `cloud-recall-risk` without changing
  the installation. A pinned cloud reparse file can still require hydration:
  these checks are **best-effort**, not a strict no-download guarantee.
  `sync` compares all files,
  validates staged bytes, preserves displaced files in unique backups, installs
  only missing/mismatched/unavailable ones, pins installed files locally using
  `attrib +P -U`, and independently rechecks each target.
- Guest script and evidence live under the guest's local app-data
  `RiftReader2\addon-sync` folder. Main-PC reports/manifest and backup receipts
  are retained under ignored `artifacts/addon-sync/<run-id>/`; guest backups
  are retained outside the RIFT addon folder in the guest's same local area.
  Offline OneDrive placeholders are instead renamed to uniquely named
  `.offline-backup-*` siblings inside the addon folder, avoiding the provider's
  refusal to move unhydrated placeholders out of its sync root.
  Do not delete backups before confirming a functional game reload.
- The workflow fails closed on missing destination, changed load list,
  non-matching staging, offline files, failed pinning, hash mismatches, guest
  identity change, or an unavailable guest credential. It never resets a VM,
  stops RIFT, manipulates a game input controller, or reloads the UI.

## Required sequence

1. After changing the Lua addon or restoring/rebooting a VM, run `check --target all`.
2. Deploy only when the target game's addon can be safely reloaded and no
   controller action is in progress. Run `sync` on the affected target(s).
3. Run `verify --target all`. If any target fails, preserve the report and
   do not start a live movement experiment using that addon.
4. **Ask Joey and wait for approval before any RIFT UI reload**, then use
   the existing reviewed console workflow (or reload manually).
   A file-level PASS does **not** prove successful Lua initialization. Check
   for addon load errors, then use `/rr2guide status` as an independent live
   smoke test. Existing nonce/session bindings must be reacquired afterward.
5. Before each live test, repeat a read-only `check`, especially when the
   addon lives in OneDrive. Cloud Files can revert a formerly readable file to
   an Offline placeholder independently of Git changes.

**Operational caution:** The safe-attribute check avoids known cloud-recall
flags before hashing, but the Windows cloud state may change before opening
a file. Do not run a content-hash check when **zero possibility of OneDrive
hydration** is required. Use metadata-only `rift_addon_inventory.py` instead.

Both VM guests and the main PC may sync portions of
their Documents folders through OneDrive. A cloud sync conflict can produce
extra files or placeholders. Never assume a write to one installation has
correctly updated the other two; verify each guest independently. The script
does not delete other addon files or resolve unrelated OneDrive conflicts.
