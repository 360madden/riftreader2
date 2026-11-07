# Continuation — RR2-owned helper tasks, November 6, 2026

Work in `C:\work\riftreader2`. Read `AGENTS.md`, `docs/status.md`, and this handoff; inspect Git state and reacquire live identities. The prior [standalone handoff](handoff-2026-11-06-console-speed-continuation.md) remains historical context.

## Implemented

`scripts/Manage-RR2HelperTask.ps1` owns Register/Start/Status for four fixed receiver/controller IDs. Its separate RR2 task namespace and local registration verify exact helper entry/arguments, working directory, task settings, current SID and receipt. It refuses a matching legacy task registration in any state, or ambiguous ownership; it never removes or stops one. It binds the exact `pythonw.exe` path but does not independently establish its binary hash or provenance. Scheduler inventory and subsequent start are not atomic across unrelated managers, so the application-level listener, queue and controller ownership checks remain essential.

The receiver/controller entry points now use the RR2 manager. For an **already-running** legacy owner, `scripts/Verify-RR2LegacyHelperTask.ps1` independently reads its task and registration evidence without running Workbridge code or changing its tasks. Receiver reuse additionally requires its existing matching process/config/source receipt. Existing-controller resolution retains unique process, source and config checks before this optional compatibility inspection; new controller startup cannot use the legacy verifier. A changed runtime source remains a blocker, not a reason to rewrite a receipt. No old owner is adopted, stopped or replaced.

On November 6, a read-only `_config`/`_probe` check verified existing Lab 1 and Lab 2 receivers via that compatibility route. It did not verify advancing feed freshness. A pre-edit inspection observed a Lab 1 controller and both receivers running under legacy tasks; those are observations, not reusable identities. No tasks, processes, VM, game or input were changed. New RR2 task registration/start has not been exercised against actual Task Scheduler; mock tests alone do not establish live activation or handoff.

Full local gate `pwsh -NoProfile -File scripts/validate.ps1` passed (exit 0): 380 portable and 301 Live .NET tests, 1,594 Python tests (2 skipped), both isolated helper mock suites, Lua contracts, synthetic native smoke and 1,016 relative links. Evidence: `artifacts/validation/20261107T003537Z-4df8c31c`. The subsequent verifier end-of-file whitespace cleanup passed its mock suite again. Code commit: `94b6687`.

## Continuation

- Preserve every existing legacy task until an explicitly reviewed per-owner handoff. A retained task in any state blocks new RR2 registration/start for that helper. Do not remove it merely to clear the block. For a controller, preserve exact generation, authenticated STOP, key release, supervisor/queue and console cleanup, and confirmed process exit; quarantine if cleanup is unknown. No queue reset or silent re-arm.
- Current controller entry source changed, so an old controller receipt that pins the previous source can fail `managed-runtime-changed`; the read-only legacy task check does not relax this. Retain accessible STOP/release routes and do not claim managed handoff readiness without current exact evidence.
- Runtime acceptance requires a separately scoped safe handoff and observed new RR2 task startup/ownership plus receiver freshness or controller health, as applicable. Do not replay Lab 1 game reload/bind or use old PIDs/nonces. Lab 2 and physical loaded-addon acceptance remains separate.

**Copy-ready resume:** In `C:\work\riftreader2`, read `AGENTS.md`, `docs/status.md`, this handoff and latest commits. Verify current owners and identities read-only. Continue standalone acceptance with an explicitly scoped per-helper handoff that preserves STOP/release and queue protections; never start a competing helper or treat receiver process health as advancing telemetry.
