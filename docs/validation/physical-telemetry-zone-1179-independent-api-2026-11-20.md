# Physical RIFT 1179 — independent Telemetry Lua zone and native zone match

**November 20, 2026, 05:50–06:11 EST · AMD-DESKTOP · read-only**

## What was recovered

An existing, separately implemented local `Telemetry` addon already publishes `RIFTTLM1|<JSON>|ENDRIFTTLM1` source frames. Its Lua `playerTelemetry.zone.id` is obtained from RIFT API data; its `zone.name` uses `Inspect.Zone.Detail`. These frames are created inside the game and are independent of RR2's native memory zone-cache decoder. The Telemetry .NET companion remained limited to the older build-1177 SHA, but **the active Lua publisher itself was found in the updated 1179 game process**. No Telemetry source code or addon files were modified.

RR2 now has a standalone CLI implementation:
- `scripts/capture_physical_telemetry_zone.py` — on the verified AMD-DESKTOP host, use an explicit physical RIFT PID, guarded 1179 SHA and process start, **read-only** process access, bounded 64-KiB scans and at most 32-KiB frame copies; retain Lua wire bytes and SHA-256 digests between native `zone-context` before/after reads. The process identity is rechecked between stages. Wrong build/host/stale PID/invalid scan range and unavailable or mixed publisher data refuse positive publication.
- `scripts/replay_physical_telemetry_zone.py` — a separate **offline-only** implementation reopens the original source bytes and native JSON reports, checks SHA-256, process/start/executable/module identity, player IDs, frame envelope/schema/session/epoch/source clock, zone ID and zone-name states, duplicate and conflicting retained frames, zone-sampled source age (≤10 source seconds), and strict native→pass1→pass2→native UTC ordering. It requires at least one new source sequence in pass2 and a bounded total host acquisition window; it never opens RIFT.
- Dedicated deterministic fake-memory and negative-case tests refuse tampered source bytes, invalid API fields, mixed generations, old or reversed source clocks, wrong player/build/process, missing advancement, replay overwrites and invalid scope requests. No source files under `artifacts` are committed.

These tools preserve the fail-closed candidate qualification. The Telemetry source session ID is its own publisher-generation marker, **not authentication**; Lua source clocks are not synchronized to host UTC and the observations are sequential, not atomic.

## First positive physical pairing — 05:50 EST

Physical process PID **22532**, start ticks **639307475284776509**, installed executable SHA-256 **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**, player ID `u035400012FA2D207` (Atank). An independent bounded read-only scan found complete Telemetry frames in the process. Two saved frame passes were bracketed by positive native `zone-context` reads.

**Both native endpoints and all 19 decoded Lua frame occurrences agree on zone ID `z0000000CB7B53FD7`; Telemetry zone name is `Silverwood`.** The saved frames comprise 10 unique source sequences, including a newly advancing sequence in the second pass; Telemetry source epoch **40** and session ID remained consistent. Host native→Lua→native window **0.9306 seconds**. Maximum elapsed Lua frame clock since its own zone-field sample **4.673828125 source seconds**. These are source-clock measurements, not wall-clock synchronization.

Ignored original evidence: `artifacts/physical-telemetry-zone-20261120-0549/summary.json`, SHA-256 **ACD0E3BF116372C543E8BB4DFBF5B9DC27BB5E265BAFE25832D2C3D61EEECD28**. The independent cold replay exited **0** with `matching-candidates`: `artifacts/physical-telemetry-zone-20261120-0549/independent-replay.json`, SHA-256 **437CD6E56922DFC9AC76194633FAC3194EAFB3B4EBA14901EDB65C40650DC987**. Native before source SHA **D4B9F283063B447170411645F32EBCEB690E5C6CF1F48C5D1BCF7058A4DAA210**; after **93382995A8DBF4F59EE48178E30BFC5EF43142FDFB8AB500F1E20FDC577D154C**.

## Reusable CLI positive physical run — 06:09 EST

The first helper CLI attempt on memory range `0x13000000` returned `unqualified` with zero Lua frames, despite successful native endpoints. This was expected refusal, not proof the publisher was absent. A bounded memory inventory then found that the current Telemetry generation **epoch 40** had moved to a different memory scope, while a separate scope had **retained older epoch-39 frames** with source clock ~16705–16717. Another helper attempt on that stale scope captured 44+44 frames but was correctly refused due **no newly advancing source sequence**. No mixed old/current generation was silently admitted.

Using the freshly observed current-epoch scope `0x17000000` (64 MiB per pass), the standalone helper succeeded **exit 0**:

```powershell
cd C:\work\riftreader2
# Reacquire actual AMD-DESKTOP physical PID, start ticks and build first.
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\capture_physical_telemetry_zone.py --physical-pid 22532 --start-address 0x17000000 --scan-bytes 67108864 --gap-ms 600 --output-dir C:\work\riftreader2\artifacts\physical-telemetry-zone-helper-20261120-0616
C:\Python314\python.exe -B scripts\replay_physical_telemetry_zone.py --summary C:\work\riftreader2\artifacts\physical-telemetry-zone-helper-20261120-0616\summary.json --output C:\work\riftreader2\artifacts\physical-telemetry-zone-helper-20261120-0616\independent-replay.json
```

The helper found **50 + 50 complete Lua frames**, replay resolved **52 unique source sequences** (first **52849**, last **52964**) and **two newly advancing sequences** in pass 2. Exact native/Lua zone ID `z0000000CB7B53FD7`, name `Silverwood`, consistent publisher session and epoch, all source wires individually SHA-verified. Host observation window **2.2089 seconds**. Maximum zone-field source age **4.810546875 seconds**. Its internal replay gate passed before CLI exit 0, and a separate subsequent CLI replay also exited 0.

Ignored original evidence: `artifacts/physical-telemetry-zone-helper-20261120-0616/summary.json`, SHA-256 **749A3EC6880DB63B7C3A15E18C0C4E9510180F0EC53087B78E038E443C53A3B8**. Independent output `artifacts/physical-telemetry-zone-helper-20261120-0616/independent-replay.json`, SHA-256 **C18CD3A607AFF09AD126880646AC0160D9F6EC241EA9DBD12AF8D59E31939CC6**. Native source SHA hashes: before **1CC572A95233A2602FA3E4401D30B9F8B986A2EEC2E96498B43A9F1AE85FBDF1**, after **85837D0C48A54213DDBF6B655651FE9069C9A0230492A31A0C8017EC32C0DE83**.

## Validation

The integrated focused Python suites passed **169/169 tests** on AMD-DESKTOP, including synthetic read-only process-memory reader tests, original source-hash validation, old/new build gates, native XYZ and RR2A1 replay, and **35 Telemetry zone capture/replay tests**. A separate direct CLI smoke test passed, both physical-zone captures and standalone offline replays exited 0, and `git diff --check` passed. The source hashes above are preserved for independent replay. The earlier empty/stale scopes correctly returned exit code 2 with `unqualified` diagnostic reports, not false successes.

## Qualification and next direction

**Qualified in bounded scope:** The current 1179 physical process contains an independently implemented Lua API publisher with an advancing, same-player, same-publisher-generation zone ID that matches RR2's guarded native ID in two tightly bracketed source-hashed captures. This removes the prior *unavailable independent Lua API zone reference* blocker for this current observed state.

**Still not qualified:** cryptographic publisher authentication; atomic native/Lua read, host vs Lua clock synchronization, world-instance uniqueness, portable current-heap addresses, causal zone transitions, sustained passive freshness, or waypoint/movement authority. The Lua frame `zone.sampledAt` may be several source seconds older than the enclosing published frame, and its age is shown rather than hidden. Source memory addresses are volatile; scans from old addresses can return old generations or zero frames. A current-epoch address-scout or auto-scope selection is an operational improvement, not a prerequisite to the now-verified current-zone correlation.

No game input, UI reload, client memory write or RIFT process restart was performed.
