# RR2 three-chat coordination — Monday, 2026-11-09

**Shared checkout:** `C:\work\riftreader2` on verified **AMD-DESKTOP**, branch `codex/modular-foundation`. Other ChatGPT conversations are **not directly message-connected**; use this repository to exchange results. This file is a coordination proposal until each chat reads and acknowledges it.

## One coordinator, two independent work lanes

- **Monday RR2 Development (coordinator):** Integrate, select next working milestone, inspect Git conflicts, run combined tests, commit/push coherent changes, and own **all live RIFT input and VMware lab controller operations**. Current priority is a new bounded Lab2 W calibration with fresh readable review and independent XYZ feedback, but only when actual controller ownership and review are ready.
- **subagent1 — offline movement/navigation:** Investigate and improve the existing review-to-action latency path and/or route-to-coordinate usability. First inspect `scripts/quick_review_capture.py`, `scripts/run_movement_session.py`, and relevant tests. Work only on specifically claimed disjoint source/test files; **do not send game input, arm, restart labs, or replace controllers**. Preserve existing 45-second review and safety gates. Submit one practical result and focused tests.
- **subagent2 — offline native retrieval/discovery:** Investigate a useful current-build native-field reader/diagnostic (e.g., player/target resource meanings or reliable read-only retrieval). Reuse existing samplers and evidence. Work only on disjoint, claimed source/test files; no live gameplay input or competing lab/guest controller sessions. Report candidate versus qualified data precisely. **Do not modify** the unrelated untracked `scripts/project_current_native_energy_variants.py` without confirming its owner.

## Minimal handoff

1. Each chat first verifies host name (must be AMD-DESKTOP for this checkout), reads current `AGENTS.md`, `docs/status.md`, this file, `git status` and latest HEAD. Do not overwrite work already in progress; if assigned scope conflicts with another chat, pick a disjoint task or report it.
2. Each chat keeps edits in its claimed files, runs focused tests, and gives the coordinator **exact changed paths, test results, Git hash (if committed), and next blocker**. Commit only coherent verified changes with current HEAD, preserve all unrelated changes, and avoid independently pushing until the coordinator integrates.
3. Coordinator checks the shared repo for new commits/changes and integrates after each completed slice. If direct chat delivery is not possible, share a concise result in the chat itself and optionally put a short status note in an explicitly owned file.
4. Only the coordinator owns one live RIFT/VM input queue at a time. Never bypass stale source/lease, controller owner, capture age, STOP/key-release, or machine-identity gates.

**Current shared baseline when written:** HEAD `04ee53244c23982b2d4d7d7a22ada331a75bbb20`; GitHub synchronized; only untracked research script noted above. These are historical snapshots and must be rechecked before edits. Prior Lab1 1D/2D waypoint arrival is established, while Lab2 W calibration has not passed. 

**Success this round:** one useful, independently tested change per lane, or a precise reproducer/blocker; no new framework or process overhead.
