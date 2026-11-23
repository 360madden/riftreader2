# RiftReader2 addon verification and synchronization

The Git-tracked `addon/RiftReader2/` directory is the authoritative Lua addon.
The game loads installed files, **not** files from the Git checkout. The version
label in `RiftAddon.toc` is not a reliable deployed-build identifier; use SHA-256.

## Check the local Windows installation

```powershell
$rr2Host = [Environment]::MachineName
$rr2Python = $env:RIFTREADER2_PYTHON
if (!$rr2Python) { $rr2Python = 'python' }
& $rr2Python -B scripts/addon_sync.py check --expected-host $rr2Host
& $rr2Python -B scripts/addon_sync.py verify --expected-host $rr2Host
```

Run from the checkout with the configured Python. Check and verify default to
the local PC and use Windows' Documents known folder, including OneDrive
redirection. Pass `--pc-folder PATH` if RIFT uses another local addon directory.
Exit code 2 identifies a failed installation or host check.

The `sync` action changes installed files and requires an explicit target.
For a reviewed local deployment, use `sync --target pc --expected-host $rr2Host`.
The historical `lab1`, `lab2`, and `all` targets select the old VMware workflow
explicitly. When several targets are selected, each gets its own result.

### Inspect addon metadata

```powershell
& $rr2Python -B scripts/rift_addon_inventory.py --expected-host $rr2Host --detail-addon RiftReader2
```

The inventory defaults to the local Windows Documents folder and reports file
attributes without opening addon content. For a custom installation, pass its
`AddOns` directory to `--pc-folder`. A partial inventory exits 3 and lists the
directories it skipped. The selected addon's metadata appears under
`detailFiles` when the directory could be inspected.

## Installation and guarantees

- **PC:** `RIFT\Interface\AddOns\RiftReader2` under the current Windows user's
  configured Documents folder.
- **Lab 1/2:** Each guest's `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2`.
  VMware access is through `LabCodex._session` and `GuestSession`, rechecking
  that VM's own cached credentials for every login. No cloud Codex CLI call.
- All seven `RiftAddon.toc`, `wire.lua`, `producer.lua`, `reference.lua`,
  `live.lua`, `guidance.lua`, and `main.lua` files must match the exact source hashes.
  The manifest enforces the load order, including `guidance.lua` before `main.lua`.
  The report lists mismatches explained by LF or CRLF in `lineEndingOnly`.
  Those files still fail exact byte verification.
- `check` and `verify` first inspect Offline, Pinned, Unpinned,
  RecallOnOpen and RecallOnDataAccess flags. They skip hashing files explicitly
  flagged for cloud recall and report `cloud-recall-risk` without changing
  the installation. Regular local files can pass check and verify based on
  their hashes. A pinned cloud reparse file can still require hydration:
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

1. After changing the Lua addon, run the read-only check on the intended installation.
2. Deploy only when the target game's addon can be safely reloaded and no
   controller action is in progress. Run `sync` on the affected target(s).
3. Run `verify` for the installations you checked. If any target fails, preserve the report and
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
hydration** is required. Use the [metadata inventory](#inspect-addon-metadata).

Both VM guests and the main PC may sync portions of
their Documents folders through OneDrive. A cloud sync conflict can produce
extra files or placeholders. Never assume a write to one installation has
correctly updated the other two; verify each guest independently. The script
does not delete other addon files or resolve unrelated OneDrive conflicts.
