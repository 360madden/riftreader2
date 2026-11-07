# Continuation — live helper migration, November 6, 2026

Work in `C:\work\riftreader2`. Read `AGENTS.md`, `docs/status.md`, and this handoff. Reacquire all PIDs, start times, receiver nonces and VM identities; values below are historical observations, not reusable authority. Prior offline context: [RR2 helper manager](handoff-2026-11-06-rr2-helper-manager.md).

## Discovery priority — November 7

Joey redirected work to discovery: use the shortest reliable experiment and
proportional checks. Remaining maintenance P2s are deferred, not the next task.
Parallel static cast/cooldown workers own separate retained artifacts; the root
retains sole live-operation ownership. Existing STOP/release and identity gates
remain intact.

First live `probe_native_unit_manager.py --lab lab2 --cast-record` completed:
native self key `u035400012DFEB5BC`, exact SHA1935A05C..., PID9752/start
639294897826627677, stable anchors, cast selector0/slot0 and both child pointers
null. It exposes raw topology, not qualified cast/idle/timer semantics. See
[receipt and limits](reference/native-current-cast-candidate.md#first-live-capture--november-7).
Cooldown research traced the original map key and two candidate resolver roots;
see [findings](reference/native-cooldown-static-followup-2026-11-06.md#key-provenance-and-candidate-roots--november-7).
No game input, bind/reload, restart or owner transition was performed.

Milestone `a7b2671` records both-lab cast capture and the initial cooldown
key/root trace. A subsequent Lab2 `--cooldown-roots` run completed with both
roots present, selector83 and stable bracketed anchors. The collection dispatch
is KERNEL32!TlsGetValue: a game-thread override may supersede owner+0x200,
and a cache miss cannot establish absence. Static cast tracing maps output
slots to `begin`, `duration`, and `remaining`; duration still requires a virtual
path, while component+0x2B8 is an unknown raw DWORD, distinct from abilityNew.
A follow-up live Lab2 capture read that raw DWORD as0 with stable anchors;
the guarded selected child's +8 DWORD is the abilityNew-key source, subject
to the producer's nested-pointer guard and marshaller lookup. The seven focused
helper checks passed; no full validation campaign was run.

**Resume:** continue native cast/timer and ability/cooldown discovery. Reacquire
each process epoch; resolve the game-thread TLS collection before relying on
cooldown cache traversal, and use retained exact-build getter disassembly for
timer fields. For cast duration, a non-null child's +0x20/+0x28 vtable slot+8
is the next static-analysis seed; never invoke it. Null-child observations
cannot establish duration or casting/idle semantics.
Do not restart the full validation gate or maintenance queue merely because
those items appear chronologically below. Save concise concrete findings and
commit useful slices; no new framework or validation campaign.

**Duration continuation:** The exact nested type vtable RVA0x26AA0E0, slot+8
target0x09D680 implements float32 object+0x18; root independently checked
getter bytes `F30F104118C3` and the slot against the retained SHA. The helper
exposes this as a fingerprint-gated raw durationCandidate, after producer guards,
with semantic begin/duration still null. Eleven focused cases passed; no live
matching duration object was observed. See [formula](reference/native-current-cast-candidate.md#type-specific-passive-duration--november-7).

**Cooldown continuation:** `--cooldown-collections` now observes thread TEB/TLS
through the existing exact-epoch snapshot reader. A small host-compiled metadata
executable uses query-only OS handles and is SHA-checked on guest invocation;
guest script-file policy is preserved. The actual chain is
`[module+0x3372C18] -> wrapper -> [wrapper] -> owner`, then owner+0x274.
The first Lab2/Lab1 trials used the wrapper as owner and are SUPERSEDED, not
selection evidence. Corrected Lab2 `44b1eeb84b434b6d9c01fd4db810a6a0`
and Lab1 `effd113dbaf040fc9d4856abd5c8ec2a` runs passed with TLS index20:
one explicit embedded collection pointer each, all other slots zero, and all
26/28 threads respectively selecting owner+0x200. Bracketed thread metadata,
TEB/TLS/owner/root/cache-header/source/process checks passed; both map headers
had stride24/count3444. See [receipts and correction](reference/native-cooldown-static-followup-2026-11-06.md#corrected-live-selection--november-7).

**Next useful experiment:** reacquire the corrected owner and TLS selection,
then read a bounded selected-cache bucket/chain set and correlate candidate
selector83 keys with independent ability data. A cache miss cannot establish
absence until fallback0x128CCB0 is understood. For duration, use the gated helper
when a non-null child is observed; do not apply object+0x18 to an unmatched
virtual type or claim a live duration before matching-object evidence. Preserve
all existing input/ownership gates; this batch performed no game input or owner
transition. Keep checks focused, and leave maintenance deferred.

## Reader startup readiness P2 fixed — November 7

The launcher no longer treats a nonempty last snapshot as readiness after its
polling deadline. It requires an explicit positive match on the current complete
bind instruction's nonce, outer/target-session nonce, exact game PID, lossless
start ticks and build SHA, plus `readerStatus=running` and enabled delivery to
the expected endpoint. Every poll clears stale candidates/nonces; terminal,
malformed or mismatched evidence cannot set success. Acceptance is checked
before the deadline. Guest strings use ordinal comparison, not PowerShell's
culture-sensitive equality; integer identity fields reject bool/float coercion.

The guest reacquires the game identity and rechecks reader exit before issuing
the ready receipt. Host receipt tuple validation and independent validation of
the copied snapshot precede the success summary. This remains startup identity,
not addon binding, advancing feed acceptance, passive freshness or restart
qualification. See [startup versus observer qualification](workflows/live-reader-freshness-observer.md#reader-startup-identity-gate).

Receiver ownership, VM-specific cached login, pre-launch game checks, reader
overlap exclusion, direct STOP/release and guarded cleanup remain. No reader was
launched, no VM/game/input/bind/reload or owner change was performed. The two
separate cleanup/publication P2s remain outside this fix; no automatic kill,
rebind, retry or cleanup bypass was added.

The actual Windows PowerShell-generated predicate and host cleanup/validation
suites pass 23 tests; independent review reran all 23. Root's broader reader,
receiver, receipt, source-pin and freshness suite passes 109 tests. Tests cover
one-tick drift above 2^53, terminal state, singleton arrays, malformed/typed
fields, deadline crossing, stale log/candidate clearing and invisible characters
that PowerShell culture comparisons previously ignored. A before/after run on
baseline `04350e0` falsely accepted wrong nonce/PID/start/build; the fix refuses
all four. Artifacts: `artifacts/reader-readiness-fix-20261107/`.

**Practical-results correction:** the user reiterated that practical progress
comes first. Relevant focused checks and review passed; the unnecessary full
gate was interrupted at their direction and is not claimed as complete. Do not
automatically run full repository validation for each narrow fix; follow the
existing AGENTS.md proportional-check policy and move on once relevant checks pass.

Two P2 findings remain. Next separate repair: host private-staging ownership on
hash failure and cancellation-safe guest cleanup, preserving no-live-reader and
identity gates.

## Scheduler startup retry P2 fixed — November 7

The helper manager now handles its own known COM-nonrunning to ScheduledTasks-
Running race, with three total Status attempts and no added sleep. Each attempt
reopens the non-reparse registration receipt, checks its digest and reacquires
the full task/legacy/registration contract. After the transition the receipt
digest stays pinned. Success still requires two fresh running-instance
observations with matching PID/GUID; each Python entrypoint separately checks
the returned engine PID against its own process.

Wrong or changing instances, legacy conflicts, task mismatch, malformed state
and access failures remain immediate refusals. Initial absence becoming Running
is not retried. Losing Running after the transition or exhausting attempts
refuses admission. No task registration/start/stop was added to Status. Stable
ordinary states, Register/Start and strict Lab 2 inspection retain their prior
contracts. Both Python callers still make one Status subprocess call with their
existing 20-second timeout; this bounds blocked COM, while the loop bounds count.

The isolated Windows PowerShell manager mock passed transition, exhaustion,
fresh-proof, changed-registration/instance, no-downgrade and no-mutation cases.
Six committed Python consumer regressions verify the single call/timeout and
strict PID/GUID/schema refusal. Root's broader ownership, controller, receiver,
movement, dependency and control suite passed 241 tests. Independent ownership
review passed. Artifacts: `artifacts/scheduler-retry-fix-20261107/`.
See [status behavior](reference/native-vm-controls.md#scheduler-startup-status-transition).

Full gate PASS: 719 .NET tests and 1,880 Python tests run (1,878 passed, two
skipped), locked restore/build/format, native smoke, real Lua/C# contracts,
ownership mocks, deterministic replay and 1,115 relative links. Evidence:
`artifacts/validation/20261107T121429Z-b2b3490f`; logs and four verified source
hashes are in the artifact directory above. Running the new transition mock
against baseline `7ceabd2` reproduces the old explicit retry refusal; the same
scenario passes with fresh proof on the fixed manager. Both runs use only
in-memory Scheduler mocks.

No live helper/VM query, task mutation, input, owner transfer or restart was
performed. This manager-only source change adds no controller/receiver runtime
pin change; the separate task-entry rollout requirement from the prior receipt
fix remains in force. Offline mocks do not establish live cold-start acceptance.
At this checkpoint three P2 findings remained; the subsequent reader-readiness
fix is recorded above, leaving two.

## Controller receipt P2 fixed — November 7

`controller_task_entry.py` now gathers and serializes all receipt data before
creating a staging leaf, flushes/fsyncs it and atomically publishes `process.json`
without replacement. Strict JSON is limited to 65,536 bytes. Only publication
success permits host execution. Metadata, partial-write, flush/fsync, interruption
and collision failures leave no malformed final and remove only owned staging.

Historical recovery is narrow: empty, syntax-invalid or incomplete-schema
receipts require a strict same-canonical-generation `exited.json` plus fresh
positive PID absence. The Windows checker distinguishes missing PID from access
denied/other failures; `process-unavailable` text alone is insufficient. A live or
reused exit PID, contradictory receipt identity, unreadable/reparse path,
duplicate/nonfinite JSON or unidentified corruption stays blocked. Full-schema
field violations are also refused. Valid receipts require complete process
identities; only a valid different start epoch establishes PID reuse.

A failed startup with no final receipt and no exit marker is skipped, because
it could not have started the host. Missing receipt plus exit evidence blocks.
Composition tests prove metadata/fsync failure followed by healthy successor
admission, without deleting history or accepting two owners. Reviewed-generation,
source/configuration, task PID/GUID and existing listener/dispatch gates remain.
See [receipt behavior](reference/native-vm-controls.md#controller-receipts-and-historical-generations).

Independent review passed 59 tests (15 publication and 44 resolver); root's
broader controller/movement/dependency/client/guest suite passed 222 tests.
Native absence smoke used only this test's short-lived local child: an exited
process object still held by the test was conservatively not absent, then PID
absence was confirmed after releasing that handle. Artifacts:
`artifacts/controller-receipt-fix-20261107/`.

Full gate PASS: 719 .NET tests and 1,874 Python tests run (1,872 passed, two
skipped), locked restore/build/format, native smoke, real Lua/C# contracts,
ownership mocks, deterministic replay and 1,096 relative links. Evidence:
`artifacts/validation/20261107T120145Z-b08bb659`; full log, before/after
reproduction and four verified source hashes are retained in the artifact
directory above. The gate covered the shared checkout, including concurrent
Lab 2 tool-wrapper changes; those changes are excluded from this fix's commit.

**Rollout remains separate:** this edit changes the task-entry source hash pinned
by existing owner receipts. No lab/helper query, restart, retirement, ownership
transfer, queue reset or input was used. Do not bypass `managed-runtime-changed`
or treat this offline fix as activation. Existing owners and direct STOP/release
remain preserved; reacquire identities and use the reviewed per-owner migration
before admitting a new-source owner. Unidentified legacy corruption still needs
independent investigation, not automatic deletion.

At this checkpoint four P2 findings remained; the subsequent Scheduler retry
and reader-readiness fixes are recorded above, leaving two.

## Armed-action preflight P2 fixed — November 7

Default and `--no-auto-start` actions now use `ensure_existing` for a recognized
managed lab. They never start/recover a controller or guest after arming.
Missing/refused ownership blocks dispatch. The existing-owner result supplies
the single authenticated status snapshot for a read-only action readiness check;
there is no extra status request or mutation of the observed arm state.

Review caught that routing alone would drop the prior default held-input/busy
gates. The reusable readiness predicate now permits an actual armed boolean while
retaining ready/connected coordination, a healthy held console, no sampled held
inputs, no busy action and no recovery requirement. Missing/malformed status
blocks. Disarmed readiness remains the default for capture/arm recovery.

Lease, arm artifact/token, payload/output admission and host/guest final-send
checks remain in place, as do direct STOP/release. No fallback, retry, re-arm,
live input, helper restart or ownership transfer was used. The existing owner
check binds managed source/config/process/listener evidence; fresh VM identity
and the action's dispatch/token/target gates remain with their owning host/guest
checks. Do not describe this sampled preflight as independent live qualification.
See [action admission](reference/native-vm-controls.md#action-admission-after-arming).

Six new offline regression methods bring the client suite to 30 tests and the
guest-readiness suite to 13; all 43 pass. Root's broader control, ownership,
dependency, console and reservation suite passes 218 tests. Independent safety
review also passed 90 related tests. The separate mocked reproduction retained
the original `connected-but-not-idle` refusal on baseline `7270b16`, while the
fix admitted one ready armed action with no recovery and still blocked sampled
held inputs. Artifacts: `artifacts/armed-action-fix-20261107/`.

Full gate PASS: 719 .NET tests and 1,838 Python tests run (1,836 passed, two
skipped), locked restore/build/format, native smoke, real Lua/C# contracts,
ownership mocks, deterministic replay and 1,081 relative links. Evidence:
`artifacts/validation/20261107T111052Z-99f84920`; full log and four verified source
hashes are retained in the artifact directory above. This gate covered the
shared checkout, including concurrent Lab 2 tool-wrapper tests; those files and
their AGENTS/workflow documentation are preserved outside this fix's commit.

At this checkpoint five P2 findings remained; the subsequent receipt fix is
recorded above; two remain after the Scheduler/readiness fixes. Preserve independently verified owner identity.

## STOP/release optional-output P2 fixed — November 7

`control_client.py` now sends one direct STOP/release POST before any optional
output path work. An existing receipt, inaccessible parent, path error or storage
failure cannot suppress cleanup. Acknowledged requests whose receipt fails still
exit nonzero with the output error code plus `error.details.operation`,
`requestCompleted: true` and the host's exact `result`. This separates storage
failure from the returned cleanup outcome; it does not certify successful release.
Transport/host errors remain unchanged, without output access or automatic retry.

No controller startup, ownership inspection, lease read/acquisition or recovery
was added to these direct cleanup routes. Recover/arm/action retain output
reservation before their protected request. Descriptor ownership transfers once
to the writer; failed writes do not trigger a second caller close/unlink that
could affect a replacement file. Console errors redact tokens and Authorization.
See [client behavior](reference/native-vm-controls.md#stop-and-release-receipt-failures).

Twelve new offline regression tests bring the client suite to 25 passing tests.
They cover both cleanup operations, storage/path failures, original error
propagation, negative cleanup results, CLI redaction, output preservation and
descriptor lifetime. No live request, input, helper restart, owner transfer or
queue/STOP/release gate change was used. Independent safety review passed.

The combined client/host/dependency/console/reservation suite passes 171 tests.
The full gate passed 719 .NET tests and 1,815 Python tests run (1,813 passed,
two skipped), locked restore/build/format, native smoke, real Lua/C# contracts,
helper ownership mocks, deterministic replay and 1,070 relative links.
Evidence: `artifacts/validation/20261107T100621Z-3f208918`; source hashes, logs
and reproduction are under `artifacts/cleanup-output-fix-20261107/`.
The separate mocked existing-file reproduction sent zero requests with vulnerable
`13276c9` and one with this fix for each of STOP/release, preserving the original
file. The acknowledged negative cleanup result remained negative in the error.

At this checkpoint six P2 findings remained. The subsequent armed-action fix is
recorded above; two remain after the later fixes. Preserve ownership and final-send safety gates.

## Console replay P1 fixed — November 7

The reviewed console now creates an exclusive `execution-attempt.json` under
the existing `ControlMutex`, flushes and fsyncs it before any connection/input,
and checks legacy `execution.json` again under the mutex. A partial marker is
never removed to permit retry. Attempt-state lookup errors fail closed; dangling
legacy reports count as existing. Only the reservation owner publishes a final
report, so a busy or losing caller cannot overwrite the owner's result.

Independent safety review found no remaining P1 replay path. Eleven new offline
regression tests cover two callers passing the early check, collision after the
owner's report write fails, the post-mutex publication window, marker
write/flush/fsync failures, inaccessible metadata, dangling legacy reports,
send/cancellation cleanup and failed final publication. The focused console
suite passes 80 tests; the combined console/native-console/reservation suite
passes 140. The new regressions also fail against vulnerable baseline `c5edf0c`;
a separate report-write-failure reproduction sent twice before the fix and once
after it, with retry refused. All input was mocked.

Full gate PASS: 380 portable plus 339 Live .NET tests; Python ran 1,803 tests,
with 1,801 passed and two skipped. Locked restore/build/format, native published
smoke, real Lua/C# contracts, helper ownership mocks, deterministic replay and
1,057 relative links passed. Evidence:
`artifacts/validation/20261107T095604Z-d546dc58`; logs and verified source hashes
are in `artifacts/console-replay-fix-20261107/`.
The first gate encountered two tests mid-edit in concurrent managed admission
work; its log is retained. That module then passed 29 focused tests and the
complete recheck passed. The broad gate covered the shared checkout, including
concurrent admission edits; those changes are excluded from this P1 commit.

Use a fresh output directory, preparation and screenshot review for a new
authorized operation after a consumed/uncertain attempt. Preserve original
markers and reports; do not clear them to replay a command. Existing VM/game
identity, source/review freshness and key/mouse release/disconnect gates retain
their order. No live input, bind/reload, helper restart or ownership transfer
was used. Details: [console validation](validation/console-interaction-speed-2026-11-06.md#durable-console-attempt-reservation--november-7).

At this P1 checkpoint seven P2 findings remained. The subsequent STOP/release
optional-output, armed-action, receipt, Scheduler and readiness fixes are recorded above; two P2 findings remain.
Any later live console use still needs fresh identities, an independently
reviewed screenshot and the existing exclusive ownership handoff.

## Lab 2 report audit — November 7

Three parallel reviewers checked the consolidated Lab 2 investigation against raw
timing traces, native/capture receipts, retained controller logs, validation logs,
release bytes and historical Git source. See the
[verified audit and discrepancies](validation/lab2-latency-report-audit-2026-11-07.md).
No live operations, input, helper changes or owner transfers were used.

The headline measurements reproduce: screenshot44.049 to5.898s (15 to3 calls),
joined remote5.826s, native persistent median0.2185915s, and ten light checks over
544.397046s. The release ZIP executable matches the reported full SHA. Retained
STOP and cleanup evidence supports the bounded historical trial; it is not a new
current-state qualification. Exact figures and source paths are in the audit.

Corrections: Python1720 means1718 passed plus2 skipped; the full-gate log records
1029 relative links. No raw result for the later1035 count was found in the
bounded search, so that count is excluded from verified acceptance. All ten
interval runs passed machine verification; only10 retains a separate visual
review. Approximately55s between samples were unobserved. Source provenance is
historical `af6662b`:23/26 raw Git hashes match, and the other three reconcile
through line-ending normalization. These observations do not qualify subsequent
runtime changes or establish continuous freshness/native semantics/restart.

**Material chronology discrepancy:** `final-acceptance.json` was composed at
03:21:20 UTC with copied ready/generation2332 fields. The retained host log records
generation2333 `stopped-still-blocked` at03:21:05.566885, disconnect at03:21:05.975067,
and the independent exit marker confirms controller PID59400 exited at03:21:05.985506.
The earlier joined workflow and its release passed; readiness at the summary's
timestamp did not. Shutdown was stopped/disarmed/not busy/no sampled held inputs.
The next logged connection was03:28:20 under a later controller. Preserve raw
receipts; do not reuse this summary as current ownership or readiness authority.

The report now reflects these boundaries. Local reproducible audit outputs are in
`artifacts/lab2-report-audit-20261107/`. Preserve current owners and STOP/release
gates; reacquire identities for any later live use. At this audit checkpoint the
P1 console-attempt defect was open; the subsequent fix is recorded above.

## Review checkpoint — November 7

The user requested a review after clearing the timed goal. Independent reviewers
checked committed runtime `399d463` and retained evidence; later `8ded91e` is
documentation only. No live input or helper mutation was used in the review.
The sustained480 and native-v2 results still reconcile. This table records the
historical review; the P1 and five P2s are now fixed above, with two other P2
findings remaining open.

| Priority | Finding | Owning source |
| --- | --- | --- |
| P1 FIXED | Failed final report publication or two callers passing the pre-mutex check could dispatch the same reviewed plan twice. Exclusive durable reservation and owner-only report publication now block replay. | `scripts/addon_command_console.py`; November 7 fix above |
| P2 FIXED | STOP/release now dispatch before optional output work; output errors retain the acknowledged result and cannot suppress delivery. | `scripts/control_client.py`; November 7 fix above |
| P2 FIXED | Both action modes verify an existing owner and its read-only readiness while permitting an existing arm; no guest/controller recovery occurs after arming. | `scripts/control_client.py`, `scripts/ensure_guest_agent.py`; November 7 fix above |
| P2 FIXED | Atomic no-overwrite receipt publication prevents incomplete final files; malformed history is skipped only with strict exit evidence and positive process absence. Unidentified history stays blocked. | `scripts/controller_task_entry.py`, `scripts/managed_controller_receipt.py`; November 7 fix above |
| P2 FIXED | Manager retries only the known nonrunning-to-running Status race, with three fresh attempts, pinned registration and unchanged caller PID/GUID/timeout checks. No task mutation. | `scripts/Manage-RR2HelperTask.ps1`; November 7 fix above |
| P2 FIXED | Reader startup requires an explicit matching nonce/PID/start/build observation before its deadline, running state and delivery binding; host receipt/copied snapshot validation precedes success. | `scripts/launch_live_reader.py`; November 7 fix above |
| P2 | Host staging ownership is lost if config hashing fails before return; guest cancellation skips Exception-only in-session cleanup. | `scripts/launch_live_reader.py:238,363` |
| P2 | Windows deny-delete reads can block atomic publication after sequence history advances, losing the publication and rejecting its same-sequence retry. | `scripts/addon_command_console.py:248`, `scripts/observation_receiver.py:70` |

Most defects predate this session. Cancellation cleanup and the extended reader
handle window involve new changes; the Scheduler retry gap involves the new
status path. Reproductions used mocked input and synthetic local files/status.
The earlier blanket claim that a reviewed plan cannot send twice was too broad:
cancellation with a saved report is covered, failed publication/concurrent calls
are not. No runtime source was changed during this review.

Documentation corrections repaired mixed UTF-8/Windows-1252 bytes in status.md,
narrowed the final retained-status claim and marked checkpoint values historical.
All262 tracked Markdown files passed strict UTF-8 decoding after repair.
Concurrent managed receipt/movement admission work was preserved; it became
commit `926309a` during the review and is excluded from the fixed `399d463`
runtime review and its earlier full-gate conclusion. No current-state claim
should be inferred from this historical checkpoint.

## Current resume point — sustained480 and helper ownership accepted

**Latest, 10:54 PM Eastern:** [current-owner sustained480](validation/lab1-current-owner-sustained480-2026-11-06.md)
passed511 samples over480.653s, gaps2.449/2.352s, drift0 and zero unavailable
reads. Independent full/fast production-gate replay and20 sampled helper checks
over578s passed. Lab1 controller is now PID15636/generation
`fcd8e722d34d4758b82f7171ddd2bae0`, receiver63376, queue5216; Lab2 remains
controller24412/receiver65764/queue2334 at that checkpoint. Both ready/disarmed/idle/free at final
postflight. Reader PID12424/nonce`f335b16b33324c33950af2df29b840bc` expired
after10:57:53 PM Eastern; fresh guest checks verified no readers, deletion of
only its private staging leaf and independent absence. The stale snapshot was
refused with exit2, `not-fresh`, `gameReady:false`. Reacquire identities and
never reuse its cached feed. Evidence:`lab1-newowner-expiry-cleanup` under the
receiver-migrations artifact root.
No further input is needed for this completed interval. The older checkpoints
below remain historical, including the pre-console controller PID61336.

[Strict sustained validation](validation/lab1-sustained480-2026-11-06.md) passed
481.134 seconds with 515 samples; independent replay verified all raw/ledger
hashes, exact identities, advancement, expiry, maximum arrival gap3.058s,
capture gap2.983s and planar drift0.0. The unchanged first attempt failed after
85s with an unavailable receipt; observer-only bounded polling/counting was
implemented and tested in `1802c4b`. Passing run had zero unavailable polls.
The original failed artifact was retained. All acceptance gates remain strict.

Recorded reader PID6464/nonce622041afc6a14371aa45ec5efcc57c8c expired
November6 9:43:08 PM Eastern; a fresh guest check verified its exit and the
receipt reader rejected the stale feed. Never reuse its pin or cached packets.
This is sustained observer-side receiver evidence, not restart, native-field,
movement or Lab2 qualification. No reload/movement/cast/Lab2 input occurred.

The sustained-run gate passed: 380 portable +317 Live .NET, 1,668 Python (2 skipped), Lua,
native smoke, ownership, format and1,022 links; evidence
`artifacts/validation/20261107T023836Z-51b6dc01`. Guest startup race fix
`54d5e95` also has26 focused passing tests. The later timed goal was cleared by the user; preserve other sessions' changes
and current owners.

### Instance-bound owners accepted, 10:30 PM Eastern

Ownership hardening was merged with the newer Lab2 inspection route, reviewed
and integrated as `23b78fb` (isolated candidate `22f91d0`). Scheduler status
now exposes the sole running PID/GUID, and controller/receiver admission binds
that PID to the verified process receipt and listener. Lab2 fast inspection
checks the same instance across both observations and retains no-legacy
admission. Explicit no-auto-start status stays diagnostic; protected operations
verify an existing owner, while STOP/release remain directly available.

All four old owners were retired before source integration. Both controllers
completed authenticated STOP, generation-specific shutdown, verified cleanup,
queue quarantine and process/port exit. The exact older Lab1 generation was
retired against all nine pinned `b2e3fa1` source blobs and its immutable receipt;
ordinary current-source admission was not relaxed. A transient immediate
receiver-vacancy failure stopped v2b safely; the continuation verified durable
queue history and all vacancies before proceeding. Lab2's intervening successful
diagnostic accounted for generations2331/2332 before shutdown2333. No queue reset,
silent re-arm, game input, reload or VM/game restart occurred.

Independent postflight verified current source/config/process receipts, Scheduler
PID/GUID, listeners, fresh VM identities, unchanged bound guest/game identities,
initial cleanup, ready/disarmed/idle status and free/unheld queues:

| Lab | Controller PID / generation | Receiver PID | Queue generation |
| --- | --- | --- | --- |
| Lab1 | 61336 / `feaac3fdb44e4027a5ad31da2dba7c7f` | 63376 | 5214 |
| Lab2 | 24412 / `37bd686548f241649ca6f5dde0586c98` | 65764 | 2334 |

These are historical checkpoint values. Reacquire them before any operation.
Evidence is under `artifacts/receiver-migrations/instance-binding-rollout-v2b`
and `instance-binding-rollout-v2b-continuation`; the latter's
`independent-postflight.json` SHA256 is
`84FBC54678981FE1F7DCB8516D138FA1426357E65B96B7DF00F50ED67A2BD6A3`.
Never rerun the one-shot migration operators against these successors.
Receiver freshness was not requalified after their restart; the earlier
sustained480 evidence applies to its recorded, now-expired reader epoch.

Host PowerShell module imports were made interpreter-local in `8a1815a` after
the first read-only preflight found `Get-FileHash` unavailable under an inherited
module path. Production import prefixes pass fresh-process tests with invalid
module paths and autoload disabled. Cleanup, configuration, replay and import
suites pass33 focused tests. The isolated ownership gate passed716 .NET and
1,724 Python tests (12 skips), Lua/native/ownership checks, then stopped at a
preexisting ignored-artifact link. The25 local evidence links are now represented
as paths. The combined main gate then passed:716 .NET,1,748 Python tests
(2 skips), native/Lua/ownership/format and1,010 links. Evidence:
`artifacts/validation/20261107T033228Z-f42863ae`; log
`artifacts/validation/combined-owner-freshness-20261106.log`.

`d68a398` bounds receipt reads through one verified handle and checks the final
same-file regular leaf and unchanged metadata. It accepts atomic replacement
completed before open;89 console/feedback tests passed. This is for the trusted
atomic publisher, not never-follow confinement or every same-metadata in-place
rewrite. Existing freshness, identity, expiry and STOP/release gates are unchanged.

That fresh-reader/bind/strict480 batch is now complete as recorded above. Root
retains all live-input ownership. The [running-helper status optimization](validation/console-interaction-speed-2026-11-06.md#running-helper-status-inspection)
was integrated as`bb3d95c`. All19 live read-only calls matched current PID/GUID;
ordinary queries averaged0.651–0.673s across four helpers, versus earlier Lab2
normal1.986s/existing inspection0.662s (three measured samples each; changed
host load prevents a controlled before/after claim). No helper restart or input
was needed. Final source/config/process/listener postflight again found both
controllers ready/disarmed/idle, queues free, same current owners. Full gate
passed716 .NET,1748 Python (2 skips), native/Lua/ownership/format and1015 links:
`artifacts/validation/20261107T040344Z-13a31e2a`. No cold start was repeated for
this status-only change.

### Advisory console phase timings integrated

`84fe0fb` integrates the reviewed timing slice (isolated commit`4a42288`, branch
`codex/console-phase-timings`). Fixed-name monotonic events go to separate v1
sidecars only after owned cleanup; canonical plan/review/execution/stdout stay
unchanged. Direct release remains untimed. Tests cover busy mutex, replaced
directories, clock/publish failure, cancellation before input, cleanup visibility,
and cancellation immediately after a successful send with canonical attempt
recording and same-plan retry refusal. The125-test console/feedback/guidance
suite passed; independent review passed69 console tests and the retry repro.
Trusted artifact directories are assumed. The combined gate passed716 .NET,
1758 Python tests (2 skips), native/Lua/ownership/format and1016 links. Evidence:
`artifacts/validation/20261107T042150Z-b4cf4cb7`; log
`artifacts/validation/console-phase-timings-20261106.log`.

No live console operation was performed for the timing change. The
`vnc-connect-initiate` phase only creates a proxy; first input/capture can include
RFB authentication. Prepare game identity is inclusive of its guest session.
Mutex waits, teardown and release are not separately measured. Collect actual
phase records during the next authorized operation; root retains all input
ownership. Do not repeat successful reload/bind merely for a benchmark.

Screenshot reuse is not implemented. Current after-screen is captured before
release and lacks hash/dimensions/actual capture-time proof. Reuse would still
need fresh VM/game admission and a separate new review; first measure the
existing phases rather than claiming the whole prepare duration can be saved.

### Native-vitals admission and replay integrated

`287a5b6`, `a310534` and `399d463` integrate the reviewed helper/workflow fixes.
Persistent preflight checks exact integer1 versions for fresh identity and native
vitals, with fixed safe refusal reasons. Persistent replay requires v2 plus a
validated response timestamp; explicit-reader v1 replay remains. Shared
`validate_response_time` enforces ordered UTC host brackets and exact100ns guest
sample/response order with the unchanged host±5s tolerance. Focused combined
checks passed90 tests; independent review passed. Full gate passed716 .NET,
1767 Python tests (2 skips), native/Lua/ownership/format and1016 links:
`artifacts/validation/20261107T044324Z-a98e4144`.

The [bounded read-only Lab2 live validation](validation/lab2-end-to-end-latency-2026-11-06.md#native-admission-and-replay-follow-up)
completed in4.978s, with screenshot lease, verified STOP/release and image review.
Health10635/10635 and resource100/100 numerically matched native candidates;
Mana was unavailable. Fields remain candidate-only. No helper/agent/VM/game
restart or gameplay input occurred. Independent artifact review passed; stored
released queue generation2336 is directly evidenced, grant2335 is inferred from
the enforced cleanup invariant. At the final recorded checkpoint
(2026-11-07T04:52:10.647668Z), the saved postflight retained four PIDs,
authenticated status, VM identities, queues5216/2336 free/unheld and
ready/disarmed/idle state. It is historical status evidence and does not retain
all source/config/Scheduler/listener proofs independently. Evidence:
`artifacts/receiver-migrations/session-final-postflight-20261106.json`, SHA256
`B97EEF634EA8441F9EEB50B30D3C68D4D62AA425A06D9E2F961865F3C4337014`.

Lab1's recorded agent advertised neither native-vitals nor fresh-identity version;
Lab2 advertised both as1. Do not infer undocumented handlers or update a healthy
agent from that observation. The persistent workflow remains explicitly Lab2-only.
The [native reference](reference/current-native-vitals.md) now accurately describes
v2 Mana/Energy per-field status and the existing direct host/guest reader route.
Physical-host metadata found no running `rift_x64.exe`; no physical game memory
was read and no physical acceptance is claimed.

**The user cleared the timed goal.** There is no active five-hour goal and no
experiment remains running. Finish this documentation checkpoint; further work
resumes only under a new instruction. Preserve current owners. Do not rerun the
one-shot migration scripts or replay old reload/bind operations. Reacquire fresh
identity, capabilities, expiry and STOP/release evidence for any future operation.

The bounded current-runtime dependency scan found no confirmed remaining active
default dependency on Workbridge, the original reader or its probe in
scripts/src/addon/config; explicit historical replay/legacy inspection remain.

The [launch-failure cleanup follow-up](validation/lab1-receiver-freshness-2026-11-06.md#launch-failure-cleanup-follow-up-1013-pm-eastern)
passed 19 focused tests and a nonsecret Lab1 deletion/fresh-session absence
smoke check. Only the failed launch's generated config is eligible, inside its
own guest session and with zero readers; unresolved cleanup remains explicit.
No additional game input or owner replacement occurred for that check.

The [offline consistency verifier](validation/lab1-sustained480-2026-11-06.md#offline-consistency-verifier)
reproduces the retained 515-sample metrics and rejects inconsistent rehashed
schemas/timelines/expiry. Its 12 focused tests pass. It checks selected recorded
output only; it grants no current freshness, artifact authenticity, VM/live
admission or full-scan-anchor qualification.

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
