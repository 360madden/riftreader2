# Modular offline foundation validation

Date: 2026-10-18 (America/New_York). Scope: RiftReader2 only.

User authorized modular architecture and foundation implementation, configurable
upgrades, repository-local Git identity, and efficient future model handoffs.
The first built slice is offline synthetic evidence analysis.

## Observed checks

Command: `pwsh -NoProfile -File scripts/validate.ps1`.

- Locked restore passed using SDK 10.0.302 and the committed package versions.
- Release build passed with zero warnings/errors and warnings treated as errors.
- 75 tests passed, covering numerical semantics, wraparound, gaps, invalid
  data/order/session, cancellation, input bounds, configuration, hashes,
  publication/no-overwrite, CLI argument errors, and report schema/provenance.
- `dotnet format --verify-no-changes` passed.
- Dependency graph checks passed for all four production projects.
- CLI capture validation and two independent replay invocations passed. Their
  saved report SHA-256 values matched.
- The independent synthetic expectations passed: 5 samples, 1 missing sequence,
  1 sequence-gap interval, 1 timing-gap interval, 2 derived intervals, 2 skipped
  intervals, maximum horizontal speed 5 units/s and absolute yaw rate 1 rad/s.
- Relative documentation links, working/staged Git whitespace checks, and
  explicit text checks including new untracked source files passed. NuGet-owned
  lock files retain their generated no-final-newline format.

Initial integrated result files:
`artifacts/validation/20261019T004240Z-280f3fc9/analysis.json` and `replay.json`.
Final result files after provenance/schema review and 75-test validation:
`artifacts/validation/20261019T004807Z-d38f8077/analysis.json` and `replay.json`.
The final check resolved all 89 relative documentation links.
The directory uses UTC for its identifier; the local review date is October 18.
Later runs create fresh directories and preserve prior evidence.

## Limits

This verifies the offline foundation and synthetic data only. No V1 wall-motion
reproduction, native RIFT field, running game, restart/update recovery, capture
completeness, or throughput benchmark was qualified. Build SHA-256 in a manifest
is declared provenance, not independent proof of the source executable.

V1 was read-only reference. No original application source was imported.
No global settings, runtime tool installations, remote repositories, or game
state were changed. SDK/package pins are controlled upgrade points, not claims
that these versions will always be current.
