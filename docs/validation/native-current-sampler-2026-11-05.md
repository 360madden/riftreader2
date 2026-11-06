# Current-build native XYZ sampler — offline and live acceptance, 2026-11-05 UTC

**Result:** Implemented a bounded, exact-build .NET 10 `sample-current-position` command and a standalone host-side on-demand tool that discovers the **current** guest game identity, reuses the SHA-checked guest sampler, and saves unique source reports. **Live read-only three-sample checks passed on both labs.** A 30-sample Lab2 host workflow passed within a 4.5-second measured sample-cadence bound. All native positions remain **cached candidates**; passive player-position freshness, same-unit Lua agreement and goal arrival remain unqualified.

No game keys, movement pulses, addon binds, VM/game restarts, debugger or process writes. Existing RRE/REA research remained read-only, per `AGENTS.md`.

## Implementation

- `src/RiftReader2.Live/CurrentBuildPositionSampleCommand.cs`: new `sample-current-position --pid PID --start-ticks TICKS --output NEW.json [--samples N] [--interval-ms N]`. Strict fixed game SHA `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`, one handle, exact process-start epoch, manager RVA `0x33624A8`, native player key/table, position index at RVA `0x2F588A0`, eight-node bounded collision chain, component float32 XYZ at `+0x48/+0x4C/+0x50`, and pre/post owner anchors with per-sample process revalidation. Finite, sequential, never-overwrite JSON report; 1–30 samples, 0–2000ms delay, bounded total requested delays. Does not use the obsolete SHA `7C356C9D...` pointer profile.
- `src/RiftReader2.Live/NativeCommandRunner.cs`: explicit entry point and help listing.
- `scripts/sample_current_native_xyz.py`: on-demand native host operation, reuses per-lab cached VM credential workflow, discovers fresh exact game PID/start/SHA, verifies the published reader SHA, uses a per-SHA guest helper copy or stages it once if absent, then validates/copies an original source report and writes distinct no-overwrite host evidence under `artifacts/native-current-sampler-20261105/runs/<lab>/<id>/`.
- `tests/RiftReader2.Live.Tests/CurrentBuildPositionSampleCommandTests.cs`: eight synthetic cases covering ordinary finite XYZ, wrong game build, missing key/range, corrupted component, changed owner/XYZ, cyclic hash links and signed low32 bucket selection.
- `tests/test_sample_current_native_xyz.py`: eight offline host-wrapper tests for options, result bounds and identity, time/sequence/finite XYZ, no false freshness promotion, guest binary reuse, staging and failed-report rejection.

The immutable published executable for these live trials is:

`artifacts/native-current-sampler-20261105/publish/RiftReader2.Live.exe`

SHA256 **`B8A725E6A9CE663C36CB836681ED660261B07FDA4118A0167262E92131B2373E`**, size **117,159,776 bytes**. A successful .NET Release `publish` and separate `--help` invocation confirmed the new command. The published binary is **not** substituted for currently installed control-agent or old telemetry reader binaries.

## Live evidence

All values are precise **cached native candidates**, not independently verified player motion.

| Trial | Original Workbridge job | Target game | Result | Sample cadence / latency |
| --- | --- | --- | --- | --- |
| Lab2 three-sample smoke | `rr2_current_native_sampler_lab2_live_smoke_20261105_01` | PID11572, start639293038821710082 | **3/3 PASS**, steady XYZ (7181.801,820.88214,3135.8762); original report SHA `1D446697E43910B25F4FD7A605503B7C82091F55D48A97B63A30FE7E75978F32` | 89.9–97.5ms per source read and exact identity check |
| Lab1 three-sample smoke | `rr2_current_native_sampler_lab1_live_smoke_20261105_01` | PID1952, start639294190379863806 | **3/3 PASS**, steady XYZ (7399.285,871.77924,3034.239); original report SHA `D356AB208CA8D94F36DBAE9CFCA6D166CE2AB796142CC424459A692867CA2288` | 81.7–94.2ms per source read and exact identity check |
| Lab2 on-demand host workflow | `rr2_native_host_sampler_lab2_30samples_20261105_01` | current PID11572/start639293038821710082, verified independently at runtime | **30/30 PASS**, no position changes; original report SHA `D048A703D957E61C7AFF69F03DDD60FFAB32619E0E509F291AE0266DAB32DD06` | max per-read 120.893ms; max start gap 532.250ms; all under 4.5s |
| Lab2 cached-helper repeat | `rr2_native_host_sampler_lab2_cached_repeat_20261105_01` | same pinned current game epoch | **30/30 PASS**, `guestReaderReused=true`; source SHA `84D9D06F2FDD4424715E6DA6F473AF85F62B38C69CA98DCB1A77198FECECD` | max per-read 135.910ms, max start gap 544.002ms; total operation 28.5s (versus 92.7s initial staging) |
| Lab1 on-demand host workflow | `rr2_native_host_sampler_lab1_30samples_20261105_01` | current PID1952/start639294190379863806, verified independently at runtime | **30/30 PASS**, no position changes; original report SHA `C0A667676B553A0CFCA769FDC8C1FD1B4E118B18F9F30FA2BA355F0C05C898BC` | max per-read 104.942ms, max start gap 538.701ms; all under 4.5s |

The 30-sample native report and summary reside under `artifacts/native-current-sampler-20261105/runs/lab2/454a483529cc4bb7aee6719febaa0875/`. The run first staged its SHA-pinned helper in the guest. The host operation verifies the byte report independently; `sourceReportSha256` is an original source integrity receipt, not a player-semantic certificate.

## Validation and next steps

- `dotnet build src/RiftReader2.Live/RiftReader2.Live.csproj --no-restore`: PASS, 0 warnings/0 errors.
- `dotnet test tests/RiftReader2.Live.Tests/RiftReader2.Live.Tests.csproj --no-restore`: **209 passed, 0 failed**.
- New host-wrapper offline `python -m unittest discover -s tests -p test_sample_current_native_xyz.py`: **8 passed**, including negative rejection tests.
- Previous current-build manager probe tests **46 passed**, and both independent original 50-second manager probes were successful; this fast sampling loop avoids transferring many separate raw read requests.
- `git diff --check` and Python compile checks passed.

**Next:** both labs passed independent 30-sample host operations, and the cached-executable Lab2 repeat passed. These short stationary runs cannot qualify dynamic player motion, passive cache freshness or sustained 480s source continuity. For native-primary XYZ to replace Lua-bound feedback, require an independent same-unit changed-state and source-clock comparison (before/after one reviewed bounded action) and a future 480s sustained evidence window. The historical full Lua scan failing freshness while the scoped fast source advanced is a distinct acquisition issue; do not report that the new sampler fixed it.
