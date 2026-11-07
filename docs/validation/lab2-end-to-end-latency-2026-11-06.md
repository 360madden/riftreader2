# Lab 2 end-to-end diagnostic latency — November 6, 2026

This follow-up runs an actual read-only diagnostic: admit the existing Lab 2
controller, freshly verify the game, optionally acquire native vitals candidates,
capture the game window under an exclusive queue lease, verify watchdog cleanup,
recheck identities and artifact hashes, then review the image separately.

All live guest operations were on Lab 2. No game input, focus command, game/VM
restart, Windows security/power change, or Lab 1 guest operation was performed.
The earlier login/identity improvements are documented in
[the preceding implementation note](lab2-latency-improvements-2026-11-06.md).

## Measurements and scope

Evidence is retained in `artifacts/e2e-latency-20261106/`. Connector call traces
use a single root clock. Child stage durations use host `perf_counter` and are
reported independently; clocks are never subtracted to invent network or model
reasoning time. Machine-workflow completion ends with the verified report, before
the later image review and conversational answer.

| Same screenshot diagnostic through Workbridge | Observed span | Connector calls | Jobs | Child duration |
| --- | ---: | ---: | ---: | ---: |
| Separate preflight/capture/verify jobs | 44.049 s | 15 | 3 | 17.974 s total |
| One job, original admission behavior | 22.043 s | 10 | 1 | 17.507 s |
| One job, scoped in-process admission | 8.837 s | 6 | 1 | 5.827 s |

Each remote row is one observed run, not a latency percentile. The first change
keeps the same admission behavior and reduces the observed span by 22.006 s
(49.96%). The final displayed configuration changes both admission reuse and
intermediate VM verification; its total observed reduction from the first row is
35.212 s (79.94%). Do not attribute that total to batching alone.

The original remote workflow had 19.743 s of phase-transition return-to-next-
dispatch gaps (8.655 s and 11.088 s); the one-job runs have none. Within-phase
gaps were 2.321, 2.069 and 1.296 s respectively, including intentional 250 ms
polling backoffs. The gaps can include orchestration, rendering and scheduling;
call round trips also include transport effects. Neither observation isolates
the model's internal reasoning.

Three local scoped runs had a child median of 6.038 s (5.988–6.077 s), with a
dispatch-to-result median of 6.867 s (6.822–6.886 s). Managed-plan admission was
then the dominant child stage: median 4.211 s. The screenshot itself took about
0.18–0.21 s. Raw traces, stage receipts and comparison provenance are retained in
`remote-batch-comparison.json` and `scoped-workflow-comparison.json`.

## Removed repeated work

`scripts/inspect_lab2_workflow.py run` keeps one admitted host in a bounded local
process. It still rereads and hashes its immutable plan/state, verifies the
original controller process/source/config/listener and authenticated connection,
and checks the exact VM process/start/log/listener at each intermediate boundary.
It performs full VMware inventory checks at admission and before publishing the
report, including rejection of a sibling VMX sharing the running log. Failed
post-admission runs also attempt the final inventory check after lease cleanup.
Ordinary movement and maintenance hosts keep their original full inventory checks.

The Lab-2-only inspection task proof uses fresh Task Scheduler COM observations,
reusing the original registration digest, path, action, principal and settings
predicates. It checks the exact root task is Running and that the competing
legacy task is absent; only the explicit file-not-found HRESULT proves absence.
It reads both names twice per proof. The fast route refuses legacy fallback and
cannot register/start tasks or inspect another lab. The ordinary manager remains
available for its original operations. Microsoft's
[registered-task state documentation](https://learn.microsoft.com/en-us/windows/win32/taskschd/registeredtask-state)
describes the dynamic state exposed by this API.

## Native executable reuse

The original native wrapper staged a new 117 MB executable for every small
sample. One measured baseline took 74.142 s (74.349 s with outer identity guards),
while its actual native read reported 8.066 ms.

Explicit reuse of an existing Lab 2 managed release reduced the complete operation
to a median 8.957 s over three final trials (8.949–9.455 s); outer guarded median
was 9.219 s (9.155–9.696 s). Relative to the single baseline and optimized median,
the observed operation reduction is 65.186 s (87.92%). This is one before sample
and three after samples, not a comparison of two measured baseline medians.

Reuse accepts only a canonical Lab 2 managed executable path and requires the
expected game identity. The host hashes its published reader; the guest checks
all executable ancestors for reparse points and hashes full reader bytes at
preflight and launch. At launch it holds the read-only file handle through native
execution, denying writes/deletion/replacement. A missing or wrong executable
fails without copying or selecting a fallback. An optional expected VM pin is
compared immediately after collection, before any guest session or staging.

The final reuse trials retain the same VM, game process epoch, game build and
reader hash as the baseline; source report hashes were independently rechecked.
The unused generated baseline executable was removed by exact path/hash only;
its host evidence and the active managed release were retained.

The explicit-reader joined workflow completed in 16.676 s inside the child. Its
native observation finished at 02:52:20.259553 UTC and its screenshot followed
2.925469 s later on the same guest clock. Root image inspection saw HP 10635/10635
and resource 100/100, matching the native HP/Energy candidates. The scene rendered
normally, with an AFK character and no blocking modal/black frame. This is static
visual corroboration only. Semantic meaning under changed state, passive
freshness and restart qualification remain unverified. Mana correctly remained
unavailable for the current non-Mana resource kind.

## Final persistent native path

`POST /api/native-vitals` now performs the same bounded candidate acquisition
inside the existing authenticated guest agent. It accepts only the four expected
identity fields, checks the configured machine/path and exact supported build,
opens a new read-only native session, and hashes game executable bytes at open
and post-read revalidation. The candidate lookup/calculation is shared with the
CLI. No process launch, executable transfer, guest output path, cached native
session, reused address or cached game hash is involved. The response includes
the actual executor instance ID, which must match the authenticated pre-status
instance and the workflow's original admission.

One background read lane requires disarmed/idle control with no pending recovery,
has a five-second cooperative cancellation deadline, and refuses competing reads,
arm, input, capture, identity and recovery while unfinished. STOP cancels it and
acknowledges without joining it; disconnect cancels and joins before reconnecting.
The host rejects input lease envelopes on this read-only route and brackets the
request with authenticated VM checks. The Python client independently brackets
the exact expected VM, validates freshness/report bounds/contract/identity, and
publishes a new local report only after final validation. There is no fallback.

| Final operation | Measured result | Samples |
| --- | ---: | ---: |
| Persistent native query, including its VM/report checks | 0.2186 s median; 0.1964–0.2945 s | 5 |
| Persistent native query plus outer fresh identity guards | 0.4452 s median; 0.4111–0.5228 s | 5 |
| Joined native/UI child workflow | 4.1049 s median; 4.0306–4.3005 s | 3 |
| Joined local dispatch to result | 4.947 s median; 4.878–5.197 s | 3 |
| Screenshot-only child, after faster task proof | 3.5974 s median; 3.5709–3.8649 s | 3 |
| Final screenshot through remote connector | 5.898 s, 3 calls, 1 job | 1 |
| Final joined native/UI through remote connector | 5.826 s, 3 calls, 1 job | 1 |

The screenshot remote comparison is 44.049 → 5.898 s, an observed 86.61%
reduction for this pair. The native-operation comparison is 74.1425 → 0.2186 s
(single baseline versus five-run final median), about 99.71%. Relative to the
already-optimized explicit-reader median, the persistent query is about 41 times
faster. These scopes exclude the conversational response and subsequent visual
review. Different timing scopes and sample counts must remain visible.

The final local joined sample-to-screenshot interval was median 0.563891 s
(0.551374–0.621485 s); the final remote joined observation was 0.526354 s.
Root reviewed the latter image and saw matching HP 10635/10635 and resource
100/100, a normally rendered game scene and no blocking modal. Matching static
values retain the candidate limitations stated above.

Live wrong-PID native acquisition was refused in 0.050 s without publishing a
report. The corrected watchdog probe observed nativeReadBusy, finished its own
lease, observed native refusal during cleanup, and verified cleanup in 0.488 s.
This is finish-to-attested-cleanup, not isolated HTTP STOP latency or unique proof
of the cancellation cause. A deliberately delayed-reader .NET test independently
proves STOP acknowledgement before the native task finishes. The first live probe
used an idle-only polling predicate and failed closed; its own cleanup passed and
that attempt is excluded from responsiveness results.

The exact Lab 2 host was gracefully reloaded after independently proving its old
task/process/config/source/VM ownership. A post-launch assertion initially ran
before the guest reconnected; explicit subsequent admission verified the new
controller, unchanged game target and safe reconnect. An admission attempted
during source editing also refused the source mismatch, as intended.

Activated guest release: `agent-221af549f59b-zip`, executable SHA-256
`221AF549F59BF38FBF792C59BE3C9B7EFF09A3BA85ABB4FC6A1DE4DA6FDF3F9A`.
The ZIP transfer was 47,768,183 bytes and took 25.640 s. The existing guarded
launcher verified graceful replacement and the new authenticated agent instance.
Rollback descriptor and the prior release remain retained in
`artifacts/e2e-latency-20261106/activation/rollback-release.json`. The game and VM
epochs remained unchanged throughout. These evidence identities are not reusable
authority for a future run.

Full validation passed: 380 portable and 336 Live .NET tests; 1,720 Python tests
with two skips; locked restore/build/format, published native smoke, real Lua 5.1
contracts, deterministic replay and 1,029 relative links. Evidence:
`artifacts/validation/20261107T030027Z-847d055a`. An independent agent rechecked
14 native source reports and nine workflow receipts/hashes against retained
process plans; historical source hashes were distinguished from activated source.
The consolidated comparison is `final-performance-summary.json`.

Ten additional light joined checks at one-minute intervals all passed. The first
dispatch through final return spanned 03:07:30.303541–03:16:34.700587 UTC
(9 minutes 4.397 seconds). Child median was 4.2219 s, range 4.0368–4.5090 s;
local subprocess dispatch median was 4.4464 s, range 4.2653–4.7412 s. Native-to-
screenshot median was 0.569634 s, range 0.495324–0.609471 s. The independent
`stability-audit.json` verifies every report/image hash, original VM/game identity,
retained controller/source/config proof, unique named lease and attested cleanup.
Between-check gaps of approximately 55 seconds were unobserved; this is sampled
stability, not continuous freshness or general reliability qualification.

Across those ten checks the largest stage medians were managed-plan admission
1.7764 s, native-candidate stage including surrounding validation 0.5388 s,
final inventory/managed proofs 0.3718 s, watchdog cleanup 0.3399 s, and screenshot
0.1879 s. The native-stage scope differs from the standalone query and raw read.
These identify the remaining measured cost without attributing it to model time.

A final controller-only graceful reconnect was proven against the current source
commit. The previous admission plan was refused in 0.0152 s; a newly admitted
joined workflow then passed in 4.0796 s. VM/game epochs and the deployed guest
agent remained unchanged. Root reviewed the final interval and post-reconnect
images: matching static HP/resource values and a normally rendered scene.
Receipts are under `reconnect/` and `joined-after-reconnect-01/`. All sampled final
states were disarmed, idle, without sampled held inputs, with released leases.

## Reuse the workflow

Choose a new output directory for every attempt; failed attempts remain available
for diagnosis. Screenshot-only:

```powershell
python scripts/inspect_lab2_workflow.py run `
  --output C:\work\riftreader2\artifacts\e2e-latency-20261106\<new-run>
```

For the fast joined diagnostic, add `--native-vitals` to that command. It requires
the current persistent native capability and refuses an unsupported/replaced
agent. It is mutually exclusive with the explicit-reader options below.

Copyable PowerShell invocation from any working directory:

```powershell
Set-Location -LiteralPath 'C:\work\riftreader2'
$lab2RunRoot = Join-Path 'C:\work\riftreader2\artifacts\e2e-latency-20261106' ([guid]::NewGuid().ToString('N'))
& 'C:\Python314\python.exe' scripts\inspect_lab2_workflow.py run --native-vitals --output $lab2RunRoot
```

RIFT must already be running in Lab 2, foreground and disarmed. The workflow
refuses changed target identity/geometry or a busy/recovering controller. Inspect
the returned `report.json` and `capture/image.bmp`; image review is a separate
step after release. On refusal, inspect stderr and the retained `run-failure.json`
and stage timings when available. Use a new result directory for the next attempt.

The explicit-reader alternative adds all three options together:

```powershell
  --native-reader C:\absolute\published\RiftReader2.Live.exe `
  --native-reader-sha256 <EXPECTED_READER_SHA256> `
  --guest-reader C:\RIFT_TRANSFER\RiftReader2Control\managed-fleet-20261029\releases\<release>\RiftReader2.Live.exe
```

Capture acquires only its named queue request. Its worker never issues an
unconditional STOP after lease loss; the existing watchdog performs exact cleanup.
Success requires the expected terminal state, original epoch, cleanup generation
increment and nonempty cleanup receipt. Artifact verification rejects target,
geometry, UTC-window, BMP length/dimensions/hash or native report/identity drift.
Images are reviewed after the lease is released.

Optional rollback of the guest agent through the same guarded launcher:

```powershell
Set-Location -LiteralPath 'C:\work\riftreader2'
$lab2RollbackRoot = Join-Path 'C:\work\riftreader2\artifacts\e2e-latency-20261106' ('rollback-' + [guid]::NewGuid().ToString('N'))
& 'C:\Python314\python.exe' scripts\guest_agent_launcher.py update --managed-lab lab2 `
  --release artifacts\e2e-latency-20261106\activation\rollback-release.json --output $lab2RollbackRoot
```

The retained descriptor selects the prior `agent-379637a8d2c0-zip` release. That
version lacks persistent native vitals: use screenshot-only or the explicit-reader
alternative after rollback. This command is documented for recovery; the measured
new release remained active at the final recorded checkpoint. Reacquire its
identity and capabilities before another operation.

## Native admission and replay follow-up

Commits `287a5b6`, `a310534` and `399d463` check requested persistent native
capabilities during joined preflight, require v2 plus its envelope timestamp
for persistent replay, and enforce ordered UTC host brackets and exact 100 ns
guest sample/response chronology. The existing five-second host/guest tolerance
and explicit-reader v1 historical replay remain. The combined focused suite
passed 90 tests; targeted control review passed.

One bounded read-only `run --native-vitals` completed in 4.978142 seconds under
`artifacts/e2e-latency-20261106/native-admission-live-validation`. It verified
the unchanged Lab2 game/agent/VM identity, candidate report v2, screenshot lease,
STOP and cleanup before visual review. The captured-and-released receipt records
released queue generation 2336. No helper, agent, VM or game restart and no
gameplay input occurred. The preserved controller remained connected, ready,
disarmed/idle with no sampled held inputs and its console reservation retained.

The image shows Bolinao AFK, health 10635/10635 and resource bar 100/100, matching
the native candidate numbers. Mana is unavailable (`not-mana-kind-three`). This
single unchanged-state numeric match does not qualify semantics, passive
freshness, changed-state behavior or restart recovery. The native report's
`candidate-only` qualification remains authoritative.

Independent saved-file validation checked state/plan/controller/source/receipt
hashes, v2 timing at exact tick precision, capture metadata and image, visual
review binding and cleanup. Review SHA256:
`9137C77B7C417A5398DE0018D17C731E1275F000EAB5E98CD232C068F6490FC4`.
The review labels grant generation 2335 as inferred from the source-enforced
cleanup increment; the retained release explicitly records 2336. It does not
authenticate saved artifacts or establish present state.

The full local gate passed 716 .NET and 1767 Python tests (2 skips), native/Lua/
ownership/format and 1016 links. Evidence:
`artifacts/validation/20261107T044324Z-a98e4144`; log
`artifacts/validation/native-vitals-admission-20261106.log`.
