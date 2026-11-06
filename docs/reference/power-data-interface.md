# Power in the live interface and field catalog

Implemented and guest-validated October 25, 2026 (local date).

The normal Windows Live reader now publishes `nativePower` in its existing
JSON snapshot. The [Power field catalog](../../config/field-catalog/power/catalog.json)
retains the validated locator, two observed game sessions, and one complete
exit/relaunch. Patch recovery remains deferred. The underlying
[locator and changed-state evidence](native-power-locator.md) are unchanged.

## Read the normal live snapshot

Run the published `RiftReader2.Live.exe` without arguments, using its existing
`riftreader2-live.json` configuration. The existing `outputPath` selects the
atomically replaced latest snapshot; the default is
`%LOCALAPPDATA%\RiftReader2\Live\latest.json`.

The added `nativePower` block has contract `native-power-observation/1`:

| Member | Meaning |
|---|---|
| `fieldId` | `player.resource.power`, matching the catalog. |
| `sourceKind` / `recipe` | `native` / `player-power-7C356C9D-v1`. |
| `status` / `reason` | `fresh`, `expired`, or `unavailable`, with failure reason. |
| `value` / `maximum` | Integer Power and cap; null when expired/unavailable. Zero Power is valid. |
| `identity` | Exact process/start/build/module identity for the read. |
| `observedAtUtc` / `expiresAtUtc` | Original read start and freshness deadline. |
| `ageMilliseconds` / `remainingFreshMilliseconds` | Monotonic age and remaining lifetime at publication. |

Native Power does not require the addon nonce binding. It never fills or
changes `riftReader2.observation`, and does not make unavailable Lua data fresh.
The existing addon binding message applies to the addon source only. `maximum`
is the native record's current cap; no separate changed-maximum test is claimed.

The native read follows each bounded addon scan and uses the existing
`freshnessTimeoutSeconds`. Age is recalculated before delivery and before the
local file is written, so delivery cannot renew a value. Expired reads retain
historical timing/identity but clear both numbers. Missing processes, unsupported
builds and failed reads clear values; normal reader termination writes an
unavailable block. No scan or offset recovery runs for an unsupported build.

A saved JSON file is a snapshot, not a continuously live value. Consumers must
check the current process identity and remaining lifetime at consumption; never
reuse `status: fresh` indefinitely. `expiresAtUtc` requires trustworthy clock
alignment when consuming on another machine. Long addon scans or poll intervals
can leave gaps longer than the Power timeout; those gaps must be treated as
unavailable. Network delivery was not exercised in this increment.

## Use the normal field-catalog/export commands

The catalog requires meaning, locator and restart-survival. Both observed
sessions are supported by recorded assessments:
`rift-1224-639285359295548343` and `rift-12076-639285736860316715`.
Update survival remains unqualified. An unobserved session or different build
does not inherit qualification, although the runtime reader can attempt the
unchanged recipe in a new process of the supported build.

From the repository root:

```powershell
dotnet run --project src/RiftReader2.Cli -- qualify-fields --catalog config/field-catalog/power/catalog.json --build-sha256 7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD --session-id rift-12076-639285736860316715 --as-of 2026-10-26T02:00:00Z --output artifacts/power-catalog.json

dotnet run --project src/RiftReader2.Cli -- export-discoveries --manifest config/field-catalog/power/discovery-sources.json --build-sha256 7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD --session-id rift-12076-639285736860316715 --as-of 2026-10-26T02:00:00Z --format json --output artifacts/power-discoveries.json
```

Use a new output filename for each run. `csv` is also supported by the same
export command. Catalog rows intentionally have no live numeric value: they
describe retained knowledge and exact applicability. Current values come from
the live `nativePower` block. The catalog's small retained originals are
byte/hash pinned; semantic status remains `supported-by-recorded-assessment`,
not independently authenticated proof. No new catalog schema was introduced.

## Verification

- Full gate: **514 .NET tests**, **820 Python passes and two skips**, Lua/C#
  contracts, native publish/smoke and formatting. Evidence:
  `artifacts/validation/20261026T013132Z-77d9dc86/`.
- Nine focused tests cover native zero/expiry/failure/build handling, source
  separation, both recorded catalog contexts, unknown context rejection, and
  the standard discovery export without an invented live value.
- The new executable was compressed, transferred through VMware Tools using
  cached login, and hash verified. SHA:
  `77CD12EB1D7AB8212DEE75333940FFFD022CC4FA17B73938B6761CC70F5D65C7`.
- A 12-second normal reader run in RIFT PID 12076 produced **16 fresh snapshots
  at 100/100**, then one terminal snapshot with null Power and maximum. Addon
  freshness remained unavailable, proving the separate native publication path.
- Guest installation:
  `C:\RIFT_TRANSFER\RR2-Power-Interface-77CD12EB1D7A`.
  Its configuration is the finite validation setup (12 seconds, two-second
  freshness timeout, small addon scan budget, local output, delivery disabled).
  It is not a newly installed background service.
- Normal JSON and CSV exports were rebuilt; both observed sessions qualified
  and an unobserved session remained unqualified. The earlier full-game restart
  evidence was reused; this integration did not restart the game or repeat casts.

Working evidence: `artifacts/power-interface-20261025-01/`.
Final state: reader exited normally, V23/input agent ready and idle, no held
input and a clear queue. NAT, HTTP, health-change and patch-recovery work were
untouched.
