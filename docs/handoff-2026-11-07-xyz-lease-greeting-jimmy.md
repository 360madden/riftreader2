# RR2 XYZ continuation — Greeting Jimmy coordination, 7 November 2026 (21:12 EST)

## Ownership and cross-chat coordination

- **Authoritative checkout:** `C:\work\riftreader2`, `codex/modular-foundation`; main RR2 coordinator owns Git commits and any VM/game input.
- The independent related conversation is named **Greeting Jimmy** (Joey's exact correction). Its reviewed source report is [xyz-jimmy-findings-2026-11-07-anchor-review-a086.md](xyz-jimmy-findings-2026-11-07-anchor-review-a086.md). Coordinate via the existing [shared packet](handoff-2026-11-07-xyz-greeting-jimmy.md) and reviewed source files, **not** a claim of direct chat messaging.
- The previous 49/49 historical branch-guard check and Jimmy's narrower 26/26 are **historical observations**, not proof of current passive XYZ refresh or a current-world position.
- Preserve Jimmy-owned report and independent RRE repository ownership. Check owner/maintenance leases before live lab activity.

## Verified in this source checkpoint

- New `NativeReadFileLease` uses an exclusive Windows file handle, stable process PID/start/current executable SHA key, and bounded cancellation/timeout. It is held through async native session disposal. Source checks ancestor and final-lock reparse points; final symlink prevention is non-atomic and relies on trusted ProgramData permissions.
- **All 27** registered CurrentBuild standalone sample commands now participate, including the position/orientation/location/paired/zone/vitals family, ability, buff, localization, stats, experience and other current-build routes. The agent's finite input action body also holds the same lease through release/journal handling. Persistent guest `native-vitals` and `native-xyz` captures use the same lease in the **new source** and advertise `nativeReadLeaseVersion=1`.
- Offline real-OS lease tests demonstrated file-share contention, release after abrupt child exit, refusal before opening a second native session, cancellation and session disposal ordering. The new symlink-rejection test **skipped its exercise internally** because Windows denied symlink creation; 887/887 Release .NET tests passed nonetheless.
- Combined .NET10 Release suite: **887/887**, exit0, Workbridge job `rr2-native-lease-full-27cli-20261108-05`. Selected Python XYZ-family suite: **264 run, 262 passed, 2 skipped**, exit0, `rr2-xyz-python-integrated-gated-20261108-04`. `git diff --check` exit0 (CRLF notices, no whitespace error).
- Standalone host wrapper `scripts/sample_current_native_location_pair.py` is currently **source-only**, now pinned to the NEW immutable host-only release `artifacts/native-xyz-lease-20261108-0213z-7b942e6a/publish/RiftReader2.Live.exe`, SHA256 `DCFC17E18A4F361095B5701AB31CDF566664178781E0740FCC8969D2C61957FD` (117966688 bytes) with shared lease source. It has not run in the labs. Host launch command-length/TOCTOU, zone-ID and timeout-receipt guards, plus authoritative same-session capability gating for native-vitals/native-xyz, have passed focused offline tests. Its pinned binary is new and has a successful host-only `--help` and synthetic native-published smoke; no VM instance or file-exclusion live acceptance follows.

## Broader validation qualifications

- Full .NET solution Release tests **1267/1267 PASS** (Live887, core380). Full Python discovery **2076 run, 10 errors, 2 skips**, exit1: every error is `ManaScreenshotTests.setUp` rejecting a pre-existing reviewed owner-probe SHA mismatch (`probe_native_unit_manager.py` expected `9326E2C2...`, actual `73F41BE4...`). The XYZ-focused264 suite passed. Do not silently change that reviewed mana pin.
- Solution-wide `dotnet format --verify-no-changes` failed largely on minified `CurrentBuildExperienceValuesSampleCommand.cs`, visibly present at Git HEAD before this lease patch; new lease lines also contribute. No bulk formatting or claim of full gate PASS. A Windows PowerShell5.1 Lua preflight quoting problem and UTF8 BOM/expected stderr problems in synthetic publish smoke were fixed with narrow test-harness changes; exact Lua5.1 and final smoke both passed offline.

## Critical non-claims and unresolved cross-process gap

- **No fleet deployment or live evidence yet.** Running legacy agents and standalone readers are not participating in this new file lease. `nativeReadLeaseVersion=1` in source or generic updater success is NOT installed-executable attestation.
- Audit: **27/27** registered CurrentBuild CLI commands now acquire the lease, and the guarded agent `action` body also participates in new source. **Generic/legacy native commands** (capture/scout/snapshot/follow-pointer, profile position/power, and related tools) remain unleased. An action with failed key release can retain pending evidence even after its scoped lease disposes. Continue external disarmed/idle/no-input ownership and shared-reader exclusion; never claim global clean-input safety.
- Game XYZ/zone values remain cache-derived candidate observations. Zone/world-instance identity, changed-state proof, API-quiet passive freshness, actor facing and a full game-exit/relaunch qualification remain absent. Historical Lab1 newly pinned reader produced 5/5 and 30/30 stationary candidate samples under the exact retained build, **not** movement proof.
- Lab updater preparation is not a push-button rollback: stage immutable binary separately, hash it on guest, preserve old descriptor and old executable, and use `guest_agent_launcher.py update --managed-lab lab1|lab2 --release <two-field-json> --output <fresh-dir>`. `prepare_guest_agent.py` output `release.json` is a **package envelope**, not directly the two-field `{release,sha256}` descriptor. Generic postflight verifies `gracefulShutdownVersion`, not new native lease capability. Current fleet owner/reader quiescence and guest ACL acceptance were NOT inspected.

## Next authorized practical milestones

1. Complete repository-wide validation and record any pre-existing format/toolchain blockers; the focused host launcher and gateway capability guards now pass offline. Preserve original binaries.
2. Run focused and integrated checks, review SHA hashes, commit source + concise status; push only the verified branch.
3. **COMPLETED HOST-ONLY:** new immutable .NET10 reader build, SHA/size, `--help` and synthetic published smoke. Keep old binaries intact. Before any deployment, confirm lab readers/agent owners are quiescent.
4. Arrange a **cooperative** single-lab maintenance window with Greeting Jimmy/other readers, fresh VM-specific cached-credential check before guest logon, exact VM/game/agent/queue identity, disarmed/no input, no active readers, trusted guest ProgramData ACL. Require exact release SHA and capability1 after guarded replacement; keep rollback descriptor.
5. Only then attempt bounded candidate XYZ+owner+zone collection and an independently observed changed-state/passive-freshness experiment. STOP on missing/excluded owner or epoch/lease mismatch; do not invent world/facing semantics.

No game input/reload/restart, guest agent update, VM logon or new live reader was performed in this checkpoint.
