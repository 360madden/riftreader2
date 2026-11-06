# Current-build vitals candidate — November 6, 2026

The new exact-build read-only `sample-current-vitals` command resolves a fresh
player/component snapshot, brackets field inputs and owner anchors, revalidates
the process, and publishes a candidate-only report without overwriting evidence.
The host wrapper stages a hash-verified reader through the VM-specific credential
workflow and verifies report identity and hashes. See [usage](../reference/current-native-vitals.md).

## Lab 2

No-input capture succeeded in RIFT PID 9752, start ticks 639294897826627677,
SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
Health was **10635/10635 candidate** and kind-4 Energy **100/100 candidate**;
read time was 7.584 ms. Original source report SHA-256
`3E3668875838F49072900C1F6B5DBB291D37157518759A3B9C3E005A909DD743`
is retained with `summary.json` under
`artifacts/native-current-vitals/runs/lab2/334a7ed14b4a401d8108f0ab67796055/`.
Reader SHA-256 `1C89D8B29A9A3A523D6B6A32F7F0DAC4E972454B5F4C3C3BD8F3C7F803F5E3C7`.
The first attempt stopped before reader launch because the encoded guest script
exceeded its size limit; staged scripts corrected the issue and passed review.

## Lab 1

No-input capture succeeded in RIFT PID 7164, start ticks 639294897866244204,
same executable and reader SHA as Lab 2. Health was **9010/9010 candidate**;
Energy was explicitly unavailable with `mana-kind-three-type-unresolved`,
as the current player is kind 3. Read time 6.643 ms. Original report SHA-256
`F5053ABA1B8AE27163FC157FD5458046D04EDF2259F42FB077DDC5EFBFCF2D6B`
is retained under `artifacts/native-current-vitals/runs/lab1/40bebc34b496435d9d8ca7938d601c8e/`.

These are acquisition and calculation candidates, not independent player/API
correlation, changed-state proof, freshness or restart qualification. No game
input, addon reload or restart was used.

## Verification

Shared lookup, XYZ, vitals reader and command: 36 focused .NET tests passed;
cast, addon-sync and vitals wrapper: 32 focused Python tests passed. Elevated
review accepted shared owner anchors, candidate math and pre-publication process
revalidation. The broader validation passed 603 .NET tests, formatting, native
smoke, Lua and Python checks but failed the final repository-wide whitespace
check on two pre-existing tracked historical Markdown files; no full gate pass.
