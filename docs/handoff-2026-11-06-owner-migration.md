# Continuation — live helper migration, November 6, 2026

Work in `C:\work\riftreader2`. Read `AGENTS.md`, `docs/status.md`, and this handoff. Reacquire all PIDs, start times, receiver nonces and VM identities; values below are historical observations, not reusable authority. Prior offline context: [RR2 helper manager](handoff-2026-11-06-rr2-helper-manager.md).

## Current resume point — Lab 1 sustained480 passed

[Strict sustained validation](validation/lab1-sustained480-2026-11-06.md) passed
481.134 seconds with 515 samples; independent replay verified all raw/ledger
hashes, exact identities, advancement, expiry, maximum arrival gap3.058s,
capture gap2.983s and planar drift0.0. The unchanged first attempt failed after
85s with an unavailable receipt; observer-only bounded polling/counting was
implemented and tested in `1802c4b`. Passing run had zero unavailable polls.
The original failed artifact was retained. All acceptance gates remain strict.

Current recorded reader PID6464/nonce622041afc6a14371aa45ec5efcc57c8c expires
November6 9:43:08 PM Eastern. Never reuse its pin or cached packets after expiry.
Controller restored as PID68160/generation`eac96b09093643e09cbb4795e1ac9c2a`,
ready/disarmed/idle, initial cleanup verified, queue generation5212 unheld/free.
This is sustained observer-side receiver evidence, not restart, native-field,
movement or Lab2 qualification. No reload/movement/cast/Lab2 input occurred.

Full gate passed: 380 portable +317 Live .NET, 1,668 Python (2 skipped), Lua,
native smoke, ownership, format and1,022 links; evidence
`artifacts/validation/20261107T023836Z-51b6dc01`. Guest startup race fix
`54d5e95` also has26 focused passing tests. User's five-hour meaningful-work
goal remains active. Next standalone ownership-instance hardening is isolated
in `C:\work\riftreader2\.worktrees\helper-instance-binding`, branch
`codex/helper-instance-binding`; it is not integrated or deployed. Preserve
other sessions' edits and all current owners. No new gameplay authority follows.

## Prior resume point — short-window cleanup and freshness passed

See [the live validation](validation/lab1-receiver-freshness-2026-11-06.md). The
fixed-file cleanup passed execution review and deleted the physical guest file;
a second fresh GuestSession confirmed absence and no reader. The earlier user
and Tools checks reflected different views; stale receipts and a simple PS
version difference were ruled out, while the exact Windows mechanism remains
unproven. This supersedes the cleanup blocker described chronologically below.

A fresh bounded reader and exactly one screenshot-reviewed Lab 1 rebind produced
12 strict advancing regular-feed samples over 8.934671 seconds (outer236→247,
addon13664→13682, same player/epoch). The managed controller was safely released
before input and restored afterward as PID64320, generation
`d3f5021244604dba97e0214310e5ab16`, ready/disarmed/idle with initial cleanup and
current source pins verified. Queue generation5210 was free/unheld. No reload,
movement, casting or Lab2 input occurred. Reader PID7108 expires at November6
8:49:59 PM Eastern; its future cached packets are not fresh evidence. Do not
reuse its nonce. Short-window feed acceptance does not establish sustained480,
restart or native-field qualification. Lab2 freshness is still unverified.

## Completed live owner transitions

- Both legacy receiver instances were individually pinned by process receipt and Scheduler COM GUID/EnginePID, stopped, checked exited/port-vacant, and replaced by RR2-managed receiver tasks. Independent postflight task/receipt checks passed: Lab 1 PID 5840/start `639296090706474389`; Lab 2 PID 4856/start `639296091161417286`. Legacy XML, registration and receipt backups are under `artifacts/receiver-migrations/lab1-76b0741c7ce14d7c8ebd573bd60adc42` and `lab2-a2804964338741578e60d4d704568bb5`. No feed packets appeared in either new output directory at the check; **advancing freshness is not established**. Migration helper commit `44df5e6`.
- Lab 1 controller old PID 29820 passed direct authenticated STOP, fresh no-input status and generation-specific verified shutdown. `artifacts/controller-migrations/lab1-20261106/verified-shutdown.json` has SHA256 `174534F26F5489F02C65373610D3D868A6FC241D23B1D495944AD55F5B3FBCFB`; its queue moved to blocked generation 5207 before successor reconciliation. Retained task XML/registration are in the same directory. The RR2 successor PID 65564, generation `c0e4e5e474b94ebabfef9a02e7e6ddd7`, passed managed receipt/source verification and connected, ready, initial-cleanup-verified, disarmed/idle/no sampled inputs status. Queue generation 5208 was unblocked, unheld, with no pending work.
- Lab 2 is **recovery**, not a verified clean handoff: prior PID 47952 and old VM PID 20020 were gone; last old-generation emergency STOP was unverified and queue generation 2252 blocked. Exact Ready-state legacy task was independently verified and backed up under `artifacts/controller-migrations/lab2-20261106`; no old task instance or controller listener existed. RR2 successor PID 10904, generation `fb51eb44863a43fcac36aabc299c227d`, subsequently connected with initial cleanup verified, disarmed/idle/no sampled inputs; queue reconciled to a fresh VM epoch, generation 2253, unblocked/unheld. `ensure_guest_agent.py` initially returned `connected-but-not-idle`; subsequent independent status showed ready. Game foreground was false; no game input was sent on Lab 2. This does not retroactively qualify old shutdown.
- At last task inventory, all four RR2 helper tasks were Running; no matching legacy helper task remained. Process/task health is not telemetry freshness.

Full local gate `pwsh -NoProfile -File scripts/validate.ps1` passed: 380 portable and 301 Live .NET tests, 1,604 Python tests (2 skipped), PowerShell ownership mocks, Lua contracts, synthetic native smoke, format and 1,018 relative links. Evidence: `artifacts/validation/20261107T005715Z-1fbf31cc`. The tests do not establish live feed freshness. Ready-state verifier commit `cf8b6bf`; staging-path fix commit `24e01a0`.

A subsequent read-only continuation confirmed Lab 1 controller connected/ready, supervisor initial cleanup verified, disarmed/idle/no sampled inputs, and receiver ownership verified (PID 5840 at that observation). The earlier automatic execution-policy rejection still blocks the guest cleanup; the user granted approval, but this does not itself override that rejection. No new bind or game input was performed.

The user reported manually deleting the staged configuration. A subsequent identity-pinned cached-credential guest check recorded `configExists: true` and `otherReaderCount: 0` in `artifacts/receiver-migrations/lab1-cleanup-verification/inspect.json`. This conflicts with the user report; request a recheck of the exact guest path and require a fresh absence check before reader launch. No new bind or input was sent.

A later identity-pinned guest check again reported `configExists: true`, `otherReaderCount: 0`, machine `RIFT-LAB-1` (evidence `artifacts/receiver-migrations/lab1-cleanup-verification-3/inspect.json`), despite the user reporting deletion and guest PowerShell reporting `False`. Earlier guest metadata recorded the exact file as 411 bytes, without reading its contents. The discrepancy remains unresolved. User requested automation without further questions, but the prior automatic execution-policy rejection still applies to guest cleanup; do not bypass it. No bind or input was sent. Other sessions have concurrent uncommitted work; preserve it.

## Historical cleanup blocker — resolved above

User authorized a fresh **Lab 1-only** reviewed reader bind/rebind solely to verify advancing receiver feed; no UI reload and no Lab 2 game input. Reader launch `artifacts/receiver-migrations/lab1-freshness-reader-20261106` failed `private-staging-cleanup-scope` before its launch step. Host private staging file was removed after same-directory-identity verification. Windows virtualization made the original resolved-path check disagree; commit `24e01a0` fixes it with filesystem identity checks, rejects reparse/symlink targets and has focused tests. No reader-ready receipt and no new bind/input were produced. The guest staging configuration at `C:\Users\mrkoo\AppData\Local\RiftReader2\Hybrid\lab1-fed73039b1614151bc92bda5b8501641\riftreader2-live.json` may contain the private receiver token and may remain on Lab 1; do not print its contents. An attempted exact guest cleanup plus no-reader verification was **rejected by automatic execution policy before running**; reason was not specified. Do not bypass that rejection. Resolve the cleanup through an allowed route/user action, verify absence and no unexpected reader, then retry with fresh identity, nonce and screenshot-reviewed controls. No feed freshness claim until strict fresh same-player/epoch receiver samples actually advance.

User did not authorize Lab 2 game input. The prior Lab 1 successful bind and reload must not be replayed. A fresh reader nonce would require a separately reviewed `rebind` only if the existing addon state supports it; never guess or blindly try both bind and rebind. Preserve controller STOP/release, exclusive console ownership, queue, exact identity, screenshot freshness and restore checks. RR2R1 typed-reference evidence is distinct from receiver-feed freshness.

**Copy-ready resume:** Read `AGENTS.md`, `docs/status.md`, this handoff and the
strict sustained validation. Reacquire current identities; reader6464 expires
at9:43:08 PM Eastern and its recorded PASS belongs only to that epoch. Continue
the active five-hour standalone development work with the isolated helper
instance-binding slice, focused tests and strong ownership review. Preserve
current controllers and receipts; no source-pin relaxation, re-arm, movement,
reload, restart or Lab2 game input is implied. Integrate only reviewed scoped
changes and use verified per-owner handoffs for any runtime rollout.
