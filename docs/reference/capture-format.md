# Offline capture and report contracts

Version: 1. This is a saved-evidence interchange format, not a qualified live
capture protocol. See `samples/demo/` for complete synthetic files.

## Capture bundle

The manifest is UTF-8 JSON, at most 65,536 bytes. All fields are required:

| Field | Meaning |
|---|---|
| `schemaVersion` | Integer 1. Other versions fail. |
| `buildSha256` | 64 hexadecimal characters declaring the source build identity. |
| `sessionId` | Nonblank string, maximum 256 characters, compared exactly. |
| `samplesFile` | Plain filename beside the manifest; no directory, drive, or stream path. |
| `samplesSha256` | SHA-256 of the exact saved sample bytes. |
| `sourceKind` | `synthetic` or `rift-recording`; declared origin, not a qualification verdict. |
| `positionUnits` | Nonblank unit label, up to 64 characters. |
| `coordinateFrame` | `xz-horizontal-y-up`; other frames need an explicit conversion. |
| `clockBasis` | `session-monotonic-seconds`; a single elapsed-time basis for this session. |
| `timingUncertaintySeconds` | Finite nonnegative timing uncertainty, or explicit null when unknown. |

The reader checks the samples digest before analysis. This verifies bytes against
the declaration; it does not independently establish the original executable,
collector correctness, timestamp accuracy, or trustworthiness of a manifest.
The same open handle is retained for replay. Supported execution is Windows;
no cross-platform concurrent-writer guarantee has been qualified.

Samples must be strict UTF-8 without a BOM, one JSON object per line, maximum
16,384 characters per line. LF and CRLF are accepted; an ending newline is
optional. Blank lines, null rows, and missing/unknown/duplicate members fail.
Every row requires:

| Field | Type and rule |
|---|---|
| `sessionId` | Must equal the manifest session. |
| `sequence` | Nonnegative signed 64-bit integer, strictly increasing. |
| `timestampSeconds` | Finite nonnegative elapsed seconds from one session clock, strictly increasing. |
| `x`, `y`, `z` | Finite doubles in the same coordinate frame and units. XZ is the horizontal plane. |
| `yawRadians` | Finite angle in radians, with a consistent yaw convention across the session. |

Sequence gaps count missing observations between received rows. A nonzero
initial sequence does not imply a known count of lost initial samples. The
format cannot prove that unrecorded observations ever existed outside its range.
At least two rows are required by `analyze` and `validate-capture`.

## Analysis configuration

An explicitly selected configuration requires `schemaVersion: 1`,
`analysis.maxGapSeconds`, `analysis.maxSamples`, and `maxCaptureBytes`.
No ambient config search or environment override occurs. Omitting `--config`
uses built-in defaults, identical to `config/default.json`.

`maxGapSeconds` is positive and finite; `maxSamples` is at least 2;
`maxCaptureBytes` is in [1, 8589934592]. Counts over a limit fail the whole
operation instead of returning an apparently complete partial result.

## Derived report

Report schema 1 records `analyzerVersion`, `evidenceKind: derived-motion`, a
tool version and SHA-256 map of the four product assemblies, source metadata
and digests, effective analysis/size settings, and summary. The report's
`input.buildIdentityVerification` is `declared-only`; its
`input.samplesHashVerification` is `verified`. Output DTOs belong to
Infrastructure and explicitly map inputs, avoiding accidental output changes
when input formats evolve. Assembly digests identify the concrete implementation
even for an uncommitted development build; retain the source commit or binaries
separately when future reproduction is required. Runtime/OS differences remain
an environmental concern outside this implementation fingerprint.
No wall-clock generation time is included: repeated inputs/configuration and
the same analyzer produce identical report bytes. Change `analyzerVersion`
when changing mathematical meaning or analysis behavior.

Derivatives are computed only when sequence increments by one and elapsed time
is no greater than `maxGapSeconds`. A skipped interval can count as both a
sequence gap and a timing gap, but is counted only once in skipped intervals.

Horizontal speed is `hypot(deltaX, deltaZ) / deltaSeconds` in source units per
second. Absolute yaw rate is the shortest wrapped angle change divided by the
actual interval, in radians per second. These are interval averages. Yaw
sampling assumes less than half a turn between observations; aliasing cannot
be ruled out from endpoint samples alone. No native velocity or rate is inferred.

Maxima are null if no interval qualifies. Non-finite input or derived arithmetic
fails explicitly. Reports are published with a same-directory temporary file
and no-overwrite move; this is complete-file publication, not a backup system
or a guarantee against every filesystem/power-loss failure.

`validate-capture` also checks semantic ordering and analysis bounds, then prints
a compact validity/digest result. It does not write a derived report.

## Compatibility

Unknown versions fail. A future format change needs an explicit migration or
adapter, tests for prior/current versions, and a decision record. Keep raw
evidence identifiable; never edit an old capture to make a new reader accept it.
