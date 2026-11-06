# Recommended movement resume prompt

Prepared 2026-10-29 from current repository source, retained trial evidence and
official OpenAI guidance. This is a saved prompt for a future run; writing it
did not deploy software, reserve the labs again or start another experiment.
Copy the prompt below, or ask Codex to execute this file when ready. Its new
test targets become instructions only when you submit it for execution.

## Copy-ready prompt

```text
Resume RiftReader2 in C:\work\riftreader2. Read AGENTS.md, the top of
docs/status.md, and docs/workflows/movement-handoff-2026-10-29.md. Check Git
status and the actual branch; preserve unrelated work. Read further files only
as needed. Do not restart from the older Codex-connection setup work.

Objective: make the existing bounded waypoint workflow repeatable on both
labs by first qualifying the buffer optimization already committed in
2d38866. Lab-1 has one verified arrival but a failed repeat; Lab-2 has an
S-only calibration and no accepted arrival. Both temporary readers and
receivers ended. The optimized published binary has not been tested in a VM.

Work autonomously. This resume request authorizes deploying the reviewed
optimization to both labs, starting bounded readers/receivers, the necessary
reviewed addon reload/bind operations, and the bounded movement tests below.
Reuse cached authentication and existing native Codex/control workflows.
Verify exclusive input ownership before game input; ask only for a genuine
blocking ambiguity or missing access. Preserve the current model/reasoning
setting unless I approve a change. Do not reboot/revert VMs or restart games
as routine setup. Use the guarded repository CLI route; direct ChatGPT
Computer Use in RIFT and patch recovery remain deferred.

Use maximum useful parallelism with disjoint ownership. You alone control
game input. Delegate acquisition analysis, controller/source review and
independent evidence checks; use each lab's existing Codex for bounded
guest-local measurements or review when helpful. Keep heavy builds and guest
analysis outside timing-sensitive measurements. Do not create a new
orchestration framework or manufacture work merely to occupy agents.

First verify the current VM/game/host identities, cached access and exact
optimized binary hash. Reuse the existing receiver and launch helpers in
the handoff. Start isolated feeds, reload/bind the new nonces, and record
installed hashes. Generate NEW source pins and calibrations: old reader
identities, profiles, goals and screenshots are historical evidence only.

Collect one fixed eight-minute no-input observation window on both labs
after startup warmup. Preserve fresh, warming, failed and missing observations.
Report scan duration and receipt gaps (median/p95/max), complete/fresh counts,
longest outage and identity continuity. Compare with the prior journal over
comparable windows; do not call it a controlled A/B benchmark unless conditions
are actually matched. Establish that the current feed can support the existing
4.5-second action-feedback wait before attempting movement. A fresh sample
or short readiness streak alone is insufficient.

Then aim for two consecutive accepted nearby waypoint trials per lab:
Lab-1 using two independently measured directions; Lab-2 explicitly S-only
unless fresh evidence qualifies another direction. Recalibrate for the new
reader identity and whenever the profile's start/identity requirements demand
it. Derive goals from current measured vectors and reviewed clear space;
never reuse old absolute coordinates or assume opposite-key equivalence.
Retain all failed attempts. Stop a failing session safely, diagnose its cause,
and retry only after a concrete correction or demonstrated recovery.

Each accepted trial must use at least two feedback-driven actions with fresh
independent observations, stay within the existing motion/geometry budgets,
arrive within 0.30 units, STOP/disarm with no held inputs, and confirm arrival
with a distinct advancing no-input observation. Preserve the 15-second arm,
12-second motion phase, 150 ms pulse cap and all existing freshness/release
checks. Never extend blind input, weaken freshness, silently rearm or conceal
an ambiguous action to obtain a pass.

If acquisition still prevents this, fix the smallest demonstrated bottleneck
and remeasure; do not chase lucky arrivals or build general navigation.
Run relevant tests for changes and the full gate when code changes. Commit
verified checkpoints promptly. Respect any time budget I supply; ending the
budget is not proof that the engineering objective succeeded.

Finish by cleaning up only exact-owned temporary processes, preserving the
usable labs/control agents, and saving an updated handoff. Report a clean
colored status table with evidence links, every attempt's outcome, measured
before/after results, commits, tests and remaining limitations. Distinguish
implemented, deployed, live-verified and still unproved work explicitly.
```

## Why this prompt is structured this way

The local evidence puts acquisition reliability ahead of another movement
feature. The optimized reader is already built, so the next run should measure
it instead of rebuilding the previous workflow. A fresh reader invalidates old
profiles; this constraint is explicit to prevent a plausible but incorrect
continuation. Fixed observation windows and recorded failed trials reduce
selection bias. Two consecutive arrivals per lab are a practical next milestone,
not a statistical reliability guarantee. These choices come from this project's
evidence; OpenAI documentation does not prescribe these numbers.

Official sources consulted on 2026-10-29:

- [Rethinking skills and prompts](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra): keep instructions relevant and reveal supporting detail when needed. Applied here as a compact prompt pointing to one task-specific handoff; no model migration is requested.
- [Using Goals in Codex](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex): define an observable outcome, verification surface and constraints; distinguish exhausted time from achievement. This file does not create a Goal or schedule.
- [Using PLANS.md for multi-hour problem solving](https://developers.openai.com/cookbook/articles/codex_exec_plans): the archived recipe supports durable context and behavior-based acceptance. Only those general ideas are used; its old model recommendations and full planning framework are not adopted.

The prompt is research-informed and reviewed for this project. Its effectiveness
has not yet been measured in a resumed run; it is not a claim of universal
prompt optimality.
