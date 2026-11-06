# Targeted Light's Balm click — October 25, 2026

**Implemented, deployed and live demonstrated.** One screenshot-reviewed click
on Light's Balm in action-bar slot 7 produced Lua Power **100 → 81 → 87 → 100**.
Health stayed **18208/18208**, and all retained Lua positions were unchanged.
This validates the intended button/action response in this trial, not universal
UI reliability or a native Power locator.

## Change

The ordinary mouse path can recenter an edge cursor for camera motion. The new
optional `clickTarget` path selects a reviewed client-pixel button rectangle,
positions at its center and checks window identity/geometry and cursor location
immediately before button-down. A one-pixel tolerance permits tiny rounding;
larger drift rejects the press. Targeted input cannot contain keys, relative
movement, wheel or a right click. Clipped/invalid rectangles are rejected.

The host requires an authenticated guest capability before forwarding this new
contract, preventing old agents from silently ignoring the rectangle. The
reusable `scripts/run_targeted_click.py` retains the existing identity, lease,
screenshot-review, arm, stop and release workflow. Movement/camera inputs are
unchanged. No input blocking or unattended spell loop was added.

## Live evidence

- Trial: `artifacts/targeted-click-20261025-01/power-click-01/`.
- Client rectangle: X **610**, Y **650**, width **26**, height **24**.
- Client origin: screen **(0,23)**; dimensions **1211 × 686**.
- Cursor began at screen **(1210,29)** and was deliberately placed at
  **(623,685)** inside slot 7. It did not recenter to the game-window middle.
- The guest recorded `targetedClickPositionVerified` at **23:35:01.9416391 UTC**,
  button-down at **23:35:01.9470849**, button-up at **23:35:02.0609202**.
  These are insertion timestamps, not exact game-consumption timing.
- The fresh after-image shows Light's Balm's tooltip and a casting pose.
- Six collection rounds returned **88 verified files**. Reviewing all retained,
  validated Lua frames recovered the Power dip and recovery; the final frame
  alone would miss it. Typed combat status is unavailable, not inferred false.
- Final state: disarmed, idle, no sampled held inputs, no recovery journal,
  coordinated host ready, clear queue and sole console ownership.

The old native candidate `0x202DBECE9C8` read **0** while Lua baseline Power was
**100**, then yielded **86, 98, 100** later. It is not a reliable current-Power
field in this run. Its owner remains unresolved and it may be a Lua/addon copy.
Do not promote it or describe this run as native/Lua equality validation.

## Deployment and checks

- Host **V22**, PID **76024**, replaced V21 after verified idle cleanup.
- The old guest helper exited by normal console cancellation. The new helper
  was launched in the existing interactive desktop with the reused private
  configuration; cached VMware guest credentials required no new prompt.
- Guest executable SHA-256:
  `7DE428BEB304241ED5C30FC0DEEA93266146D501BA731D117693810867A319BE`.
- RIFT remained PID **1224**, start ticks **639285359295548343**, executable SHA
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
- A large binary copy exceeded the original timeout; the longer bounded copy
  and guest hash verification succeeded. Use the existing
  `artifacts/tools/control-python/Scripts/python.exe` for VM-console bootstrap;
  system Python lacks its dependencies. Short staged Windows Run launchers
  worked; the initial long command did not establish launch completion.
- Full repository gate passed: **484 .NET tests**, **814 Python tests** with
  **2 skips**, Lua/C# contracts, formatting, dependency checks and smoke tests.
  Evidence: `artifacts/validation/20261025T232357Z-e126f7c8/` and
  `artifacts/targeted-click-validation-fixed.log`.
- Focused checks cover drift, clipped/invalid rectangles, mixed-input rejection,
  older-agent rejection before dispatch and capability-aware delivery.

Export: `artifacts/exports/targeted-click-20261025-01/evidence.zip`, **19 files**,
**3,063,989 bytes**, verified SHA-256
`BB9D37FD076DEDEE9D44D0F418CC449072D990B75C47180E1B37734CA9171711`.
The export excludes the private arm token and contains original capture evidence,
the click receipt, all validated Lua frames and the offline review.

## Limits and next use

Select the rectangle from a fresh screenshot; UI rearrangement requires another
review. Physical input is not locked out, and a small check-to-insertion race
remains. One successful click does not establish arbitrary spell automation.
Sampling does not measure the exact spell cost, minimum Power or regeneration
rate. Health-change testing and patch recovery remain deferred. This update
did not restart RIFT and makes no new full-game restart claim.
