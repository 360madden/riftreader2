# Waypoints survival integration

## Physical results on November 14

On AMD-DESKTOP, the physical RIFT client ran as PID 21672, process start 639302305454629980, executable SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. These identifiers describe the recorded trials. Acquire the current identity for a new run.

| Trial | Result |
| --- | --- |
| Current player and catalog | Two nonce-bound Casting 0.4.2 frames advanced from sequence 10 to 18. Atank was a level 45 Warrior with 18,208/18,208 HP and 100 current Power. The API reported 55 learned abilities. The capture contains eight IDs and names on page one of seven. Selected Elite Practice Dummy was level 50 with 3,060,200/3,060,200 HP. Player combat/dead and target relation were absent from this API frame. [Physical telemetry](../../artifacts/survival-first-live-20261114/result.json) |
| Movement with survival monitoring | The guarded approach started 9.316 units from its destination and arrived within 0.213 units. Player HP was 18,208, release succeeded and the pressed-input list was empty. [Guarded approach](../../artifacts/survival-guarded-approach-dummy.json) |
| Pacifying Strike | Native trial 07 confirmed **212 damage** from Atank to the exact selected Elite Practice Dummy. The configured cast ID `A661611602A6D2082` produced the verified effect ID `A70A3925291DD1E14`. The distinct Auto Attack event `A4FDE7DEC3FDF0909` was excluded. Native cast and cleanup both released input. The earlier legacy button trial showed 210 physical damage in the game combat log. [Exact outcome](../../artifacts/survival-native-pacify-positive-07/qualified-outcome.json) · [Native cast and cleanup](../../artifacts/survival-native-pacify-positive-07/result.json) |
| STOP during autoattack | With STOP already latched and raw combat byte 1, the native cleanup click completed, released the mouse and left the pressed-input list empty. The subsequent sample after the eight-second wait reported raw combat byte 0. STOP stayed latched and the release-fault flag stayed false. This qualifies the combined cancel control for this autoattack case. Active cast/channel cancellation still requires a separate observation. [Physical STOP result](../../artifacts/survival-native-stop-acceptance-06/result.json) |
| Headless survival route | With no encounter, the ordinary CLI run completed all three real waypoints over 18.3234 planned units. [Headless route receipt](../../artifacts/survival-waypoint-run-d3d5eb519fc744338dfc70f212562cbb.json) |
| Explicit Resume after a halt | Attempt 01 halted before retreat because its trail contained only completed waypoint positions. Attempt 02 retreated successfully, then halted during rejoin when it used a cached nearest path sample. An explicit Resume finished the saved route at waypoint three. [Attempt 02 checkpoint at halt](../../artifacts/survival-midleg-encounter-progress-02-at-halt.json) · [Resume receipt](../../artifacts/survival-waypoint-run-9bb6c16b50b749e0a13dc80c4b3e8bc9.json) |
| Automatic encounter retreat and rejoin | In trial 03, the native combat guard interrupted at the start of the final leg. The level 45 Warrior treated the level 50 Elite Practice Dummy as unsuitable, canceled autoattack and retreated 9.728908 units over the retained traversed corridor. The player was healthy at the recovery check. The helper automatically rejoined and finished the pending leg without operator Resume. All three waypoints arrived in 28.346 seconds on the shared clock. Final error was 0.127137 units, release succeeded and the pressed-input list was empty. The dummy did not retaliate. [Integrated route receipt](../../artifacts/survival-waypoint-run-1824607962c146c08c9af5621fe69c64.json) |
| Uncertain cleanup in a later run | Trial 04 halted when it could not verify cleanup. A fresh, explicit cleanup verified release. Explicit Resume then completed the saved route. The original cause remains unresolved. The action backend now retains failure diagnostics and prevents a second automatic cleanup click for a failed attempt. [Separate cleanup](../../artifacts/survival-explicit-cleanup-04.json) · [Resume receipt](../../artifacts/survival-waypoint-run-4fcce6701f254662900d4eb3c0bfc049.json) |
| Return along the full walked corridor | Trial 05 handled one real native combat interruption. After retreat, the helper followed the previously walked corridor back to the interruption point before proceeding to the pending goal. Retreat and return together used 18.987737 auxiliary units. The run completed 3 of 3 waypoints in 39.037 seconds with final error 0.208768 units, release verified and no pressed inputs. The event log records travel → fight → retreat → rejoin → travel → completed. A separate offline right-angle case checks that rejoin follows the turn. [Trial 05 receipt](../../artifacts/survival-waypoint-run-8ba1a1565aad434aaa91b55d3da65621.json) · [State transitions](../../artifacts/survival-midleg-encounter-run-05.jsonl) |
| Hostile run 09 | The selected level 13 Coastal Stalker was explicitly hostile. Its Maul events matched the selected attacker and the level 45 player's ID. Sampled native HP reached 18,049 before returning to 18,208/18,208 out of combat. The separately timed API frames reached 18,014. When the selected target disappeared, the run halted with `survival-frame-target-mismatch`. The target-ending race fix passed 76 focused tests. The run did not establish automatic continuation. [Incoming damage and HP](../../artifacts/survival-hostile-20261114/telemetry09.jsonl) · [Run result](../../artifacts/survival-hostile-20261114/run09.jsonl) |
| Explicit Resume 06 | The separate native route-finish fix passed 43 focused tests. Explicit Resume completed all three waypoints with final error 0.205093 units. [Resume receipt](../../artifacts/survival-waypoint-run-d14c38a5a8ed47aca94b5a4a2129a7d2.json) |

## Configure and inspect

Use the Casting addon bound to the physical client. Out of combat, prepare up to eight learned abilities in one diagnostic command. Supply a new 32-character lowercase hexadecimal nonce and the exact ability IDs for this character. Setup clears the old profile slots and publishes the nonce after the secure buttons are prepared. Each ability occupies the slot given by its position in the list.

```text
/rr2surv setup <nonce> <ability-id-1>,<ability-id-2>
```

The secure toolbar is anchored at UIParent X 20, Y 180. Slots use two columns and Cancel/STOP sits at X 20, Y 352. All five deployed addon files matched the source hashes. After reload and setup, the ability buttons and Cancel/STOP were visibly clear of the minimap at the normal 1266×714 client size.

Create a schema-version-1 JSON profile using the same nonce. Set `abilities.damage` to the exact intended damage ID and `actions` to the list of one to eight allowed IDs. Optional heal, defense and interrupt roles accept exact IDs or null. Supply the current host/process/player binding and a measured `coordinateBasis` in `UIParent-to-client-pixels` space with viewport and client dimensions, X/Y scale and offsets. The profile contains no macro text. The addon prepares its own secure controls. [Profile schema and validation](../../scripts/survival_profile.py)

For Warrior Power set `resourceKind` to `absolute-power` and supply `thresholds.recoverResourceAbsolute`. The observed `power` and `costPower` use absolute units. The addon does not publish a Power maximum. Include the schema's health thresholds, `recoverResourcePct` compatibility field, level-delta limit, retreat bounds, polling interval and action deadline. The absolute-Power policy uses the absolute recovery threshold. [Profile fixture](../../tests/test_survival_profile.py)

### Standalone CLI

Run the headless command from the repository with the current physical RIFT PID and your own profile, route and checkpoint paths. The CLI works with the Waypoints GUI closed. Preflight reads current state. Run and Resume require `--execute`. [Headless entry point](../../scripts/survival_waypoints.py)

```powershell
$riftProcessId = Read-Host 'Current physical RIFT PID'
$survivalArgs = @('--expected-host', 'AMD-DESKTOP', '--physical-pid', $riftProcessId, '--profile', 'C:\path\to\profile.json')
$routeArgs = @('--route', 'C:\path\to\route.json', '--checkpoint', 'C:\path\to\progress.json')
python scripts/survival_waypoints.py preflight @survivalArgs
python scripts/survival_waypoints.py run @survivalArgs @routeArgs --execute
```

Press Ctrl+C during execution to request the shared STOP and release owned input. After a stop or a resolved safety halt, explicitly continue the same saved route and checkpoint with `python scripts/survival_waypoints.py resume @survivalArgs @routeArgs --execute`.

### CLI for an open Waypoints helper

```powershell
python scripts/waypoints_cli.py survival configure --profile C:\path\to\profile.json --json
python scripts/waypoints_cli.py survival status --json
python scripts/waypoints_cli.py survival set --enabled on --json
python scripts/waypoints_cli.py survival preflight --json
```

Run preflight with the intended route loaded and player idle. It checks the current telemetry, geometry, ownership and STOP state without sending game input. The live route entry points are `survival run --execute` and explicit `survival resume --execute`. Global STOP latches across the handoff. A route checkpoint advances only after the original route leg arrives. [CLI](../../scripts/waypoints_cli.py) · [Route runner](../../scripts/survival_route_runner.py)

## Interpreting an action

The producer exposes separately configured action rectangles, API ability targets and readiness. A self-targeted slot can report its player effect target while a hostile remains selected. A native click receipt establishes input delivery and release. Exact action verification additionally checks a fresh, matching event after submission, including its sequence, clock, player, selected encounter, effect target and ability ID. Effective damage or healing is retained by ability ID for up to five seconds. The latest diagnostic event can independently report immune, dodge or miss. Confirmed incoming damage from the selected actor to the player has a two-second window. A missing relation or event leaves hostility unresolved. [Addon producer](../../addon/RiftReader2Casting/survival.lua) · [Consumer](../../scripts/survival_live.py)

The current physical profile enables damage only. Touch of Life's ability target still resolved to the selected hostile in the prototype, so the heal role is disabled. Trial 05 qualified automatic route continuation after retreat from the dummy. Run 09 observed exact hostile incoming damage and a return to full native HP. The remaining physical check is a single hostile encounter that handles the target ending, verifies recovery and finishes the pending route automatically. A self-heal effect, XP, level-up and active-channel cancellation also need observed results.
