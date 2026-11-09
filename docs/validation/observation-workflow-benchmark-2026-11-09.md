# Observation workflow benchmark — 2026-11-09

AMD-DESKTOP, 06:12–06:14 EST. This tests the preserved legacy entry point against
the new explicit-target route in the same working tree, not a checkout of older
backend code. Both use the same managed controller / guest-agent capture backend.

## Measured result

Host-process wall time includes Python startup, guarded work and verified JSON
delivery; it excludes MCP/network/model latency and image display. No preview
was generated inside these timed runs.

| Route | Measured runs | Median | Min–max | Median guarded workflow |
| --- | ---: | ---: | ---: | ---: |
| Legacy screenshot-only | 3 | 4.803 s | 4.342–4.893 s | 4.587 s |
| New screenshot-only | 3 | 4.639 s | 4.588–4.780 s | 4.414 s |
| Legacy native data + screenshot | 3 | 6.598 s | 5.834–6.655 s | 6.378 s |

Each route had one excluded warmup. Measured order rotated across three rounds;
all 12 observations verified cleanup and unchanged exact VM/game/controller pins.
No failed trial was discarded and there was no retry or cross-target fallback.

The equal-work median difference is 0.163 s (3.4%), with overlapping ranges and
one paired run slower on the new route: **no established backend speedup**.
Old native+UI versus new screenshot-only saves 1.958 s (29.7%) by omitting native
diagnostics, not by making the same work faster. The native acquisition stage
itself had a 2.000 s median. This small sample establishes observed behavior,
not long-running reliability or statistical significance.

| Round | Legacy capture | New capture | Legacy native+UI |
| --- | ---: | ---: | ---: |
| 1 | 4.893 s | 4.780 s | 5.834 s |
| 2 | 4.803 s | 4.639 s | 6.598 s |
| 3 | 4.342 s | 4.588 s | 6.655 s |

## Pixel delivery check

The last new-route original was 1211×702 / 3,400,542 bytes. A separately timed
non-authoritative JPEG preview was 588×341 / 30,080 bytes (40,108 base64 bytes),
generated in 0.092 s. Binary image payload was 99.1% smaller; this is a reduced
resolution/lossy review image, **not** an equal-quality compression or measured
network-latency gain. The original and SHA remain unchanged. The returned pixels
were reviewed as a visible RIFT scene with addon panels, not a blank frame.

## Reproduce / evidence

Use the verified repository Python environment and a new direct child of
`artifacts/e2e-latency-20261106` for every output:

- Legacy capture: `scripts/inspect_lab2_tool.py --capture-only --output <fresh>`
- New capture: `scripts/observe_target.py --target lab2 --expected-host AMD-DESKTOP --output <fresh>`
- Legacy native+UI: `scripts/inspect_lab2_tool.py --output <fresh>`

No gameplay input, VM/game restart, controller refresh or credential changes
were performed during this comparison. Existing authenticated channels were reused.

Raw measurements, per-stage timings and source SHA pins:
`artifacts/e2e-latency-20261106/benchmark-6ca0d9cd9501477ebfc61f95d3aa5df7.json`.
Each capture directory uses `bench-6ca0d9cd9501477ebfc61f95d3aa5df7-<ordinal>-<route>`.
RIFT PID 10876, exact start ticks `639297512883473394`, build
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`;
managed generation `04f54152d0c04ef4924c4e9e02d55b38`.
Last capture ID `44a91ae11bc44a5fb50d2e7e7489c9d3`, UTC `2026-11-09T11:13:52.1663685+00:00`,
original SHA `4445D5E02FB37E57A0E05ADCA055DAEC99AC0AD42ED27BCC553E2698F9D18DBF`.

The benchmark pinned workflow source
`33b5ef070a31c42773f7ab35c34ed8581563340776d1f9ee8743bf49a9a8a104`.
A subsequent exception-only change exposes allowlisted typed controller blockers;
it does not change the successful capture path. All other benchmark source hashes
are retained in the raw measurements.

## Remaining target limits

Lab 1 code is implemented and offline-tested; live dependency admission stopped,
and the strict resolver reported `managed-runtime-changed`. Its guest was
disconnected, with a blocked/unheld queue and no cleanup receipt. Recovery must
preserve that ownership boundary. Physical AMD RIFT was not running; no positive
physical screenshot or physical benchmark is claimed. Native VMware-console
capture was not tested by these guest-agent observations.
