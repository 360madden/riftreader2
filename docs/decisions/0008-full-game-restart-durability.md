# 0008: Prioritize full game restart durability; defer patch recovery

Status: accepted user policy.
Date: 2026-10-25.
Authority: Joey explicitly requested durable policy: defer patch recovery and
prioritize surviving restarts, meaning completely exiting the game and starting
it again.

## Decision

The current objective is durable, reusable collection across **full RIFT process
exit and relaunch on the same supported build**. Preserve the locating method,
build applicability and supporting evidence so each new game process can be
located and read without rediscovering already-known fields from scratch.
Saved absolute addresses, old PIDs and old coordinates are session data, not
durable locating knowledge.

For restart acceptance, record the old process ending and an absent-game
observation; then launch RIFT normally, acquire a fresh process/start identity,
resolve the saved recipe to current owner addresses, and verify fresh values
after world entry. Preserve raw originals, hashes, source freshness and separate
Lua/native provenance. Reject absent and stale processes instead of reporting
old values as current. This defines acceptance, not a new authorization to
perform a disruptive live trial without the applicable session authorization.

Addon reload, character logout/login, and external-reader restart alone do not
demonstrate this game restart requirement. VM restarts, host restarts, crashes
and snapshot restores are separate scopes and are not implicit requirements
for this policy update. Label each observed scenario accurately.

**Patch/update recovery is deferred until Joey explicitly resumes it.** It is
not the automatic next task, and patch survival is not a prerequisite for
accepting demonstrated same-build restart durability. Retain existing
exact-executable SHA guards: a changed build fails closed. This policy does not
authorize using old offsets on an unknown build or silently starting patch
rediscovery.

## Evidence and qualification

The [October 25 normal restart trial](../validation/native-xyz-restart-2026-10-25.md)
already recorded complete game exit, absence rejection, a new PID/start and
owner, unchanged-profile automatic XYZ reacquisition, old-process rejection,
and independent advancing Lua agreement. The [export record](../validation/native-xyz-results-export-2026-10-25.md)
preserves its raw evidence and checksums with the earlier movement trial.

This establishes one observed same-build restart case. It does not establish
unlimited future reliability, restart durability of other fields, patch survival,
loading/menu behavior, synchronized clocks, or native-field semantic promotion.
The separate meaning/locator/restart/update claims in [ADR 0005](0005-durable-field-catalog.md)
remain in force; no report qualification or contract is changed by this policy.

## Consequences and superseded sequencing

Favor fast fresh-process acquisition and durable reusable recipes in subsequent
work. Keep failure evidence and validity boundaries visible. Existing roadmap
and historical handoff references to patch recovery describe future work only;
their automatic next-step sequencing is superseded by this decision. Patch
recovery resumes only on Joey's explicit instruction.

This is a documentation and priority update. It neither repeats the already
observed restart nor expands live-control or downstream automation scope.
