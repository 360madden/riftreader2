# RR2 physical orientation candidate burst — handoff (2026-11-10 ET)

## Completed result

Read-only five-sample orientation capture works on **AMD-DESKTOP** against the exact physical RIFT x64 process, with no gameplay input, UI automation, process writes, or VMware guest access. Both raw matrices and compact per-sample candidate angles are retained under the same lease/session/process and player-component identity.

Run from `C:\work\riftreader2`:

```powershell
python scripts/physical_rift.py --expected-host AMD-DESKTOP --physical-pid 44888 --read-native orientation --samples 5 --interval-ms 100
```

- Native command: `sample-current-orientation --samples 1..30 --interval-ms 0..2000`. One sample retains the original single-report contract; multiple samples produce `native-current-orientation-candidate-burst/1` with `observations` and final `observation`.
- `scripts/physical_rift.py` confirms exact process/build, requested/completed sample counts, unchanged player unit and component, and all matrix float32 raw bits before projecting `orientationSeriesDegreesCandidate`, wrap-aware `orientationSignedTravelDegreesCandidate`, matrix delta series, and refresh field series.
- Changed player/component/epoch, invalid matrices, or incomplete bursts never promote a result. Native runner writes a new report only after all samples pass revalidation.
- The projection always retains `headingQualified: false`. Matrices **must not** be treated as proven body yaw or camera facing.

## Physical evidence — 2026-11-10 21:31 EST

- Host: **AMD-DESKTOP** (selected independently before launch).
- RIFT PID: **44888**; process start UTC ticks: **639299470183328173**.
- Executable SHA-256: `1935a05c9db6d468e34e0055014a4a99c1b5afceb1695884e24600f5c20a4be8`.
- Unit key: `239816685251645959`; same component address across all five captures: `1779061326720`.
- Requested/completed: **5/5**, over **648.5738 ms**.
- Primary planar candidate, offset `+0x60`: **111.88167763120833°** for all five reads.
- Secondary planar candidate, offset `+0x94`: **111.88233336294573°** for all five reads.
- Candidate signed travel: **0.0°** for both series; maximal corresponding-matrix element difference **0.0000106**.
- Refresh handle `0x0000000000000000` and flag `0` in all five samples.
- Raw unique artifact: `C:\work\riftreader2\artifacts\physical-native-orientation-ae0dcc6e91484f5c9241f6e89301c864.json`
- Raw artifact SHA-256: `2b6940a75015524dcb1a5718ba20d35eadf66090f24c9165f17d4da99229e8bd`.

## Verification

- `dotnet test tests/RiftReader2.Live.Tests/RiftReader2.Live.Tests.csproj --no-restore --verbosity quiet`: **1123 passed, 0 failed**.
- `python -m unittest discover -s tests -p test_physical_only_selection.py -v`: **43 passed**.
- `dotnet build src/RiftReader2.Live/RiftReader2.Live.csproj --no-restore --verbosity quiet`: **success, 0 warnings / 0 errors**.
- Added offline tests for same-owner burst, owner/component invalidation, bounds and invalid-row rejection; actual live sample was passive/read-only.

## Next constrained task

**Do not infer body/camera heading from the stationary matrices.** With independently approved, coordinated movement/turn testing on a single physical client, compare before/after angle changes against the known input action and camera state to determine axis, sign, source freshness, and actor-vs-camera ownership. The movement controller owner should coordinate that test; no extra movement was performed in this workstream.

For offline follow-up, regression-test 360° wrap crossings and repeated capture/restart epoch invalidation without affecting the active navigation or statistics lanes. Other developers' dirty files, including fresh actor pose and stat-reader work, were deliberately left untouched.

Prior orientation single-sample commit: `d28853e821f49951319f8ad066291111fad689f1`. This handoff accompanies the burst implementation commit.
