# Automatic Telemetry publisher scope discovery — build 1179

**November 20, 2026 ~06:41 EST · AMD-DESKTOP · RiftReader2**

## Change

`scripts/capture_physical_telemetry_zone.py` now supports **`--auto-scope`** with bounded **`--scope-count`** (1–8). Its existing manual `--start-address` behavior is unchanged unless the new flag is supplied.

The optional discovery algorithm:

1. Verifies the exact **AMD-DESKTOP** RIFT PID, process start and supported executable SHA as before.
2. Reads a source-hashed native player/zone **preflight** before the timed capture bracket, then checks process identity again.
3. Surveys 1–8 adjacent caller-bounded private-memory windows using read-only `ReadProcessMemory` access. Only a complete Telemetry `RIFTTLM1` frame with the exact player ID, expected canonical zone ID, valid schema, consistent source session/epoch and at least two advancing source-clock/sequence candidates can rank a scope.
4. Selects the strongest eligible publisher **candidate**: highest source epoch, then source-frame clock and sequence, within this verified physical process. This is a scouting heuristic, **not** proof of the current producer's authority or wall-clock freshness.
5. Retains `native-survey-owner.json` and `scope-survey.json`, checks the same PID/start/build and player after the survey, and only then begins the original **new native-zone-before → Lua pass1 → Lua pass2 → native-zone-after** capture.
6. Requires the existing independent file-based replay gate before reporting `matching-candidates`. A missing, stale or mismatched publisher fails closed. Survey data alone never establishes API/native agreement.

The survey runs **before** the timed native–Lua–native bracket. Its own 15-second monotonic budget prevents an uncontrolled memory search. `--scan-bytes` is still restricted to one 64-KiB-aligned region up to 128 MiB; `--scope-count` does not bypass the original per-scan memory bound. No existing source contracts were broadened to admit stale publisher frames.

## Physical acceptance — November 20, 06:39 EST

After a fresh process selection, the command ran on physical RIFT **PID 22532**, process start ticks **639307475284776509**, exact game SHA-256 **DF954B798331E18359BE62A31CC74B49FC3F50B87385EBB080A5448256322C01**:

```powershell
cd C:\work\riftreader2
C:\Python314\python.exe -B scripts\physical_rift.py --expected-host AMD-DESKTOP
C:\Python314\python.exe -B scripts\capture_physical_telemetry_zone.py --physical-pid 22532 --auto-scope --scope-count 6 --start-address 0x13000000 --scan-bytes 67108864 --gap-ms 600 --output-dir C:\work\riftreader2\artifacts\physical-telemetry-zone-autoscope-20261120-0640
C:\Python314\python.exe -B scripts\replay_physical_telemetry_zone.py --summary C:\work\riftreader2\artifacts\physical-telemetry-zone-autoscope-20261120-0640\summary.json --output C:\work\riftreader2\artifacts\physical-telemetry-zone-autoscope-20261120-0640\independent-replay.json
```

**Results:** physical collector exit **0**, independent replay exit **0**, `matching-candidates`.

- Scanned **six 64-MiB windows** (384 MiB total), successfully reading all survey bytes. The candidate scanner selected **`0x1B000000`** automatically after comparing observed source-generation clock/sequence candidates across regions.
- Newly acquired native endpoints and **19 + 22** complete Telemetry Lua frame occurrences agreed on **`z0000000CB7B53FD7`**, independent Lua zone name **Silverwood**.
- Independent source replay recovered **22 unique source sequences**, **3 new advancing second-pass frames** (first sequence **70580**, last **70629**), Telemetry epoch **40**, Atank ID **`u035400012FA2D207`**, and a **2.0156-second** native→Lua→native host capture span.
- Maximum Lua frame-clock age of its own sampled zone detail: **4.580078125 source seconds**, not a host-UTC timestamp.
- `scope-survey.json` SHA-256: **B0B4AF838054820397601CC8D44750B44C11B344A89BA5CFEEC2245BA66090AE**.
- Source-hashed capture `summary.json` SHA-256: **CEDC593AED367B4FB642B860E6095AECF5E4A28B38E266362E1E987A24FABF6A**.
- Fresh cold `independent-replay.json` SHA-256: **48F54C729F3CDAE845CF2BCCF7BABB3DB1951ACC98B96D30BC37CBA73F88ED95**.
- Native before source SHA **8F00DD75E4090AD0270A48030509D3255E2E5CD182CC5E6074FD1E570AB1B8AE**; native after **DCF64764D1A71AE0A043C253624164CC654EFFB9A71991B543BDF697100A743E**.

All raw files are retained locally under ignored `artifacts/physical-telemetry-zone-autoscope-20261120-0640/`; they are not committed to Git. The newly selected memory address is not persistent across allocations, UI reloads or process restarts.

## Regression coverage

The focused suite passed **64/64**, including scope selection where an older epoch has a much *larger* sequence number than the active epoch, wrong player, wrong zone, one-frame-only scope, regressed source clock, out-of-range scope count, unknown build, early process identity change and preservation of a failed survey receipt. The wider composite suite passed **167/167** Python tests, including prior RR2A1 and native-zone readers and replay, and the independent cold replay passed against the actual saved physical files. Whitespace check passed.

## Qualification boundary

`--auto-scope` removes the need to manually locate a volatile current Telemetry memory window in tested conditions. It does **not** turn candidate zone equality into world-instance identity or route clearance, prove continuously fresh Lua source data, synchronize Lua and host clocks, prevent transient zone changes between non-atomic acquisitions or authorize gameplay input.

**Next:** demonstrate changed-zone API/native agreement under a *user-observed* transition, and controlled selected-target A→B→A sampling, with the same fail-closed source and process/epoch gates. No RIFT client focus, gameplay input, memory writes, restart, UI reload or changes to the sibling Telemetry repo were performed in this acceptance.
