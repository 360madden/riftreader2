# Open questions

Status: revised after the modular offline foundation was authorized and built on
2026-10-18. See [current status](../status.md),
[ADR 0001](../decisions/0001-modular-offline-foundation.md), and
[the roadmap](implementation-roadmap.md).

## Resolved foundation choices

The project now uses a pinned .NET 10 SDK, four enforced production modules, an
xUnit test project, strict versioned JSON boundaries, streaming offline
analysis, explicit CLI composition, and file-based artifacts. The initial
synthetic slice and repository gate are implemented. These are current choices,
not open architecture questions.

## Next outcome questions

The [hybrid requirement](../decisions/0002-hybrid-addon-and-reader.md) makes a
minimal Lua/C# contract the next foundation increment. The
[dated first-objective comparison](first-objective-options.md) still explains
why reproducing the saved wall-motion conclusion is the recommended next
evidence result. The foundation does not resolve these questions:

| Question | Why it changes the next increment |
|---|---|
| What minimal API observation and capability states should the first Lua producer expose? | Defines the smallest interoperable Lua/C# contract. |
| Which transport and reload/session rules can the current client support and validate? | Establishes live acquisition separately from valid payload decoding. |
| Which exact saved V1 files form the first immutable evidence bundle? | Determines hashes, format adaptation, applicability, and reproducibility limits. |
| Is the wall-motion rejection still the highest-value first V1 result? | Confirms whether fixed-input reproducibility remains ahead of restart or new-field work. |
| What compact result must an independent replay preserve? | Prevents an importer from reproducing numbers while losing uncertainty or semantics. |
| Which V1 capability merits selective adaptation after independent review? | Avoids duplicate work without inheriting V1 architecture or assumptions. |
| Which effort measures should be captured during the replay increment? | Measures local work and repeated AI work removed by the foundation. |

## Later capability questions

| Topic | Decision still needed |
|---|---|
| V1 import | Input bundle, conversion boundary, retained provenance, and rejection behavior. |
| Lua addon | Current-client API subset, bounded workload/configuration, producer/schema pairing, deployment, and shared contract tests. |
| Native capture | Process/build identification, read-only scope, timing, failure behavior, and platform test seam. |
| Field catalog | Qualification states, confidence, contradiction, invalidation, and consumer contract. |
| Persistence | When measured query or integrity needs justify adding SQLite indexing to retained artifacts. |
| Experiments | Supported movement/turning stimuli, observation methods, completion checks, and recovery behavior. |
| Timing | Required delivered interval, capture completeness, clock alignment, and uncertainty. |
| REA | Tasks to delegate to the installed tool and whether persistent session access is needed. |
| Consumer access | Which export or interaction contracts future programs actually require. |
| Validation | Independent reference, restart cases, changed-build cases, and acceptance thresholds. |
| Performance | Baseline workloads, elapsed-time budget, local resource use, and AI interaction cost. |

## Recording outcomes

Record adopted material choices in
[the decision register](../decisions/README.md). Retain alternatives as dated
proposals when useful. Implementation may continue within the authorized scope
and current repository instructions; do not invent an approval requirement for
routine work already authorized.

Resolve only the choices needed for the next measurable increment. Later
capabilities can remain open until evidence makes the tradeoff concrete.
