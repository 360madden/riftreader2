# Saved wall-motion replay — 2026-10-19

## Outcome

RiftReader2 independently reproduced the selected V1 wall-motion conclusion
from the retained batch-6 JSON Lines capture. Free travel closely matched the
saved projection, while two wall-contact trials disagreed decisively. This
disproves the projection as realized velocity for this evidence. A desired or
commanded vector remains a hypothesis rather than a qualified meaning.

This is an offline fixed-input result. It does not qualify a native velocity
field, prove the projection's meaning in every game mode, or establish current
build compatibility.

## Content-pinned input and applicability

The replay reads the V1 capture in place without importing it into the V2
repository:

`C:\rift modding\RiftReader\.riftreader-local\motion-recovery\20261018\batch-6-samples.jsonl`

| Property | Recorded value |
|---|---|
| Byte length | `100187956` |
| SHA-256 | `F1B63D83B1DB09B9D06A5A7C051F5FC56235562C748554A17BFB9C68FA8A7D54` |
| Sample count | `9598` |
| Observer instance | `bcae8028-8901-49df-a434-e1cb6248903d` |
| RIFT process | PID `9540`, start `2026-10-18T17:15:04.3406507Z` |
| RIFT executable SHA-256 | `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD` |
| V1 report build label | `STABLE-1-1169-a-1256556` |

The replay independently recomputed the source size and SHA-256 and checked the
declared observer/process/executable identity on every sample. The human-readable
build label comes from the reviewed V1 result; the executable hash is the
machine-checked build binding.

The tracked replay manifest pins the capture identity, process epoch, sample
count, and three selected trial artifacts. It uses `w6` for the free-travel
control and `wall-contact2` plus `wall-contact3` for the two decisive wall
cases. `wall-contact1` is outside this selected three-trial replay scope.

## Reproduction procedure

Run the repository command documented in the
[development workflow](../workflows/development.md). The adapter verifies the
strict manifest, source size and SHA-256, declared observer/process/build
identity, sequence and timestamp order, and each selected run SHA-256 before it
publishes a result. It streams the roughly 100 MB source rather than copying V1
application architecture or loading the whole capture into memory. The report
records the effective boundary, projection-gap, free-travel, and wall
classification thresholds used for the result.

For each trial, the replay uses the last sample at or before key-down and the
first sample at or after key-up to calculate realized XZ displacement. It takes
the median saved projection vector during the key hold, multiplies it by the
recorded hold duration, then compares projected and realized displacement.
V1 called bracket displacement divided by key-hold duration
`actualHorizontalSpeed`. V2 names the value
`bracketDisplacementPerKeyHoldSecond` to make its denominator explicit; it is
not a sample-time instantaneous or native velocity measurement.

An independent reference calculation over the same bytes was retained at
`artifacts/wall-replay/independent-reference.json`. It recomputed the capture
hash, count, process identity, trial brackets, medians, projected displacement,
direction error, and vector error without calling the V2 implementation.

## Result

| Trial | Classification | Direction error | Vector error / actual displacement |
|---|---|---:|---:|
| `w6` | free-travel plausible | `0.008074355943100176` degrees | `0.007927892359465063` |
| `wall-contact2` | decisive wall disagreement | `62.605068600620896` degrees | `1.8838513428426238` |
| `wall-contact3` | decisive wall disagreement | `62.49343354768298` degrees | `1.9452942188771931` |

The full-precision values differ slightly from the rounded numbers in the V1
report. The classifications and conclusion are unchanged. Both wall trials
also preserve the decisive sign conflict: the projection predicts positive Z
while realized displacement has negative Z.

The replay consumed all 9,598 samples from sequence 1 through 9,689. Its trial
brackets were 904–910, 6,191–6,197, and 6,709–6,715 respectively. Each trial
contained five projection samples, and every boundary and projection gap was
below the manifest's 100 ms limit.

Two final Release invocations took 887.1059 ms and 948.7362 ms, including .NET
host startup and same-handle hashing plus streaming of the 100,187,956-byte
source. Both compact `v1-wall-motion-replay/1` reports were 7,238 bytes with
SHA-256
`2B174BEFF4D15B10C1472D09F6820D288A7E7D58ECD8738090E3DFCD14715A06`.
The no-overwrite check exited 2 and preserved the existing report hash.
Repeating the command requires no numerical AI interpretation; the remaining
manual or AI step is to review the compact conclusion and its limitations.

The final repository gate passed 183 C# tests (177 core and 6 Windows), 108
Lua assertions, 22 actual-Lua-to-C# cases, and 9 Python host-gate tests. Locked
restore, a zero-warning Release build, formatting, dependency checks, the
deterministic demo, and 153 relative links also passed. Evidence is retained at
`artifacts/validation/20261019T040527Z-d6abdfaf`; the replay log and two reports
are under `artifacts/wall-replay/`.

All three trial brackets, projection counts, vectors, angles, and vector errors
matched the independent Python calculation. The numerical comparison used
`1e-7` degree tolerance for angles and `1e-10` for vectors and error fractions.

## Evidence limits

- V1 recorded the run/control timestamps on the host and sample timestamps in
  the guest observation stream. Their UTC alignment is an inherited assumption;
  this replay does not independently measure host/guest clock offset.
- The selected run artifacts record `inputSent: true`, `releaseSent: true`, and
  explicit visual review, but `gameResponseVerified: false`. The replay
  classifies the retained coordinates and projection bytes; it does not upgrade
  that historical run flag.
- The run artifacts serialize process start to microsecond precision while raw
  capture identity preserves one additional 100 ns digit. They identify the
  same process epoch because the reader requires either an exact timestamp or
  an exact match after flooring the raw epoch to one microsecond; it applies no
  general timestamp tolerance.
- Trial boundaries are source-sample brackets around the recorded key times.
  They are evidence for displacement over the interval, not exact samples at
  the input instants and not instantaneous velocity.
- The replay covers the three selected trials only. It does not reproduce the
  first wall-contact trial or V1's native-field negative scan.
- The result applies to the recorded executable, observer instance, process
  epoch, and capture bytes. It is not update-recovery evidence.
- Derived displacement and speed remain derived observations. No stored native
  velocity field is qualified.
