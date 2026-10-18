# Open questions

Status: open for discussion with Joey. No default answer in this file selects
an architecture.

## First discussion

| Question | Why it changes the first useful increment |
|---|---|
| What first field or behavior should V2 discover or revalidate? | Establishes a concrete result against which to evaluate the work. |
| Which delay matters most today: collection, analysis, restart recovery, update recovery, or AI interaction? | Helps choose the first measurable improvement. |
| Should the first experiment use VMware, native RIFT, or saved captures? | Determines available evidence and operational conditions. |
| Which existing V1 capabilities should be reused, adapted, or studied only? | Avoids both unnecessary replacement and accidental inheritance. |
| What evidence would make the first result trustworthy? | Defines validation independently of a plausible output. |

## Subsequent design choices

| Topic | Decision still needed |
|---|---|
| Language and runtime | Whether C#/.NET 10 and any supporting tools fit the chosen increment. |
| Application layout | Responsibilities, process boundaries, and project structure. |
| Persistence | Storage format or engine, indexing, retention, backup, and versioning. |
| Resolution | Field definitions, locating operations, invalidation, and repair strategy. |
| Experiments | Supported stimuli, observation methods, completion checks, and recovery behavior. |
| Timing | Required sample interval, capture completeness, clock alignment, and uncertainty. |
| REA | Tasks to delegate to the installed tool and whether persistent session access is needed. |
| Consumer access | Which export or interaction contracts future programs actually require. |
| Validation | Independent reference, restart cases, changed-build cases, and acceptance thresholds. |
| Performance | Baseline workloads, elapsed-time budget, local resource use, and AI interaction cost. |

## Recording outcomes

Record Joey's actual choices in [the decision register](../decisions/README.md).
Retain alternatives as proposals when useful. An evidence-backed recommendation
does not become a user decision without an instruction adopting it.

The next discussion can resolve only the choices needed for the first useful
increment. It need not settle every future feature.
