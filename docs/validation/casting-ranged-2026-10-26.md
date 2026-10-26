# Light's Decree ranged-reach validation

Validated 2026-10-26 using normal Chat Workbridge assistance for ability selection
and saved-evidence review; the coordinator alone performed deployment and guarded
live input. Patch recovery and controlled health-loss testing remain deferred.

## Result

The updated casting addon 0.2.0 was deployed through cached-login VMware Tools.
Guest hashes matched the three source files. The new range/cast/channel rows and
moved controls were visible and usable without overlap. Source remains unchanged
from `0b097f5`; the prior full gate passed 514 .NET and 861 Python tests/two skips.

Light's Decree (`A6B8B16CD6F8B3DB9`) reports rangeMax 20, costPower 20 and a
12-second cooldown. Its description explicitly identifies damage. Its API
`weapon=melee` remains intact: this validates **ranged reach**, not ranged-weapon
classification. Missing minimum range, cast time and channel state remain unknown.

| Observation | First recorded attempt | Second recorded attempt |
| --- | --- | --- |
| Exact selected-target outcome | Dodge; no ability damage | 402 Life damage |
| Samples over bounded 60s window | 565 | 560 |
| Power start/minimum/end | 100 / 80 / 100 | 100 / 80 / 100 |
| Cooldown Begin to End | 12.009766s | 12.005859s |
| Derived XYZ distance, constant throughout | 3.593105 | 5.178950 |
| Autoattack events | 9, excluded | 0 |
| Final readiness | observed-ready | observed-ready |

Exact player ID was `u035400012FA2D207`, selected Normal Practice Dummy ID
`u80000001EB003765`. The successful damage event at frame-clock 19791.587890625
matches those IDs and authoritative `Event.Combat.abilityNew`, not just names.
Three other dummies took 243, 243 and 240 damage from the same area ability;
these events correctly have `matchesTarget=false` and are excluded from the
402-damage result. Player health stayed 18208 throughout both captures.

The first attempt was investigated before a separately recorded repeat. Its exact
target dodge was retained; unrelated autoattack damage was not misclassified.
The final UI wording `no-matching-outcome-observed` is imprecise for this case:
raw dodge evidence exists, although no positive damage/healing outcome exists.
Keep this as a small follow-up to improve the displayed reason, not a reason to
weaken exact-ID matching.

## Identity and preservation

RIFT PID 12076, start ticks `639285736860316715`, SHA-256
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
Guarded clicks checked current foreground identity, screenshot, exclusive access,
arm and release. Stop autoattack was used after each attempt; evidence retrieval
records the controller disarmed, idle, no held inputs and no recovery required.

Deployment: `artifacts/casting-20261025-01/ranged-deploy-01/deployment.json`.
Raw first/second evidence: `ranged-evidence-03/` and `ranged-evidence-04/` under
that same casting artifact directory. Both untouched SavedVariable Lua files,
bounded decoder JSON, sample CSV, combat events, reviewed screenshots, sanitized
identity/action receipts and SHA-256 manifest are exported under
`artifacts/exports/casting-ranged-20261026-01/` (`report.html`, `report.json`,
`evidence.zip`). Private arm/configuration files are excluded.
Normal Chat worker receipts: `artifacts/casting-ranged-20261026-01/`.

One retreat request (`ranged-retreat-04`) expired before action and failed closed;
subsequent fresh status confirmed stopped/released/idle before another bounded
request. Two staging-script retrieval attempts failed; the existing direct file
copy route succeeded using the discovered exact SavedVariable path and cached
guest credentials. No password prompt or networking changes were needed.

## Limits and next useful work

Derived coordinate distance is not a calibrated hitbox-range boundary. The
successful hit verifies this attempt reached the intended target; general facing,
line-of-sight, independent GCD and cast/channel timing are not qualified. This was
UI reload and evidence preservation, **not full-game restart validation**.

Next practical increment: show exact-target avoidance outcomes clearly, then use
the existing API to select a non-area ranged attack or a real cast-time ability
for a separately bounded trial. Do not build a rotation or timed retry loop.
