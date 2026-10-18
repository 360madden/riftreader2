# Proposed success measures

Status: proposed. Baselines, thresholds, sampling rates, and supported cases
must be chosen during discussion. No V2 performance results exist.

| Measure | What to record | Why it matters |
|---|---|---|
| Time to a validated finding | Start/end, input evidence, retries, and qualification outcome. | Captures useful discovery speed rather than scan throughput alone. |
| Restart reacquisition | Fresh session identity, time to a validated result, failures. | Measures whether saved knowledge remains useful after restart. |
| Update recovery | Old/new build identities, reused evidence, search stages, validation outcome. | Keeps update claims distinct from same-build restart success. |
| Observation completeness | Expected/received observations, gaps, ordering, dropped data. | Exposes missing evidence. |
| Acquisition timing | Actual intervals, capture duration, and relevant percentiles. | Separates configured rate from observed behavior. |
| Read quality | Partial/unreadable data, inconsistent object identity, stale observations. | Helps identify plausible but invalid results. |
| Local resource cost | Elapsed time, CPU, memory, bytes read/written, storage growth. | Shows where offloading or caching helps. |
| AI interaction cost | Tool round trips, input/output volume, token counts when available. | Measures repetitive work removed from the AI. |
| Reproducibility | Repeat results on fixed saved inputs and independent sessions. | Tests whether findings generalize within their claimed scope. |

## Evidence principles to discuss

- Distinguish native readings, derived values, independent references, and
  intended stimuli.
- Confirm observed movement or turning; issuing a command alone does not prove
  that the intended experimental condition happened.
- Qualify candidates with cases that distinguish competing explanations.
- Preserve failures and uncertainty alongside successful observations.
- Record capture timing and avoid assuming different machines share a clock.
- Include warm/cold tool startup and cache state in comparisons when relevant.

These are measurement suggestions. They do not select a test runner, data schema,
capture design, or acceptance threshold.
