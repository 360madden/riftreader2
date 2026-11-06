# Success measures

Status: measurement framework. The offline foundation has a verified functional
baseline; performance thresholds, sampling rates, and live supported cases
remain open. See [current status](../status.md) and
[the foundation validation](foundation-2026-10-18.md).

## Current foundation baseline

On 2026-10-18 the full repository gate passed 75 tests in Release with zero
build warnings, exact SDK and locked restore enforcement, formatting and module
dependency checks, byte-identical repeated synthetic analysis, and 89 relative
link checks. The synthetic report also matched independently stated fixture
expectations.

This establishes reproducible offline processing for the tracked illustrative
fixture. It is not a throughput benchmark and provides no evidence of RIFT
field semantics, native capture, restart reacquisition, or update recovery.

## Measures for later capabilities

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

## Evidence principles

- Distinguish native readings, derived values, independent references, and
  intended stimuli.
- Confirm observed movement or turning; issuing a command alone does not prove
  that the intended experimental condition happened.
- Qualify candidates with cases that distinguish competing explanations.
- Preserve failures and uncertainty alongside successful observations.
- Record capture timing and avoid assuming different machines share a clock.
- Include warm/cold tool startup and cache state in comparisons when relevant.

The architecture now selects a test runner and versioned capture/configuration
schemas for the offline slice. The measures above continue to govern later
evidence; numeric acceptance thresholds should be adopted only for the
capability and workload they claim to qualify.
