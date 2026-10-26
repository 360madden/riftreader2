# Casting workflow handoff — 2026-10-26

## Resumed workflow result — supersedes pending instructions below

The bounded dummy test **passed** after this handoff was saved. `record-04` /
`cast-04` produced one Aggressive Block damage event of **118**, matching player
`u035400012FA2D207`, dummy `u80000001EB003765`, and modern ability
`A6663BAE96C8E85E6` through `Event.Combat.abilityNew`. Final verdict is
`intended-hit-confirmed`; the raw legacy ID is retained too. The 60-second trial
contains 565 samples. Power was **100 -> 80 -> 100** and health stayed **18208**.
Cooldown Begin reported 1.5 seconds at frame time 13054.46484375; End arrived at
13055.978515625 (1.513671875 seconds). The readout observed waiting then readiness.
Separate autoattack events do not count as Aggressive Block hits.

`stop-secure-04` stopped autoattack; `flush-trial-04` shows the character out of
combat and the finished successful verdict. Saved evidence is
`artifacts/casting-20261025-01/trial-evidence-04/evidence.lua` and `.json`.
The successful trial used deploy-10. Deploy-11 adds a narrow fail-closed guard
for contradictory modern/legacy event IDs; its regression suite passed and the
files were hash checked and reloaded. No further offensive test is needed for this
increment. No full-game restart, ranged ability, moving target, channel, or
general facing/line-of-sight validation is claimed. Next useful increment is a
separately scoped ranged ability with its own cooldown; patch recovery stays
deferred. Full gate passed: 514 .NET tests, 849 Python passes/two skips, contracts,
format, published-reader smoke and 619 links. Final focused suite: 30/30 including
the extra ID-conflict regression. Gate: `artifacts/validation/20261026T045106Z-525cce97/`.
Export: `artifacts/exports/casting-dummy-20261026-01/` with report, JSON summary,
CSV samples, raw evidence archive and archive SHA256. No credentials/private arm
receipts are exported. Final controls are disarmed, idle and released.

The sections below preserve the detailed handoff as written before resuming,
including unsuccessful attempts and operational instructions. Treat references
to a pending cast as historical; start future work from this result and current
status, with fresh identities and screenshots.

## Objective and authority

Finish the user-authorized casting readout and one offensive ability test on a
training dummy, account for cooldowns, and prove the intended target received the
selected ability. Reuse RIFT's API and existing guarded helpers. The user asked
for this detailed handoff before resuming. Work in `C:\work\riftreader2`.

Model preference: Astra / High is the last user-confirmed selection. Remind the
user each response; do not claim independently verified runtime model metadata.
Keep the work practical. Patch recovery and controlled player-health-loss tests
remain deferred. Direct ChatGPT Computer Use inside RIFT remains deferred; the
separately authorized guarded VM-console helper is allowed. The user released
guest controls. Recheck fresh identity, foreground, screenshot, queue ownership,
arm and release for every input. Reuse cached guest login through
`scripts/vmware_guest_session.py`; no credentials in chat or artifacts. VMware
Tools is the transfer route; leave NAT alone. No memory writes/injection.

## Current code and deployment

Baseline commit `92e3dd2` added the optional addon and initial tests/documentation.
Current uncommitted changes are `addon/RiftReader2Casting/main.lua`, `model.lua`
and `tests/test_casting_addon.py`. Preserve them. Latest guest deployment receipt:
`artifacts/casting-20261025-01/deploy-10/deployment.json`; each file hash was checked
after VMware Tools copy. `load-fix-03` reloaded that build in RIFT.

The addon is now recognized, enabled, and visibly running. Initial discovery
failed because TOC Email metadata was omitted. Comparing working addon manifests
identified and corrected that omission; this is no longer a blocker.

The model uses ability list/detail, unit lookup/detail, castbar, cooldown events,
and combat events. It checks living player/target, exact effective target, range,
cooldown, cast/channel state, usability and required resource. Facing and line of
sight remain unverified until a successful result. No assumed fixed GCD sleep.
The effective cooldown is labeled ability/GCD because it is not a separately
qualified global-cooldown clock.

Current controls:

- Abilities selects a known nonpassive, nonpositioned, non-autoattack ability.
- Record 60s starts observation only, pins player/target/ability IDs, and retains
  up to 630 samples, 64 combat events and 64 cooldown events. Countdown is visible.
- Cast invokes RIFT's restricted secure `EventMacroSet` with `cast <ability name>`
  only on a physical click. Configuration is refused during secure combat or an
  active trial. No automated retry, timer-based casting, or rotation.
- Stop autoattack is a separate restricted button with the `stopattack` macro.
  It worked live: the character left combat while still within melee range.

The cast button itself does not enforce the diagnostic readiness checks; the
supervised helper must review the live panel before clicking. The game enforces
its own ability restrictions. Do not describe this as a finished combat engine.

## Findings and failed trials retained honestly

Artifact root: `artifacts/casting-20261025-01/`.

1. Discharge was unusable despite full Power and zero cooldown; it was not cast.
2. Aggressive Block reports 3m melee range and 20 Power cost. It was initially
   blocked as out of range. Reviewed 250ms W pulses reached API-reported readiness.
   `approach-02` and `approach-04` delivered/released; declined or expired reviews
   did not move. `approach-05` was declined because already in range.
3. Trial 1 (`record-01`, `cast-01`, `trial-evidence-01/evidence.lua` and `.json`):
   Power 100 to 80, effective cooldown Begin 1.5s then End about 1.504s later;
   player health stayed 18208. A 118-damage Aggressive Block event matched player
   and dummy but used legacy ID `a000000006663BAE9`. Selected API ability ID was
   `A6663BAE96C8E85E6`. Initial normalization failed, so original verdict remains
   `no-matching-damage-observed`; do not rewrite this historical verdict.
4. Autoattack followed the ability. An attempted stop at the first action-bar
   slot was mistaken: its tooltip identified Retaliation, not autoattack.
   Preserve `stop-autoattack-01` as a misidentified control, not successful stop.
   A reviewed 250ms S retreat (`retreat-02`) left range. Later the explicit Stop
   autoattack button provided the correct control (`stop-secure-02/03`).
5. Research found that combat events expose `abilityNew`; a working RiftMeter
   source uses it, though generated API documentation omits it. Current code
   retains and prioritizes this exact ID. A conflicting modern ID cannot fall
   back to a matching legacy ID or name. Optional API-detail fallback remains
   guarded; installed legacy `Inspect.Ability.Detail` appears absent. Read-only
   historical mapping probes are retained without changing historical verdicts.
6. Trial 2 (`record-02`, `cast-02`, `trial-evidence-02`) recorded no events because
   the reviewed click arrived just after the 30s deadline. This does not disprove
   the ID fix. Stop autoattack worked afterward. Current 60s window accommodates
   screenshot review overhead and displays remaining time.
7. Trial 3 (`record-03`) began with the 60s build. Pending `cast-03` was explicitly
   declined when the user requested this handoff. No third cast was delivered.
   Let that empty trial expire before a fresh record; do not reuse its review.

Primary implementation reference for `abilityNew`:
[RiftMeter source](https://gist.github.com/Bamux/6bc1062bf3ad49887c9bec642e471271).
Installed-client API docs and inventory are in `runtime-api/evidence.json` and
the saved trial files. These are better current-client evidence than web docs.

## Last observed live identity — must refresh

- VM: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`.
- RIFT PID 12076, process start ticks 639285736860316715.
- Executable: `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`.
- SHA256: `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
- Guest agent instance: `acf21500d6084658a0fce8438bd42cb5`.
- Client size 1211x686; screen origin (0,23).
- Atank, level45 Warrior; player ID `u035400012FA2D207`.
- Selected Normal Practice Dummy: `u80000001EB003765`.
- Last screenshot: in melee range, full Power100 and health18208, no autoattack.

Do not assume these identities remain current. Helper configuration is
`artifacts/xyz-workflow.json`; host private config must not be printed/exported.

## Operational commands and UI locations

Artifact helpers wrap the existing repository tools; source remains under
`scripts/`. Use fresh unique output labels because folders are created once.

`python artifacts/casting-20261025-01/control.py LABEL` captures a read-only
screenshot and status. Add `X Y WIDTH HEIGHT` for one guarded targeted click.
Run click commands with a terminal/TTY so the review prompt accepts input.
They wait 40 seconds for `approve CAPTURE_ID <review reason>`; inspect the actual
screenshot before approval. Expiry/decline yields no input and releases access.
Return the initial screenshot in the same tool call as starting the helper to
avoid losing review time. Never derive approval automatically from capture IDs.

Current client-pixel rectangles, always confirm visually:

- Record: `344 184 60 14`.
- Cast: `350 214 100 14`.
- Stop autoattack: `350 237 100 14`.
- Existing reloadui action-bar macro: `750 647 28 28`.
- Diagnostic overlay Hide, if visible: `710 377 32 18`.
- Ability picker open: `263 182 50 18`; Aggressive Block first entry `275 72 95 14`.

`move.py LABEL` supplies one reviewed 250ms W pulse. `back.py LABEL` supplies S.
Do not move if already ready or if a dialog hides the path. Current character is
beside the dummy, so no movement is expected to be necessary.

`deploy.py LABEL` copies and hashes TOC/model/main through cached VMware login.
Installed addon directory is the guest user's OneDrive Documents RIFT AddOns
folder, not the host workspace. `guest_ops.py` supports staged guest PowerShell
and file retrieval. The exact SavedVariables path can be recovered from its prior
invocation/evidence; do not expose account-specific path details in user prose.
After normal UI reload saves the file, retrieve it as `evidence.lua`, then run
`artifacts/tools/lua-python/Scripts/python.exe artifacts/casting-20261025-01/read_evidence.py PATH`.
This bounded Lua decoder writes sibling JSON. SavedVariables are offline
evidence, never a live transport. UI reload is not a full-game restart.

## Validation and next steps

Focused casting suite: 29/29 passed after the current 60s/630-sample changes.
Previous full gate passed at baseline: 514 .NET tests, 837 Python passes/2 skips;
that full-gate result predates current casting edits. Run the full gate before
the final implementation commit: `pwsh -NoProfile -File scripts/validate.ps1`.
Test-only subagent `/root/casting_tests` owns only `tests/test_casting_addon.py`;
its work is complete. Do not start another live controller.

Resume with a fresh read-only capture and confirm stopped, ready, correct dummy.
Let record-03 expire, then Record60s, fresh review, one Cast click, fresh review,
Stop autoattack. Retain the full bounded capture through cooldown recovery.
Verify exact player + target + modern ability ID and positive damage. Preserve
autoattack as separate events, not selected-ability hits. If no confirmed hit,
inspect evidence before retrying; do not loop attacks blindly.

Flush/retrieve raw evidence, summarize Power/cooldown/hit/health and control
release, update this handoff and current status, correct reference documentation,
run full validation, export a credential-free evidence archive, and create a
coherent local commit. No push. Old pending export remains historical at
`artifacts/exports/casting-readout-pending-20261025-01/evidence.zip`; do not present
it as final success. Full-game restart durability of this new casting increment
has not been tested; existing XYZ/Power restart results remain separate.
