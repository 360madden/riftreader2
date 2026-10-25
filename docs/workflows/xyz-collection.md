# Repeatable XYZ collection and evidence review

Use the existing exact-build locating recipe for routine XYZ reads. Do not repeat
heap searches merely because RIFT restarted. Discovery, routine collection and
independent semantic validation are separate tasks with different evidence needs.

Use the [reusable preparation, returned-archive verification and export commands](../reference/xyz-workflow-tools.md)
for the local parts of the workflow. They retain the existing live-operation
boundaries and do not start a transfer or touch VMware.

## Current workflow

1. Check [current status](../status.md) and the relevant saved recipe. Refresh
   actual process/build identity before live work; historical PIDs are evidence,
   not a current target. Preserve existing sole-controller ownership.
2. Run the [position window](../reference/position-panel.md) or the
   [bounded sampler](../reference/known-position-sampling.md) in the guest using
   the verified executable and profile. The host cannot directly read guest
   process memory. Each read resolves the recipe afresh; preserve failures.
3. Close the panel normally and retain its entire new session directory, including
   `panel-session.json`, `panel-events.jsonl` and all `read-*.json` originals.
   Use the existing reviewed transfer procedure and retain independently pinned
   archive hashes. Do not audit a directory still being written.
4. Run the offline checker below against the saved copy. Keep its output beside
   the originals as derived evidence, not as a replacement for them.
5. For a restart claim, additionally preserve normal game exit, zero-process
   absence, normal relaunch, fresh process/start identity, independent pointer
   agreement and cleanup evidence. Follow [the restart policy](../decisions/0008-full-game-restart-durability.md).
   For semantic/movement claims, use the separate
   [native/Lua comparison](../reference/native-motion-pair-review.md).

```powershell
python scripts/review_position_panel.py --session-dir PATH_TO_CLOSED_PANEL_SESSION --output NEW_REVIEW_JSON
```

The checker reads local files only. It checks session/report contracts, profile
and build consistency, report hashes, report-event identities, exact live-state
linkage to original observations, clearing of non-live values and subnormal
startup values published as live. It reports counts and process epochs without
promoting field meaning or claiming a new restart test.

Exit codes: **0** means the recorded checks passed; **2** means valid evidence
contains behavioral findings; **1** means malformed, incomplete or inconsistent
evidence, an existing output, or a file error. A completed session must begin
with `opened` and end with `closed`. Missing read numbers are allowed because
failed attempts may produce no report. Extra unreferenced read reports are
rejected. UTC event times must not go backwards, read numbers must increase,
and the full identity must remain consistent within each process epoch. Each
report must be followed immediately by its state outcome; interrupted or
interleaved outcomes are rejected as ambiguous rather than accepted. Subnormal
reports must pair with a cleared `unavailable/position-values-not-ready` state.
Limits are 32 MiB per file and 100,000 events. Outputs never overwrite.

Hashes establish consistency, not authenticity. This audit does not prove that
the UI rendered a state, reproduce monotonic freshness timing, establish player
semantics, or independently verify Lua, process absence, deployment or cleanup.
Normal finite initialization values may still need separate semantic checks.

## When to investigate

- Known exact build and working recipe: collect directly.
- Missing process, failed pointer or unavailable values: retain the failure and
  inspect identity/profile/readiness before attempting another bounded read.
- New field: check Lua API evidence and known structures first; use a small,
  explicit search only when a missing locator or independent source requires it.
  XYZ's owner and offsets do not establish another field's layout or meaning.
- Changed executable SHA: fail closed. Patch recovery remains deferred.

Direct ChatGPT Computer Use inside the RIFT guest remains deferred. This workflow
does not resume it or authorize unattended game interaction.

## Incremental follow-ups

1. **Implemented:** reusable offline panel audit, replayed against both retained
   October 25 trials; [results](../validation/position-panel-review-2026-10-25.md).
2. **Implemented offline:** pinned deployment payload preparation, returned
   Courier ZIP verification and audited panel-session export. The subsequent
   [reusable Courier and transfer lifecycle](../reference/xyz-courier-transfer.md)
   are host-verified; actual guest deployment and real-network use remain pending.
   Authenticated media control retains its existing reviewed path.
3. Collect additional normal exit/relaunch cases when the live interaction path
   is explicitly resumed; report the observed count, never unlimited reliability.
4. Add the evidence to the field catalog without automatically promoting XYZ,
   then choose the next field and its independent semantic checks.
