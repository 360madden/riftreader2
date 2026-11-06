# Current-build HP/Energy candidates

`sample-current-vitals` performs one read-only exact-build acquisition, using the
shared fresh player lookup, owner/type/input rereads and process revalidation. It
never calls a native getter. Results are candidate-only; independent same-player
changed-state meaning, passive freshness and restart recovery remain unqualified.
Kind-3 Mana is explicitly unavailable; Energy is not a generic resource reader.

Use an explicitly hash-pinned published reader from the host:

```powershell
C:\Python314\python.exe -B scripts\sample_current_native_vitals.py --lab lab2 --reader C:\absolute\path\RiftReader2.Live.exe --reader-sha256 SHA256
```

The host wrapper checks the executable hash before lab access, obtains the
VM-specific cached credentials, reacquires game PID/start/SHA, stages unique
scripts and executable, and validates transferred report bytes and source identity.
Outputs are unique under `artifacts/native-current-vitals/runs/<lab>/<id>/`. A
launch timeout leaves guest reader cleanup unverified. Source validation, lookup
bracketing and sequential memory reads cannot rule out ABA or stale game caches.

The guest executable can also be used directly with
`sample-current-vitals --pid N --start-ticks N --output NEW.json`; no existing
report is overwritten. Health and Energy statuses must be checked independently.
See [validation](../validation/native-vitals-2026-11-06.md) for observed results.
