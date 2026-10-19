# Targeted health snapshot request — October 19, 2026

## Milestone: reproducible bounded acquisition plan — COMPLETE

The existing RIFT process (PID 8356, creation ticks
639279978665141458, game build SHA-256
7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD)
remained live and unchanged during preparation. The prior native health scan
from the same process and build had SHA-256
07DB7E70D98EA102FE0939A9CD89C1153FA8A0D0318B5E431B90D3BC3766415F.
The exact two-epoch marker comparison had SHA-256
6C3CD09B59F34F92A78B42D85DEF677A31B5C3A595C443E0EAA37E413C9E81BD.

The new host-only scripts/plan-targeted-health-snapshot.py validates the
saved report, marker shape/multiplicity, and a fresh receiver receipt bound
to the exact PID/start/build and player. It generates an existing native
snapshot request contract rather than another scanning implementation.
This is a planning and provenance milestone, **not** a live health
snapshot or field qualification.

Retained ignored files:

- Request: artifacts/field-discovery/targeted-health-20261019-01.request.json
  SHA-256 B3768055D382B4A9BCE39C7024E7A29305120AF1ADEDEA9F8940DE74986FFA62
  (908 bytes).
- Manifest: artifacts/field-discovery/targeted-health-20261019-01.manifest.json
  SHA-256 68CB587A344C42BB2869B1D5471BF53ADDE96EB48BFF373698AC02FFB6AAE8C3
  (6,738 bytes).
- Pinned receiver receipt:
  artifacts/field-discovery/targeted-health-20261019-01.receipt.json
  SHA-256 4BA0B234FDAF5F89FF251ADB2B398E0979B599925B7A9A7E348FB84FD1FF1A8C
  (10,393 bytes).

The request selects five explicitly known candidate groups, with 80 bytes
per group and only **400 bytes total** (five memory ranges). These groups
are independently retained *within this same process epoch* and reflect the
single repeated layout (three health/max-value int32 sites, raw power 100,
and a visual level hint 45). The manifest includes source-window hashes,
exact expected marker byte offsets, current Lua 18,208 health/max and raw
power 100, and a newer typed API sequence. These repeated values are
potential caches or copies, not identified native health pointers.
The request cannot survive a new process epoch without rediscovery.

The generator's focused synthetic suite passed **21 tests**, including
wrong PID/start/build/player, stale/future receipts, missing source hashes
and contexts, timestamp formats, invalid limits, deterministic output,
atomic no-overwrite publication, and no partial outputs on pre-existing
destinations. See the [usage guide](../reference/targeted-health-snapshot.md).

The final PowerShell 7 repository gate passed with exit 0 on October 19:
**242 C# tests** (225 core and 17 Windows), **114 Python tests**,
108 Lua assertions, 22 actual Lua-to-C# shared cases, a zero-warning .NET 10
Release build, locked restore, synthetic native publish smoke, deterministic
replay, formatting checks, and **224 relative links**. Workbridge job:
rr2_targeted_snapshot_full_validation_20261019_43. The ignored validation
run is artifacts/validation/20261019T165539Z-35545237.

## Attempted same-epoch guest execution: NOT QUALIFIED

The currently installed .NET 10 Windows reader was published under ignored
artifacts/field-discovery/targeted-snapshot/media/. A disposable ISO was
generated with that reader, the exact request, a private receiver delivery
configuration, and an experimental lab-only PowerShell runner; every ISO
entry was verified byte-for-byte. Local build evidence:
artifacts/field-discovery/targeted-snapshot/media-receipt.json.
PowerShell 5 syntax parsing of the guest runner passed, but the runner
was **not** executed and remains ignored/unqualified.

With the exclusive VM controller lock, VMware's configuration accepted the
temporary ISO as the optical drive backing; however, the running guest
continued to show the previous RR2_FIELDS media after Explorer refresh.
A reversible start-connected flag cycle also failed to refresh the live
guest optical drive. This prevents claiming any new native-memory
acquisition or health data from the 400-byte request.

The original optical backing was restored and verified in the VMX:

    sata0:1.fileName = "C:\work\riftreader2\artifacts\field-discovery\rr2-fields.iso"
    sata0:1.startConnected = "TRUE"

The temporary ISO and guest runner are retained only under ignored local
artifacts for future investigation; no guest VM restart was performed.
The post-restoration receiver confirmed RIFT still in foreground under
PID 8356 with fresh typed Lua observations. No game memory was written,
no RIFT or V1 source was changed, and no movement/combat action was issued.

## Next live field-evidence milestone

Acquire the five candidate regions using the already implemented
RiftReader2.Live snapshot-native in the **same process epoch**, via a
verified guest transport/deployment path that does not require a live
VM restart. If the game has restarted, discard the absolute addresses
and generate a new plan from verified fresh-epoch evidence. Record exact
snapshot coverage/read failures, actual source hashes and fresh typed
Lua before/after samples. To identify authoritative current health and
resource fields, compare genuinely changed typed values and multiple
candidate copies; static matching alone cannot qualify a field.

The parallel movement-control roadmap and its uncommitted docs/README
and docs/status edits were kept separate and are not part of this
milestone or its commit.
