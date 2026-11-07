# Current-build vitals candidates

`sample-current-vitals` performs one read-only exact-build acquisition, using the
shared fresh player lookup, owner/type/input rereads and process revalidation. It
never calls a native getter. Results are candidate-only; independent same-player
changed-state meaning, passive freshness and restart recovery remain unqualified.
The `/2` report contains independent Health, Mana and Energy candidate results.
Mana requires resource kind 3 and its type fingerprint (`0x072A`); Energy requires
kind 4 and its type fingerprint (`0x072B`). Energy is not a generic resource
reader. Check each field's `status` and `unavailableReason` before using its
values; a complete report does not mean every field is available.

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
The persistent path requires the agent's `freshIdentityVersion` and
`nativeVitalsVersion` capabilities to equal 1 and a
`native-current-vitals-candidate-sample/2` report. Explicit historical `/1`
report replay remains supported by the existing report validator; it does not
make a `/1` response eligible for the persistent path.

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

The published executable can also run directly on the host or in a guest, without
the VM wrapper:

```powershell
& 'C:\absolute\path\RiftReader2.Live.exe' sample-current-vitals --pid <PID> --start-ticks <DOTNET_UTC_TICKS> --output 'C:\absolute\path\NEW.json'
```

Use the current process ID and its .NET UTC `StartTime.ToUniversalTime().Ticks`
(not Win32 FILETIME ticks). The command requires executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`,
revalidates process identity, and performs one bounded, read-only acquisition;
it never overwrites an existing report. The lookup limits the entity chain to
eight nodes and individual memory reads to 4,096 bytes. Obtain and verify the
current target and published reader before use; this direct route alone does not
establish physical-host acceptance.
See [validation](../validation/native-vitals-2026-11-06.md) for observed results.
