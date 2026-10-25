# Real XYZ field catalog

The real XYZ catalog is in
[`config/field-catalog/xyz/`](../../config/field-catalog/xyz/). It turns the
October 25 retained observations into a mechanically evaluated field record;
it does not scan RIFT or contact the VM.

## Current qualified context

For executable SHA
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`
and post-relaunch session `rift-1224-639285359295548343`, the catalog records:

| Claim | Status | Recorded basis |
| --- | --- | --- |
| Meaning | `supported-by-recorded-assessment` | Native and Lua endpoints agreed within 0.02 units per axis; their guarded-movement displacement agreed within 0.04 units per axis. |
| Locator | `supported-by-recorded-assessment` | Main-module RVA `0x32E0200` resolved an x64 owner; float32 X/Y/Z came from owner offsets `0x320/0x324/0x328`. |
| Restart survival | `supported-by-recorded-assessment` | Explicit records cover pre-exit session `rift-11712-639285339497136209` and fresh post-relaunch session `rift-1224-639285359295548343` on the same build. |
| Update survival | `unqualified` | No second executable build has been assessed. |

The field requires meaning, locator and restart-survival, so its aggregate
status in the post-relaunch context is
`supported-by-recorded-assessment`. Update survival is deliberately not a
required claim and remains unqualified.

The module-relative recipe is durable; an absolute resolved owner is not.
Every sample must re-resolve the owner. A different executable SHA, stale
process identity, failed pointer read, nonfinite/subnormal value, or native/Lua
disagreement invalidates use until reviewed.

## Rebuild the report

Run from the repository root:

```powershell
dotnet run --project src/RiftReader2.Cli -- qualify-fields --catalog config/field-catalog/xyz/catalog.json --build-sha256 7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD --session-id rift-1224-639285359295548343 --as-of 2026-10-25T18:00:00Z --output artifacts/validation/xyz-field-catalog-20261025-02/current-session-report.json
```

The evaluator verifies every retained file's byte length and SHA-256. The
expected report has catalog SHA-256
`C60BC237F08390709BC4AF9A4B24DB968F18D637F849F8C51741CBB17F6C1AD1`,
field-definition SHA-256
`0F5FAA3661BBA09845D252B6226C465BBA584F18FBBCDC00C1119101803DD4D8`,
and `artifactVerification: verified-retained-bytes`. It labels semantic
verification `recorded-assertions-only` and build/session identity
`declared-only`; those boundaries are intentional.

Evaluating the earlier session is also useful:

```powershell
dotnet run --project src/RiftReader2.Cli -- qualify-fields --catalog config/field-catalog/xyz/catalog.json --build-sha256 7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD --session-id rift-11712-639285339497136209 --as-of 2026-10-25T18:00:00Z --output artifacts/validation/xyz-field-catalog-20261025-02/before-session-report.json
```

That earlier context supports the restart endpoint but remains aggregate
`unqualified`: no separate meaning or locator assessment was asserted for it.
This prevents the restart evidence from silently becoming semantic evidence.

## Retained evidence and limits

The catalog keeps hash-pinned copies of the corrected restart manifest, both
pointer-follow reports, the guarded displacement review and action receipt, and
the initial and corrected panel reviews. The initial review remains because it
found 48 live subnormal startup presentations. The corrected review recorded
59 raw subnormal startup observations as withheld and found no live leak. The
bad initial presentation is implementation history, not proof that subnormal
coordinates are valid.

| Catalog copy | Retained original |
| --- | --- |
| `restart-package.json.raw`, `before-pointer.json.raw`, `after-pointer.json.raw` | `artifacts/update-recovery-20261023-01/xyz-interface-restart-oct25-02/verified-originals/` |
| `motion-review.json.raw`, `motion-action.json.raw` | `artifacts/validation/xyz-guarded-displacement-20261025-01/` |
| `panel-initial-review.json.raw` | `artifacts/validation/position-panel-review-initial-01.json` |
| `panel-corrected-review.json.raw` | `artifacts/validation/position-panel-review-corrected-01.json` |

The assessment files pin each copy's exact byte length and SHA-256. The
catalog separately pins both assessment files, so a changed observation or
review cannot silently retain its status. The `.json.raw` suffix marks these
as byte-preserved retained data; unlike authored JSON source, their original
newline convention is not rewritten.

Confidence is intentionally narrow:

- Only one complete game exit/relaunch pair was observed.
- The guarded movement comparison was one bounded 100 ms W pulse. It supports
  coordinate meaning, not speed or continuous tracking.
- Hash verification proves retained-byte consistency, not independent
  authenticity of reviewer or session declarations.
- No patch/update survival, reboot survival, or all-fields survival is claimed.
- Direct in-guest Computer Use and patch recovery remain deferred.

When new real evidence arrives, retain it as a new sibling file, add a new
assessment with its exact length and SHA-256, and run `qualify-fields` again.
Do not edit retained evidence or broaden the executable/session applicability
to make a claim pass.
