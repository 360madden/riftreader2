# Current-build HP/Energy candidates

`sample-current-vitals` performs one read-only exact-build acquisition, using the
shared fresh player lookup, owner/type/input rereads and process revalidation. It
never calls a native getter. Results are candidate-only; independent same-player
changed-state meaning, passive freshness and restart recovery remain unqualified.
Kind-3 Mana is explicitly unavailable; Energy is not a generic resource reader.

On the activated Lab 2 controller, use the joined persistent diagnostic to avoid
guest process launch and executable/report transfers:

```powershell
python scripts/inspect_lab2_workflow.py run --native-vitals --output C:\work\riftreader2\artifacts\e2e-latency-20261106\<new-run>
```

It performs fresh expected VM/game/build/agent checks, acquires the same bounded
candidate report through the authenticated channel, captures the matching game
window under its own lease and verifies cleanup. See
[end-to-end measurements and limits](../validation/lab2-end-to-end-latency-2026-11-06.md).
This route was activated and tested on Lab 2 only.

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
