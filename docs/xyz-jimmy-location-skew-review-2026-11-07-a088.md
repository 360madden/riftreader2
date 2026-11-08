# Jimmy RR2 location-context skew reproduction — November 7, 2026 (a088)

**Scope:** read-only follow-up to `docs/xyz-jimmy-lease-review-2026-11-07-a087.md`. No source edits, status/handoff edits, commits, live game/VM/controller operations, or new captures.

## Confirmed validation gap

The current location-context host validator requires the zone interval to start after the XYZ interval completes, but it imposes no maximum positive separation. This is not just a theoretical missing assertion: a synthetic report with the zone interval **10 seconds after** the XYZ interval, while still inside the report's outer interval, is accepted by `validate_report(..., mode="location-context")` and returns `zoneStatus="null-provider"`.

Reproduction was executed offline using the existing test fixture from `tests/test_sample_current_native_location_pair.py`:

- Job: `rr2-jimmy-confirm-location-skew-gap-20261107-a088`
- Exit code: **0**
- Output: `null-provider`
- The synthetic position interval ended at 00:00:00.001Z; the synthetic zone interval began at 00:00:10.000Z and ended at 00:00:11.000Z. The outer report interval was extended to include it.
- This proves the validator accepts a 9.999-second positive gap. It does **not** claim that an actual live zone scan took that long.

## Why the skew can matter

Reviewed current code:

| File | SHA-256 |
| --- | --- |
| `src/RiftReader2.Live/CurrentBuildLocationContextCandidateReader.cs` | `79DDBFED66B5EE2CD0CCC92C4F315587C3ACF9B2DE4867A1BE05954559E94121` |
| `src/RiftReader2.Live/CurrentBuildZoneSeedSampleCommand.cs` | `DAEE793A6B94077C7443D89C36434B800E11FBB2CC68C7955B2D727276B0B4D9` |
| `src/RiftReader2.Live/CurrentBuildPlayerContextCandidateReader.cs` | `72F19547AD9300D8ADCE3F343F1082488702FF668F24DBE41393BA66B8E6E801` |
| `src/RiftReader2.Live/WindowsThreadTlsSnapshot.cs` | `C10CB098D837E7DBCFDD6ED7620766815970A415DEC51F2EC99820F23FAB877B` |
| `scripts/sample_current_native_location_pair.py` | `55C24973ECDCB8628D01DE25821795A348A8D5FB6FEF3C3E2B1B742C05D9C3C4` |
| `tests/test_sample_current_native_location_pair.py` | `4771C707CF6F4A2484F350FB8FFD8DBD7382AC317E251EB7F554724971E0A8E2` |

The zone candidate path is not a single trivial field read. `CurrentBuildZoneSeedSampleCommand.Read`:

1. Captures player context and the zone key.
2. Resolves the zone provider/registry and TLS index.
3. Enumerates up to **256** live threads; opens each thread and checks TEB/client/thread creation identity.
4. Reads each thread's TLS slot and requires a consistent collection.
5. Validates a collection with up to **4096** records and follows a hash chain for up to **128** nodes.
6. Re-reads the player context and the full thread epoch set before returning.

The read budget is capped at **2 MiB**, and the thread/cache loops are bounded, but there is no elapsed-time limit within this synchronous reader. The location-context reader's final `lookup.VerifyUnchanged` checks owner/anchor identity, not whether the earlier XYZ values stayed unchanged during the TLS/zone search. A same-player/process identity check therefore does not make the two fields simultaneous.

## Required correction before location consumers

- Add an explicit maximum `zone.startedAtUtc - position.completedAtUtc` cross-field skew, separate from the duration bound for either individual read. Select the threshold after profiling the bounded zone scan; do not invent a timing target from this synthetic reproduction.
- Add a formal test where a large positive gap (for example 10 seconds) is rejected.
- Alternatively, retain separate timestamps and explicitly prevent consumers from treating the two candidates as one waypoint/location identity. A final XYZ reread after zone discovery can improve bracketing, but should still be labeled non-atomic unless the engine provides a stronger snapshot guarantee.
- Keep `worldInstanceStatus=unavailable`; the zone key/ID candidate is not a world-instance identifier.

**Coordination:** Shared review evidence only. The main coordinator owns any source/test changes and any later live experiment.
