# Manual external guidance

This prepared slice adds ordinary addon information exchange. Live delivery and
current-client UI behavior must pass the
[two-lab acceptance](../planning/bidirectional-feasibility-2026-10-28.md) before
being called verified. It implements no gameplay actions.

## Bind and calculate

Install the core `addon/RiftReader2` package, including `guidance.lua`. The
producer's RR2A1 schema and version and RR2L1 framing are unchanged. Source
hashes distinguish this package revision; the package TOC remains 0.1.0.
Generate a new 32-character lowercase hexadecimal nonce for each lab/load.
In the named lab, manually enter:

```text
/rr2guide bind lab2 REPLACE_WITH_FRESH_32_HEX_NONCE
```

This also performs the existing live-reader binding. A conflicting existing
`/rr2bind` cannot be replaced; reload then bind a new reader. A repeated identical
bind does not reset replay protection. No binding or result is persisted.

Use the existing read-only reader's current `latest.json`. The external CLI
consumes that normal reader output and generates a result:

```powershell
dotnet run --project src/RiftReader2.Cli --configuration Release -- guide-addon --snapshot artifacts/current-latest.json --lab lab2 --session-id REPLACE_WITH_FRESH_32_HEX_NONCE --result-sequence 1 --destination-x 7163 --destination-y 821 --destination-z 3160
```

The illustrative destination is not a live command or chosen safe destination.
Use a reviewed point in the current player's coordinate system. Optional
`--output PATH` writes a no-overwrite JSON report. Exactly one of `--snapshot`
and `--frame` is required. `--frame` accepts a saved raw RR2L1 envelope as an
explicitly offline test/replay source, with unverified freshness.

The snapshot gate requires a running reader, matching nonce/target session,
valid process/build identity, bound fresh selected observation, completed scan,
aligned candidate counters, ordered collection timestamps and remaining
freshness. Capture age is at most two seconds; effective last-advance age adds
elapsed capture age and a 250 ms assumed UTC-skew budget. Source/host clock
synchronization is an operating assumption, not something this file reader can
prove. A slow guest-file transfer fails closed; use the proven delivery path or
calculate beside the reader rather than relaxing freshness checks.

The report computes the snapshot-file SHA-256 and retains reader/target identity
and timestamps. Envelope/addon-frame hashes are reader-reported in snapshot
mode; without original wire bytes they are not independently reconstructed.
Producing a command does not prove live addon receipt or completed transport.

Manually deliver the report's `slashCommand` in that same lab. Display and
`/rr2guide status` report accepted external planar distance and signed deltas.
`/rr2guide clear` cancels the displayed result without clearing replay counters.
After movement, acquire a newer source frame and increment the result sequence.
The receiver cannot continuously refresh distance without new delivered results.

## Version 1 bounded result

```text
/rr2guide result LAB NONCE RESULT_SEQ EPOCH SOURCE_SEQ SOURCE_CLOCK PLAYER SOURCE_X SOURCE_Y SOURCE_Z PLANAR_DISTANCE DELTA_X DELTA_Z DELTA_Y
```

Only `lab1` and `lab2` are allowed. The Lua argument string and generated full
command are bounded at 512 printable ASCII characters. The receiver requires
exact token count, the immutable bound lab/nonce, positive counters no greater
than 9007199254740991, finite bounded values and an ASCII player identifier.
Source/destination coordinates are bounded to +/-10000000, deltas to
+/-20000000 and planar distance to 30000000. The receiver also checks the
distance agrees with the vector within max(0.01, distance * 1e-9).

The current addon API observation must have available coordinates and a clock
within 1.5 seconds of `Inspect.Time.Frame()`, matching player and epoch, and a
sequence at least as new as the result source. Source age must be from 0 through
10 seconds. Future source times and results older than the window are rejected.
Accepted result and source sequences must strictly advance. These are replay
guards for a manual local experiment, not authentication against a malicious
addon with access to the same game runtime.

Display validity is checked every update. Missing/rolled-back clock, changed
identity/epoch, expired source, or displacement over 0.5 on any axis clears the
calculation and exposes an unavailable reason. Returning to the old position
does not restore the result. There is no arrival claim, route progression,
protected macro, arbitrary Lua, or external controller operation.

Planar distance is sqrt(deltaX^2 + deltaZ^2); vertical delta is deltaY. Bearing
in the external report is degrees from positive X toward positive Z, with no
bearing at zero planar distance. The addon displays coordinate deltas instead
of unvalidated left/right, facing, camera or cardinal instructions.

`RiftReader2_Guidance` exposes bounded current status/result in the Lua runtime
for later read-only receipt evidence. It is not a separate network or file
channel. The acceptance message and result retain source-to-receipt age on the
same game frame clock; it includes manual transfer delay. No cross-machine clock
synchronization is claimed.
