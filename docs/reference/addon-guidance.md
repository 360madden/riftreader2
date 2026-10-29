# Manual external guidance

This slice adds ordinary addon information exchange. Separate live return
results and recalculation after bounded movement were verified on both labs in
the [October 29 trial](../validation/two-lab-guidance-hour-2026-10-29.md).
Movement-triggered invalidation remains unproved in the live client; see the
[acceptance boundaries](../planning/bidirectional-feasibility-2026-10-28.md).
The guidance channel implements no gameplay actions.

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

## Reviewed VM-console delivery helper

For installations under OneDrive, verify that each TOC-listed Lua file is
locally readable. On October 29, Lab-1's TOC and five other core files matched
the repository, but `guidance.lua` was an unreadable cloud placeholder. That
caused `main.lua:6` to index a nil `Guidance` module. Preserving the placeholder,
replacing it with the hash-verified file, and pinning that file locally restored
loading. Validate all six installed hashes, reload, then require a successful
`/rr2guide status` response; the package version alone does not prove readable
installed contents. Keep any previous unreadable file as recovery evidence.

`scripts/addon_command_console.py` is the bounded VNC delivery path for the two
labs. It is not a general console controller. Every operation uses a new output
directory, exact VM identity and pinned game identity, the shared controller mutex, a screenshot,
an immutable whole-plan hash, and an exact root-agent review receipt. Execution
rechecks review age and identity before input and records release certainty and
an after-screen. Direct Computer Use remains deferred.

Do not assume typing `/` opens RIFT chat through VNC; a live trial showed the
letters reaching gameplay shortcuts instead. Establish UI state through separate
freshly reviewed operations:

- `--ui-step close-ui` sends one `Esc` only when the screenshot shows a closable
  ordinary panel and closed text entry.
- `--ui-step hide-addon --hide-frame readiness|casting --hide-x X --hide-y Y`
  sends one left click only to the reviewed ordinary **Hide** button. The exact
  frame, pixel and captured screen dimensions are plan- and receipt-bound. It
  cannot express a general click or select protected Casting controls.
- `--ui-step open-chat` sends one `Enter` only when no panel is visible and text
  entry is closed.
- A command is typed only after a new screenshot visibly establishes an open,
  empty, focused chat entry. Closed, nonempty or unfocused chat fails closed.

If the character is AFK, the first reviewed `Enter` may only clear AFK. Treat
that as a completed one-key attempt, take a fresh capture, and separately review
a second `open-chat` operation. A short multi-frame no-input capture can confirm
the blinking white caret before approving a command; do not infer focus from an
empty gray strip alone.

Stacked panels require one separately prepared and reviewed close/hide attempt
per panel. An execution receipt proves only that the reviewed input and cleanup
were attempted against the pinned identity. Inspect the next fresh screenshot
before inferring that a panel closed, chat opened, or the addon accepted text.

### Deferred fresh result calculation

Screenshot review can exceed the addon's ten-second source lifetime. For
results, `--deferred-result-intent INTENT.json --fast-source-pin PIN.json`
reviews an immutable calculation intent instead of an already-aging slash
command. The strict intent binds lab, nonce, positive result sequence, reviewed
destination XYZ, seed player/epoch/origin, the exact `dotnet` executable, and
the six Release `net10.0` CLI/Application/Domain/Infrastructure/runtime/deps
file hashes. Those six files are frozen into the operation output; arbitrary
programs, arguments, directories and command strings are not accepted.

After review, execution obtains a new authenticated live receipt no older than
two seconds, requires the same receiver/reader/target/player/epoch stream and a
position within 0.5 on each axis of the reviewed seed, then runs the fixed
`guide-addon --snapshot` argument shape using the approved destination and
sequence. It strictly verifies the generated report, source and destination,
vector/distance, snapshot hash and exact slash command, and freezes the receipt,
snapshot, report and command evidence before typing. Immediately before input,
the stream must still be continuous, position must be within 0.5 of the actual
calculation source, and effective source age—including the 250 ms clock-skew
allowance—must remain below eight seconds. The Lua ten-second limit is not
relaxed.

After Enter and input release, fast result delivery waits at most four seconds
for a strictly newer pinned receiver observation. Its host receipt time must
follow completed input, and its guest capture time must be at least 250 ms
later to conservatively account for clock skew. Receiver ownership, reader and
target identity, continuity, origin and freshness checks still apply. Only a
transient stale-receipt rejection is retried within that deadline; input is
never retried. Exact accepted receipt bytes and their hash are retained, then
the VM identity is checked again. Normal bind/status operations retain the
GuestOps identity checks. A blocked post-check can follow already-delivered
input: inspect the execution flags and screenshot before deciding any next step.

Reader PID/start/hash in the fast source pin are a reviewed startup attestation,
not facts proved by the HTTP receipt. The live receipt independently proves its
receiver instance, authenticated source IP, reader instance/nonce and current
target mapping. A completed helper execution is still not addon acceptance;
retain the after-screen or subsequent `/rr2guide status` evidence separately.

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
