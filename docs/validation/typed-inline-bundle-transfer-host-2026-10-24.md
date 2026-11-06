# SHA-pinned guest bundle selection and transport regression proof — October 24, 2026

**Outcome: real Windows-host preflights and loopback tests passed; no VM network listener was started and no RIFT guest binary was transferred.** This change prepares the independently host-validated `scout-copy-typed-native` executable for the existing restricted one-use host→guest stream.

## Reused transport, narrow extension

- Reused `scripts/serve_guest_native_scout.py`, preserving its existing **`--bundle scout` default**, VMnet8-only bind `192.168.56.1:8765`, exact sole allowed guest `192.168.56.128`, maximum **600-second** lifetime, 64 KiB streaming, full initial and sent-byte SHA checks, single successful GET, rejection of other methods/peers/paths, and Windows signed-in `pythonw.exe` requirement for a live listener.
- Added only the explicit `--bundle typed-inline` selection, not a free-form source-path or arbitrary file server. The approved source is the already-published ignored `artifacts/validation/rr2-scout-copy-publish-oct24-01/RiftReader2.Live.exe`, pinned at **74,254,755 bytes** and SHA-256 `484FC6A0980BCAC823154229B974B0BD18412A9053903A542BC0313EB5EF1716`. It has the distinct exact guest route `/rr2-typed-inline-oct24-01.exe` and download name `rr2-typed-inline-oct24-01.exe`.
- The original `scout` source remains **74,209,699 bytes**, SHA-256 `C34D1C9BC5EC134D50AE38FBE6A16D13B0DBAC9EC412D9C4F4714E3DDFD9876C`, route `/rr2-scout-oct24-01.exe`. Its no-argument descriptor continues to choose this original route; default behavior has not been silently switched.
- Each bundle's eventual transfer receipt is stored in its **own ignored publication directory**, and never implies that the guest verified or ran that binary. Guest must independently check exact size and SHA before any read-only CLI invocation.

## Actual host verification

- `C:\Python314\python.exe -m scripts.serve_guest_native_scout --bundle typed-inline` returned exit **0** and `state=verified-not-serving` after actually hashing the entire new 74,254,755-byte source. Descriptor supplied the expected peer/port/route/SHA and explicitly reported `guestFileVerified=false`, `guestScannerExecuted=false`.
- The legacy no-option `python -m scripts.serve_guest_native_scout` independently passed the old exact source hash and printed its original `scout` route, proving default compatibility.
- New loopback tests confirm the second route's complete >64KiB GET bytes, checksum header and safe filename, refusal of the legacy route/query, disallowing an unregistered server route, and a real file descriptor hash/PE `MZ` check for the new published bundle. Full focused transfer suite: **14/14 passed**.
- The full Python suite's initial run had **one nondeterministic Windows `ConnectionAbortedError: WinError 10053`** in an *older receiver test* that sent a POST body for a request rejected from headers (later isolated with the error appearing on a different header-rejection case). A minimal **test-only** correction in `tests/test_receive_guest_memory_report.py` now sends the same declared `Content-Length` **without needless POST body** for early-rejection status probes. It continues to assert the exact HTTP refusal codes, while success/digest/publication-race tests still upload actual bytes. Production guest receiver was not modified. Combined transport tests **26/26 pass**.
- **Full `python -m unittest discover -s tests -p test_*.py`: 549/549 tests passed** after that fix (Windows Python 3.14, 50.997 seconds). `git diff --check` passed. The previously committed V2 .NET **432/432**, Lua **108**, and shared Lua→C# **22** gates were not changed by this Python-only transport extension; those are earlier passed results, not freshly rerun here.

## Acceptance still pending

1. Freshly recheck exact VM/game/V14 ownership, queue and `foreground=false` caveat; only execute the existing normal V14 STOP/release once the next guest trial is actually ready.
2. Launch `pythonw.exe -m scripts.serve_guest_native_scout --bundle typed-inline --serve --seconds ...` **only during exclusive guest maintenance**, consume one exact GET from the guest and independently verify saved executable size/hash. Never overlap the existing exclusive VM controller.
3. Create a fresh exact-process `native-typed-inline-capture-request/1` after checking the game's current start/build; take two independently time-separated `scout-copy-typed-native` read-only measurements with *different*, nonexistent output directories.
4. Hash/archive all originals, use a restricted no-overwrite guest→host return path, offline verify each strict snapshot and compare typed-wire evidence. Restore V15 under its prepared pinned VM identity and confirm ready/disarmed state even if the live attempt fails.

**No new RIFT process read, Lua frame qualification, XYZ correlation, VM console input or supervisor handover occurred in this milestone.**
