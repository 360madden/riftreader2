# RR2 offline A-turn CLI handoff — 2026-11-10 04:33 EST

**Machine:** AMD-DESKTOP (Workbridge confirmed), `C:\work\riftreader2`, branch `codex/modular-foundation`. Joey reported RIFT offline; not rechecked, no input attempted.

## Results pushed
- `234a306`: C# `TurnSkeletonPlanner.AnalyzeAProbe` converts candidate angle before/after + confirmed input/key release into estimated A sign and degrees/sec; rejects contaminated window, stale samples and changed source/epoch.
- `98f76bd`: calibration uses measured key-down/key-up interval (bounded drift), not requested hold or total executor duration.
- `a127428`: offline C# CLI `analyze-turn-probe` reads direct guest `samples.json` before/after and host action `action-1.json`. Requires exact build/module/component/owner, ordered capture/action windows, controller receipt, actual key hold, explicit contamination declaration.
- `75344c4`: CLI checks raw 3×3 F32 bits/decoded cells and candidate angle consistency. **16/16 focused .NET tests passed**; all four commits pushed to origin, no force.
- Existing unrelated untracked energy/anchor files preserved; no VM, game, controller or input changes.

## One offline command (from RR2 root)
```powershell
dotnet run --project src/RiftReader2.Cli -- analyze-turn-probe --before "PATH_TO_PRE_SAMPLES.JSON" --after "PATH_TO_POST_SAMPLES.JSON" --receipt "PATH_TO_ACTION-1.JSON" --matrix primary --uncontaminated true
```
Use `--uncontaminated false` if keyboard/mouse activity invalidated the turn window. Input window status is operator-declared, not independently verified. This command does **not** send game input; matrix candidate angles are not yet actor/body heading.

## Live continuation
1. When RIFT returns, reacquire fresh VM/process/build/controller identity; do not reuse previous PID/ticks/lease. Managed-controller owner drift (`managed-runtime-changed`) blocked earlier native-agent staging. Never replace/bypass ownership.
2. Capture fresh primary/secondary orientation sample and before screenshot. Execute exactly one approved 100ms A under existing screenshot review/lease gates. Obtain real action receipt with keyDownInserted/keyUpInserted and clean STOP/key release; avoid user typing.
3. Capture post sample and screenshot; run the new CLI, inspect candidate delta and rate. Only promote actor facing after independent visual/API changed-state evidence. Calibration is scaffolding.
