# RR2 RIFT 1179 post-update recovery — 2026-11-17

## Outcome (AMD-DESKTOP only)

The physical RIFT x64 game updated to `STABLE-1-1179-a-1256672`. RR2 native player owner, position and body-facing readers are working again; the Waypoints 1.4.0 GUI is started on AMD-DESKTOP and is bound to a freshly measured movement calibration. No route was executed and no combat/casting occurred.

- New `rift_x64.exe` SHA-256: `DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01`.
- Historical exact build SHA retained for replay: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
- Tested game process: PID `77980`, start ticks `639305214834918403`, HWND `0x24B181E`, player key decimal `239816685251645959` (Atank); **these process values expire when RIFT restarts**.
- Game module base during testing: `0x7FF687CE0000` (ASLR; never retain as static).
- Validated new player-system global RVA `0x3373BA0`; entity-manager global RVA `0x3373C68`; position-selector RVA `0x2F698A0`; actor-selector RVA `0x2F69490` (actor discovery only); health-selector RVA `0x2F68850` (discovery only).
- New position vptr RVA `0x26C35C0`, entity backlink/owner key verified; new facing was cross-checked against independent player-system yaw with sub-microdegree agreement. Camera optical projection remains unqualified on this build.

## Update Helper used

Central `C:\work\Update Helper` captured 274 files before patch, 272 after; diff was 7 modified, 2 removed. `C:\work\Update Helper\data\RIFT-Live-diff-20261117-0916EST-rr2.md` records the exact comparison. RR2's postpatch analyzer: `artifacts\patch-analyzer-20261117-0918-postpatch\REPORT.md` (375 of 376 selected files unchanged; EXE changed).

## Live movement and calibration

Tested on the identified physical game instance with exact PID/start/EXE SHA/HWND, bounded Windows key-down/up and successful release. Initial 100 ms W pulse on a seaside cliff produced no planar movement; a screenshot showed Atank at the cliff edge. Subsequent backward motion was used to move inland before measuring the four controls.

Authentic new-build receipts (ignored research artifacts, preserved locally):

- `artifacts\postpatch-basis-{w,s,q,e}-20261117.json`, with planar displacements W `1.769`, S `0.784`, Q `1.560`, E `1.563` world units for nominal 250 ms holds.
- `artifacts\postpatch-movement-basis-20261117.json`: cardinal geometry accepted. W/S opposite `179.9725°`, W/Q near perpendicular `89.8468°`, Q/E opposite `179.9052°`.
- `artifacts\postpatch-turn-{a,d}-20261117.json`: independent native facing read before/after 250 ms A/D turns; A `45.2169° -> 89.7111°` and D `89.7111° -> 45.8034°`. Corresponding rates: A `+0.172233°/ms`, D `-0.172740°/ms`; native XYZ stationary during turns.
- Current active `config\physical-movement-basis.amd-desktop.json` replaced only after validating original receipts. All candidate/eligibility flags remain conservative; reuse does not imply independently proven autonomous routing.

`C:\Python314\python.exe scripts\launch_physical_waypoints.py --physical-pid 77980 --check` returned `ready` with matching build, process epoch, player key and basis SHA `54CDB58DCE11234C62BC1ECB96EE55B1EB7BC2C3BD53B89F02BB1929E812C5ED`.

GUI visual acceptance: `Joey D's Waypoints v1.4.0` showed live coordinates X `7208.423`, Y `842.877`, Z `3118.577`, facing `45.80°`, and `Fresh` pose. Persistent launch after transient test: GUI PID `75688` with RIFT PID `77980`; one-time task used to start it was removed after verifying GUI stayed open. Any restarted game requires fresh process selection and basis identity validation. No route started.

## Validation

- `dotnet build src\RiftReader2.Live\RiftReader2.Live.csproj -c Debug --no-restore`: 0 warnings, 0 errors.
- `dotnet test RiftReader2.slnx -c Debug --no-restore --verbosity minimal`: 444 core + 1,420 live tests passed, 0 failures (2026-11-17).
- Targeted Python physical/Waypoints suite: 139 tests passed.
- Exact current-build native facing via `scripts\physical_rift.py --expected-host AMD-DESKTOP --physical-pid 77980 --read-native facing`: passed, independent screen `PlayerCoords` XYZ agreed.

## Remaining work / guarded limitations

1. **Target projection, optical camera, native target/health/mana/energy and actor pose sampler**: not requalified yet on new EXE; current bridge deliberately rejects unsupported new-build native reader kinds. Revalidate per field, do not silently accept old offsets.
2. **Old recorded routes** remain tied to a previous build/player and are intentionally blocked from replay. Record a new route or explicitly migrate route metadata only after its geometry, world-instance and safety checks pass; do not simply edit hashes.
3. **Autonomous navigation and combat** were not claimed proven by these tests. A bounded motion sample + GUI health does not demonstrate whole-zone path execution or safe collision handling. The Atank cliff location makes blindly replaying old routes unsafe.
4. After any further patch or client restart, require fresh EXE hash, machine, process epoch, window, player owner, movement/turn calibration and route validation. `Update Helper` is the central before/after file evidence store; this RR2 repository owns RR2-specific fixes.

## Code scope

Updated exact-build allowlist/owner and selectors in `CurrentBuildPlayerLookup`, position/orientation/facing readers and commands; `NativeCommandRunner`; physical Python routing; and `MoveKeyCommand` exact-build XYZ feedback. Historical old-build constants preserved. No unrelated dirty developer files touched.
