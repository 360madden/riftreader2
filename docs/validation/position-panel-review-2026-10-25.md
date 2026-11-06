# Reusable position-panel evidence audit — October 25, 2026

Implemented `scripts/review_position_panel.py` to replay saved panel evidence
without process reads, scanning, VM input or a new guest deployment.

The retained original directories were reviewed in place under
`artifacts/update-recovery-20261023-01/xyz-interface-restart-oct25-01/verified-originals/panel-01`
and the corresponding `xyz-interface-restart-oct25-02` directory. Inputs were
not modified. Derived reports are
`artifacts/validation/position-panel-review-initial-01.json` and
`artifacts/validation/position-panel-review-corrected-01.json`.

| Retained trial | Report files | Live states | Subnormal raw observations | Live subnormal findings | Result |
|---|---:|---:|---:|---:|---|
| Initial reader | 226 | 226 | 48 | 48 | Recorded checks failed, as expected |
| Corrected reader | 323 | 263 | 59 | 0 | Recorded checks passed |

The corrected journal also records 59 `position-values-not-ready` states. Both
sessions retain two process epochs. Those counts alone do not prove a complete
game restart: the [original corrected trial](position-panel-corrected-restart-2026-10-25.md)
preserves the independent absence, relaunch, pointer and cleanup evidence.

The checker rejects missing/tampered reports, unsafe report paths, inconsistent
profiles/identities and unmatched live observations. Behavioral findings retain
their journal line and, for a live subnormal value, original report filename.
This is an audit of recorded evidence, not a UI/timing acceptance test or field
qualification. See the [workflow and command](../workflows/xyz-collection.md).

Validation: 20 focused synthetic tests passed, including tampering, unsafe paths,
profile/identity mismatches, late report reuse, ambiguous outcomes, timestamp and
read-order errors, and false subnormal withholding. The full repository gate
passed 469 .NET, 682 Python, 108 Lua and 22 Lua/C# checks plus publication,
formatting and 565 documentation links before the final outcome/order tightening.
That tightening retained the historical 48-finding/zero-finding replay results;
the complete Python suite passed **689/689** afterward. Logs are
`artifacts/validation/position-panel-review-full-gate.log` and
`artifacts/validation/position-panel-review-final-python.log`.
