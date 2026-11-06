# RiftReader2 runtime reconciliation — 2026-11-04

This is an **observed runtime checkpoint**, not a blanket live-telemetry or movement qualification. It reconciles the 2026-11-01 Lab2 movement handoff with changes visible on 2026-11-04, approximately 22:23–22:31 UTC. Source project: `C:\work\riftreader2`, branch `codex/modular-foundation`, baseline commit `ec132754d378d78dc3e639b4f719c68473c6fe95`.

## Verified environment

| Surface | Observation | Qualification/limit |
| --- | --- | --- |
| RR2 Git | Clean at initial and pre-documentation checks; prior handoff is committed as `ec132754`. | No RR2 source changes were required for this audit. |
| Workbridge | `0.16.4-dev`; reports 36 global command jobs and 36 coordinated worker assignment slots; configured roots include `C:\work`, `C:\rift modding`, and physical-PC addon/screenshot folders. | Assignment slots are **not** independent AI reasoning agents. |
| Developer stack | `C:\Python314\python.exe` reports Python 3.14.6. `C:\Program Files\dotnet\dotnet.exe --version` returned `10.0.302`, matching `global.json`. | Full PowerShell/.NET/Lua validation gate was not rerun. Workbridge did not resolve `pwsh` or the conventional PS7 install path; do not infer PS7 is absent system-wide. |
| Physical-PC RIFT | `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe` exists, 60,493,640 bytes, SHA256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. No physical `rift_x64.exe` process appeared in the 22:27 UTC host tasklist snapshot. | Exact installed binary remains the prior pinned build; not proof the physical game is loaded or current beyond the snapshot. |
| VM Lab1 | VMware PID **44308**; guest RIFT PID **1952**, started **2026-11-04 14:57:17 EST**, installed `C:\RIFT_TRANSFER\RIFT\rift_x64.exe` SHA256 **1935A05C...**. | Fresh runtime epoch; reject historical process addresses, reader nonces, and session pins. |
| VM Lab2 | VMware PID **20020**; guest RIFT PID **11572**, started **2026-11-03 06:58:02 EST**, same installed executable SHA256 **1935A05C...**. | Historical November 1 PID 7012 is obsolete. |
| RR2 Lua addon | `scripts/addon_sync.py check --target all` **PASS exit 0**; physical PC, Lab1, Lab2 all matched all six source files with zero reported issues. | No sync/deploy/reload occurred. Hash agreement is **not** evidence of actual in-game addon initialization, binding, or freshness. |
| Static control fleet | `control_fleet.py --manifest artifacts/control-fleet-live/fleet.json` **PASS exit 0**, two configured, noncolliding lab endpoints. | Static configuration only. |

## Controller reconciliation

The **initial read-only** `control_client.py --no-auto-start status` found Lab1 host HTTP responsive but `connected=false`, `coordination.state=waiting`, console reservation held and supervisor absent. Lab1 guest process inventory showed RIFT present but no command containing RiftReader2/managed-fleet/guest-control naming. Lab2 was connected/ready, supervisor running, RIFT foreground, disarmed/idle with no sampled held inputs.

Used the existing **on-demand** recovery for **Lab1 only**: `python scripts/ensure_guest_agent.py --lab lab1`, Workbridge job `rr2_recon_safe_recover_lab1_20261104`, **PASS exit 0** at 22:29:48 UTC. It reported `state=started`, `hostConnected=true`, `coordination=ready`, `consoleHeld=true`, `guestDisarmedIdle=true`, RIFT PID1952. This is the existing managed task/guest-agent path, not a VM restore, game restart or input experiment.

Both subsequent independent `--no-auto-start status` checks passed at 22:30:55–57 UTC:
- **Lab1:** connected, ready, supervisor running, console reserved, RIFT PID1952/SHA1935A05C..., **isForeground=false**, unarmed/idle, no sampled keys, no recovery required.
- **Lab2:** connected, ready, supervisor running, console reserved, RIFT PID11572/SHA1935A05C..., **isForeground=true**, unarmed/idle, no sampled keys, no recovery required.

No actual player XYZ, cast/HP/Power, qualified reader nonce, addon session, stable post-action feedback or current accepted goal calibration was established. Reader/receiver process existence alone never qualifies the live feed. The 2026-11-01 Lab2 two-W-pulse `elapsed-budget` / stalled-addon-sequence failure remains historical and unresolved.

## Cross-repository change inventory (inspection only)

| Repository | Observed drift | Boundary |
| --- | --- | --- |
| `rre` | Active Nov4 spellcasting/RRECollector research; dirty task JSON and untracked backup/probe files. | Preserve its changes; do not copy its controller or overwrite RR2. Reuse only appropriately source-hashed native findings. |
| `REA-Lab1` | New Ghidra and iced-x86 exact-byte helpers, modified handoff/task board and untracked native analysis. | Candidate native research only; no same-object/field promotion without independent evidence. |
| `Rift API` | Modified Desktop/UI files and untracked evidence export. | Independent project; no RR2 integration implied. |
| `AutoFight` | Clean; independently porting RR2 reader/telemetry for standalone runtime. | RR2 remains its **reference**, not its live runtime dependency. |
| `workbridge-mcp` | Active Nov4 MCP/Desktop investigations and modified FreeBuff ConPTY probe. | Shared bridge provides current access; do not change service/settings incidentally. |
| `LuaPadModern` | Separate active addon/logging work on Nov4. | Possible UI reload or addon interaction requires new session binding; no direct conflict proved. |

## Current safe resumption priority

1. Preserve this checkpoint. Keep current controller owners, queue, VM processes and user game state intact.
2. For read-only discovery, use existing VM-specific authenticated guest tools; do not require game foreground merely to inventory the current executable or files.
3. Before live telemetry, establish exact **current** game, reader, receiver, addon nonce/epoch/player identity and independently advancing receipts. Inspect receiver/scanner performance and addon publication stall from saved evidence first.
4. Lab1 is **not foreground** at final check. Do not bring it forward or send game input without the normal reviewed foreground/control/lease workflow. Lab2 is the better currently foreground lab, but no fresh source is qualified.
5. Before goal-directed movement, run a new exact-reader qualification; do not reuse November 1 live-session pins or calibrations as active authority. Observe feedback health before bounded movement and verify STOP/release and final XYZ.
6. Keep RRE/REA/AutoFight/workbridge write ownership separate and coordinate any reloads or OneDrive addon changes with fresh RR2 nonce binding.

## Retained evidence / commands

- Source/guest addon compare: `rr2_recon_alladdon_20261104`; ignored report `artifacts/addon-sync/20261104T222354Z-c0562e8e/`.
- Guest RIFT identity reports: `artifacts/reconciliation-20261104/lab1-game-55552b17aa5e.json` and `lab2-game-0ef232aa424c.json`; original VMware guest file probes were hash-bound to the running VM identity and copied to ignored host evidence.
- Guest presence: `rr2_recon_20261104_probe_lab1`, `rr2_recon_20261104_probe_lab2`; controller pre/post: `rr2_recon_20261104_controller_lab1/lab2`, `rr2_recon_postrecover_20261104_lab1/lab2`; static fleet: `rr2_recon_20261104_fleet`.
- The Lab1 recovery request generated ignored artifacts through the existing helper. No source code, other project, addon installation, RIFT client, VM lifecycle, movement/input path, or Git history was changed by the runtime reconciliation.
