# Physical waypoint prototype — November 12, 2026

Authoritative checkout: `C:\work\riftreader2`, branch `codex/modular-foundation`.
Active machine: **AMD-DESKTOP only**. Implementation is committed through
`cfe96b8`; no push was performed. User priority: functional first, practical,
existing tools, small focused checks. Avoid turning the prototype into a process.

## Use the working prototype

Double-click `Waypoints.cmd`, or open the tested triangle:

```powershell
Waypoints.cmd --route artifacts/waypoint-triangle-demo.json
```

The launcher selects exactly one local physical client, or requires
`--physical-pid PID` if ambiguous. Startup verifies the movement basis and reads
pose; it sends no input. The default is **Face, then walk**.

- Save Current, enter X/Z, click the player-oriented preview, or Add Target.
- Go Selected visits selected points; Run Route visits the list in order.
- Face Selected turns without walking. Up/Down reorder; Clear empties the list.
- Load/Save Route use `{"waypoints": [["name", x, z]]}`. Add Target saves a fixed
  position, not an entity-follow command; unavailable/stale/different-height
  positions are refused.
- Live pose refreshes while idle and preserves entered coordinates. Actions and
  observations are serialized. Closing waits for cleanup.
- **F8** latches STOP without focus change; the GUI STOP button preserves game
  foreground. CLI Ctrl+C also latches STOP, allowing the native child to release.

For another local tool or Codex, use the same backend directly:

```powershell
python scripts/launch_physical_waypoints.py --check
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid 18092 --run-route artifacts/waypoint-triangle-demo.json --face-waypoints --execute
python scripts/physical_waypoints.py --expected-host AMD-DESKTOP --physical-pid 18092 --face-bearing -5.46 --execute
```

CLI execution requires `--execute`. Its F8 listener must be available before
input starts. Successful CLI receipts retain all named legs and native pulses.
See [the waypoint guide](workflows/physical-waypoints.md) for limits and commands.

## What actually worked

| Trial | Observed result |
|---|---|
| GUI triangle: 13.66 planned units, three points | Completed in approximately one minute; 0.150 units from start; 27 released pulses (14 W, 9 A, 4 D), 3,700 ms requested hold, no target loss. |
| Facing restored after triangle | 0.361° from pre-route bearing, no XYZ change. |
| Add Target → Face Selected | Saved the dummy 6.234 units away without input, then faced it within 0.236° using two A turns; XYZ unchanged and dummy visibly centered. No travel to or attack on target. |
| CLI one-unit outbound and return | One W + two S presses; 0.0102 outbound error, 0.00414 return error; bearing unchanged, releases successful. |
| Programmatic SIGINT during real W child | One bounded helper completed and released; no second pulse, subsequent pose settled. Not a physical Ctrl+C keyboard test. Returned to saved point within 0.0322 units afterward. |
| Earlier STOP/blur trials | GUI F8/click STOP left player stationary; a targeted mid-hold blur trial released and showed zero subsequent displacement, including after focus returned. Windows queue acceptance remains separate from game-response evidence. |

Useful retained evidence:

- Triangle inputs: `artifacts/waypoint-input-7aaf3780a54e4a3da35eb9030dcf56d3.jsonl`.
- Triangle facing restoration: `artifacts/waypoint-run-314b50d1257b4cce97ec8c9c98c5ad4b.json`.
- Target-facing WGC/native bracket: `artifacts/observe-wgc-fe6fe17cdf544e1488bf54ccfbde4935/image.png` and `.png.json`.
- CLI route: `artifacts/waypoint-run-dba8ed0a046c4036a33437a61912766d.json`.
- SIGINT trial: `artifacts/waypoint-cli-sigint-trial.json`; return: `artifacts/waypoint-run-987ffb388789472ab48ee1e6f13ecdc9.json`.
- Additional saved route: `artifacts/waypoint-target-demo.json` (for preview/facing; travel to target untested).

Focused checks passed: **33 Python waypoint tests**, **117 native control tests**,
**21 frame/observation tests**, **14 WGC self-checks**. Native listener checks
covered registration conflict, owned hotkey message, unexpected exit, forced
startup-timeout cleanup and re-registration. A child-process SIGINT test verifies
cleanup completion. No claim of a full-repository gate.

## Closing state and identity

Verified at **03:23 EST / 08:23 UTC**, November 12:

- RIFT PID **18092**, start ticks **639300391441133615**, HWND **919618 / 0xE0842**.
- Executable: `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe`.
- SHA256: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Atank: player key **239816685251645959 / u035400012FA2D207**.
- Settled XYZ **(7424.6748046875, 863.5861206054688, 2946.075439453125)**;
  body bearing **−5.457765305951625°**, measured from +Z toward +X.
- Latest GUI source loaded in **pythonw PID61684**, triangle loaded, Home selected,
  idle with live pose updates. Its zero-input Home check finished 0.184 units from
  that older triangle anchor. Native input ownership was acquired read-only and
  released, and F8 was available after GUI cleanup.
- Final fresh WGC/native bracket:
  `artifacts/observe-wgc-ba6a12d005974ae5b80322a91cc57d8c/image.png` and `.png.json`.
  Both pose reads agreed, and native inspection found no held desktop inputs.
  PlayerSystem bearing also matched body bearing at this settled observation;
  this does not promote its post-turn/freshness semantics to qualified.

These are observations, not reusable authority: reacquire exact identity and
fresh pose before further actions. The initial user-chosen position was preserved
to within the prototype's arrival tolerance after the trials.

## Limits and recovery

This is a **supervised open-ground, current-process prototype**. Route caps:
20 planned units, 64 pulses, 9,000 ms requested hold, 120 seconds. Each translation
segment retains the existing six-pulse/900-ms/12-second limits. Facing is bounded
and checks actual post-release response. A/S/D/W/Q/E work through the existing
native helper; there are no game-memory writes or injection.

The basis in `config/physical-movement-basis.amd-desktop.json` is deliberately
pinned to this process epoch, player and exact executable. Full-game restart
recovery/calibration is **not qualified**; do not edit identity fields to bypass
the refusal. Native pose/projection flags remain candidates. The preview has no
terrain or obstacle model; it cannot find a path around the wall or NPC props.
DotRecast is the researched reuse candidate if suitable RIFT geometry becomes
available; no third-party source was copied.

An earlier GUI-focus STOP left Atank moving into the wall; Joey confirmed no
manual input. The original interrupted receipt was absent, so the exact cause
was not proved. Native release timing, latched blur, owned-window key-up fallback,
GUI no-activate STOP and retained failure receipts now address that failure.
CLI SIGINT no longer raises inside `subprocess.run`, which could kill the native
child before key-up. Listener failure latches STOP; startup timeout requests
shutdown; GUI styles restore in cleanup's finally block.

**Do not activate/restore/drag RIFT through generic Computer Use.** That restored
the maximized game to its stale normal rectangle and broke fresh capture. Use
native move-key focus and the existing WGC observer. Computer Use is fine for
the waypoint window. The BlackBox `Restore-RiftDisplay3.ps1` recovery was reused
under physical reservation on Win32 `DISPLAY5`, 1936×1048 normal-window size,
without restarting RIFT or sending movement input. Current fresh WGC images are
1922×1041, with a 1920×1009 client at frame offset (1,31).

## Preserve concurrent work

Unrelated edits were left unstaged: `scripts/fresh_native_actor_pose.py`,
`tests/test_fresh_native_actor_pose.py`, Application/Domain/Infrastructure
`packages.lock.json`, and untracked `scripts/project_current_native_energy_variants.py`,
`scripts/rank_native_anchor_candidates.py`, `tests/test_rank_native_anchor_candidates.py`.
The index was clean after implementation commits. LEGION and VMs were untouched.

For further work, use the working prototype first. The consequential future gap
is fresh calibration/recovery after a full game restart; terrain routing needs
actual geometry. Neither gap prevents today's demonstrated nearby-waypoint use.
