# Top 20 proposals for discussion

Status: **proposed**, captured from the 2026-10-18 discussion.
This order is an initial recommendation, not an approved build sequence or
application decomposition. All designs, dependencies, and priorities can change.

| ID | Proposal | Intended practical benefit |
|---|---|---|
| P01 | Local experiment runner | Complete a bounded collection and validation scenario with fewer AI round trips. |
| P02 | Local numerical candidate analysis | Filter and rank candidates using complete datasets; return reasons and unresolved ambiguity. |
| P03 | Durable field definitions and locating recipes | Preserve meaning, units, applicability, resolution steps, and evidence across sessions. |
| P04 | Fast restart reacquisition | Reuse applicable knowledge, resolve fresh addresses, and verify the result. |
| P05 | Staged recovery after game updates | Identify the build, test applicable knowledge, and broaden only unresolved searches. |
| P06 | Complete buffered experiment recording | Preserve observations needed for investigation and disclose gaps or dropped data. |
| P07 | Efficient shared memory read planning | Reduce redundant resolution and reads while preserving consistency checks. |
| P08 | Cache stable metadata | Avoid rediscovering unchanged information and invalidate it when its basis changes. |
| P09 | Indexed binary evidence storage | Find relevant captures and observations without repeatedly scanning whole archives. |
| P10 | Replay saved captures | Evaluate new analysis ideas against existing evidence before collecting again. |
| P11 | Discriminating test protocols | Use cases such as body turning versus camera rotation to reject misleading candidates. |
| P12 | Record object and component relationships | Preserve structural clues that help validate and relocate fields. |
| P13 | Independent session and holdout validation | Reduce accidental promotion of candidates that fit only one experiment. |
| P14 | Consistent live and offline resolver semantics | Avoid differing pointer operations or interpretations across analysis paths. |
| P15 | Dependency-aware invalidation | Recheck affected findings when a root, build, recipe, or analyzer changes. |
| P16 | Resumable discovery jobs | Preserve completed stages and negative findings across interruption. |
| P17 | Compact AI evidence interface | Return findings, exceptions, and evidence references with targeted drill-down. |
| P18 | Sampling matched to each experiment | Measure actual delivered observations and use rates appropriate to the question. |
| P19 | Export reusable knowledge for other programs | Make qualified information understandable without requiring those programs to repeat discovery. |
| P20 | Benchmark validated discovery cost | Track elapsed time, local work, AI interactions, and reliability together. |

## Questions to apply to each proposal

- What current delay or failure would this remove?
- What existing RiftReader, Workbridge, or REA capability can be reused?
- What evidence would show that it helped?
- What could produce a plausible but incorrect result?
- What is the smallest useful scope?

A score or correlation supports a hypothesis; it does not establish a field's
meaning. A configured sampling rate does not establish delivered rate. An update
recovery method remains unproven until evaluated on the relevant changed build.

Source: assistant recommendations discussed with Joey on 2026-10-18. These are
planning ideas, not implemented capabilities or accepted architecture.
