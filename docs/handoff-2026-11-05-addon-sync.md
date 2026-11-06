# Handoff — LLM-coordinated RIFT addon sync (2026-11-05)

**Purpose:** Resume this specific three-installation addon-sync investigation in a later ChatGPT conversation without mistaking matching files for live addon acceptance. This is a dated evidence checkpoint, not an instruction to deploy.

## Resume here

1. Work in `C:\work\riftreader2` through the configured Windows Workbridge connection. Read `AGENTS.md`, `docs/status.md`, `docs/workflows/llm-rift-addon-sync.md` and `docs/workflows/addon-sync.md` first.
2. Check fresh Workbridge health, repository status/HEAD, VMware guest identity and the correct VM-specific cached credential source **on every guest login**. Previous reachability is not proof of current reachability.
3. Keep physical RIFT, RIFT-Lab-1 and RIFT-Lab-2 independent live-testing producers; preserve machine-specific SavedVariables, screenshots, telemetry, logs, and trial edits.
4. **Ask Joey and wait before any `/reloadui`, RIFT client/game restart, host reboot or VM guest reboot.** Do not infer permission from this handoff. A `/reloadui` is a RIFT UI reload, not an OS restart.

## User decisions and boundaries

- Joey chose the active LLM to coordinate sync **on demand**, without a new always-on custom coordinator, scheduler, Windows SMB/network changes, or VMware shared-folder changes.
- OneDrive on both VMs has been unreliable about promptly pulling updates; do not treat cloud syncing or matching timestamps as proof of exact installed bytes.
- Avoid blind three-way mirrors or a universal 'newest file wins' policy. A development repository may intentionally be ahead of an installed live-tested version.
- Addon code deployment requires scoped, reviewed source/target decisions and backups. Never overwrite unrelated addons, RRE/REA repos, character data or installed SavedVariables.
- RRECollector v0.4.11 is handled by **a different RRE conversation**. Do not change or reload RRECollector as an incidental addon-sync test; coordinate if that owner requests it.

## Observed environment

- Windows host: `AMD-DESKTOP`; VMware guests: `RIFT-LAB-1`, `RIFT-LAB-2`.
- Installed AddOns are under `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns` on each Windows instance. Workbridge 0.16.4-dev permitted `C:\work` and the full physical `Documents\RIFT` tree; re-check current configuration.
- Existing LabCodex VMware Guest Operations works without enabling HGFS/SMB. Use its fresh per-lab `_session` credential validation. No desktop/game input was needed for sync diagnostics.
- Installed Cloud Files reported Pinned, not Offline, and reparse-backed. These attributes **do not guarantee** that hashing avoids fetching small content from OneDrive.

## Working tools and verified results

| Scope | Command (run from `C:\work\riftreader2`) | Verified state |
| --- | --- | --- |
| RiftReader2 six-file source/installed parity | `C:\Python314\python.exe scripts\addon_sync.py check --target all` | PC, Lab 1, Lab 2 exact SHA-256 matches; no copies needed. Latest observed receipt: `artifacts/addon-sync/20261105T180256Z-e9bb9355/`. |
| Three-machine passive AddOns inventory | `C:\Python314\python.exe scripts\rift_addon_inventory.py --target all` | 48 top-level entries per machine, same names; metadata only, not full file parity. |
| Selected package immediate metadata | `C:\Python314\python.exe scripts\rift_addon_inventory.py --target all --detail-addon ApiAtlas` | Each machine: nine immediate files and one uninspected `fonts` directory. Receipt: `artifacts/addon-inventory/20261105T180356Z-3aee577c/`. |
| ApiAtlas nine-file read-only hashes | `C:\Python314\python.exe scripts\rift_addon_hash.py --target all` | Exit 0 in 25.8s; 27/27 files hashed, identical installed hashes on all three machines. Four files match development, five differ. Receipt: `artifacts/addon-hash/20261105T184359Z-39fee431/summary.json`, plus per-machine JSON. |

### ApiAtlas is intentionally release-separated

- The three installed copies match each other and are documented as **0.3.0**, previously live-checked with RIFT. The development repo `C:\work\API Atlas\addon\ApiAtlas` is **0.4.0-dev.3**, with new collection-feedback behavior still pending live acceptance.
- SHA-256 matches development for `Bootstrap.lua`, `Theme.lua`, `Navigation.lua`, and `Presentation.lua`.
- SHA-256 differs from development for `RiftAddon.toc`, `Version.lua`, `Collector.lua`, `UI.lua`, and `Public.lua` on **all three** installations.
- Bounded read-only semantic diff of the five PC files against the development source passed with their recorded SHA hashes (Workbridge job `apia-semantic-diff-20261105-1`, exit 0). `RiftAddon.toc` and `Version.lua` change only `0.3.0` to `0.4.0-dev.3`.
- `Collector.lua` adds attempted/target/limited bookkeeping, guarded elapsed timing, and protection against stale callbacks; `UI.lua` adds a two-line collection-status footer and availability-aware buttons; `Public.lua` expands `/atlas status` output.
- Project evidence: `C:\work\API Atlas\README.md`, `docs/roadmap.md`, `docs/validation.md`, and `docs/collection-feedback.md`. Source checkout HEAD captured by hash report: `f2b2ce27afa306e80a325c4b197abb1168f22b2f`; last addon-path change `ee612b114a3b8a7cc21856f73b3bcc78a319193f` (Oct 30).
- **Conclusion:** This is an intentional installed 0.3.0 versus development 0.4.0-dev.3 split, **not** evidence of a failed PC/VM sync. Do not deploy 0.4 merely to remove hash drift.
- The `fonts` subtree was excluded from the nine-file hash check. Hash parity does not prove what Lua is currently loaded by the running game.

## Validation and repository state

- Relevant test suites after adding the hash helper: 4 ApiAtlas hash, 20 addon inventory, 8 original addon sync = **32/32 passing**. `git diff --check` passed.
- RiftReader2 branch `codex/modular-foundation` was clean after commit `171b63160878b6ad73eb1d9463adb21eba06561c` (Nov 5, 13:51 EST), before this handoff.
- Key commits: `704f1d3bc8d5247ffde7a1a81b56a7f16869dd73` (guarded ApiAtlas hash tool/results); `171b63160878b6ad73eb1d9463adb21eba06561c` (intentional release split); earlier inventory/safety work is in the linked runbook.
- The independent `API Atlas` repo was already dirty in unrelated files (`README.md`, `api-atlas.cmd`, `tests/test_launcher.py`). Preserve those user-owned changes; the addon source directory had no reported modifications.
- This chat performed no addon copy/deployment, no guest/host reboot, no RIFT restart, no `/reloadui`, no SavedVariables writes, and no RRECollector edits.

## Next priorities — request Joey's direction before any deployment

1. **Controlled 0.4 canary:** If Joey authorizes, make a backup-first plan to stage 0.4.0-dev.3 onto only one explicitly selected lab while keeping the other two 0.3.0 copies as baselines; verify selected files and TOC load order, then **stop for separate approval before any `/reloadui` or restart**. No canary deployment has been approved in this handoff.
2. **Remaining package parity:** Optionally verify the immediate `fonts` subtree on all three machines with bounded metadata/hash checks, preserving the existing untouched files.
3. **Continue on-demand LLM coordination:** Keep inventory → provenance-aware hashes → reviewed backups/deploy → verification as the lightweight workflow for other selected addons. Do not build a long-running sync daemon or mix RRECollector ownership into this lane.

**Do not confuse:** RiftReader2's existing `addon_sync.py` is hardcoded to its own six Lua/TOC files, while `rift_addon_hash.py` is a read-only ApiAtlas nine-file diagnostic. Neither is a generic three-machine file synchronizer.
