# Fast candidate-region reader — built and validated, not deployed (2026-10-30)

**Verdict:** Source build and offline validation PASS. New standalone Windows x64 reader is an immutable ignored artifact, **not installed in either RIFT VM** and NOT yet proven to fix the Lab 1 feedback gap.

## Exact source, artifact and provenance

- Source: branch codex/modular-foundation, HEAD 63ae03ada7db96fa9657ee8c937a32dc778add25 at build. Worktree clean at start and immediately before documentation.
- Tracked fast-region implementation commits already in source: 4e91cac, 451fed5, fc9dd49; older deployed reader was built before these changes.
- New published single-file executable: artifacts/two-lab-resume-20261030/fastcandidate-published-01/RiftReader2.Live.exe
- New bundle SHA256: A4F6D9329A25695006F23695D776A8904A48FFAD487BA82BBABC4868270DB860; byte length: 117135200.
- Previous kept bundle: artifacts/validation/20261029T215649Z-6e2ed889/native-published/RiftReader2.Live.exe; SHA256: 322241A454A4685F75964F8DA4576A435DAA98D208CB4502D77B29D26390E268; byte length: 117102432.
- Preserved new sidecars: riftreader2-live.json SHA256 651A6648A59D5CE2C8B1BC822EBA77AA94DDF38446E293AD4156B30E8F5E499A; position-candidate-profile.json SHA256 FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8.

## Actual completed validation

| Check | Evidence | Verdict |
| --- | --- | --- |
| Exact .NET SDK | dotnet --version => 10.0.302 | PASS |
| Locked restore | rr2-fastcandidate-locked-restore-1030-a | PASS |
| Release solution build | rr2-fastcandidate-release-build-1030-a, zero warnings and errors | PASS |
| Core .NET tests | rr2-fastcandidate-all-dotnet-tests-1030-a, 366 | PASS |
| Live .NET tests | Same job, 195 | PASS |
| Focused fast-region positive/negative tests | rr2-fastcandidate-focused-fast-region-tests-1030-a, 6 | PASS |
| Format verification | rr2-fastcandidate-format-verify-1030-a | PASS |
| Lua 5.1 / Lupa 2.8 | rr2-fastcandidate-lua-runtime-1030-a | PASS |
| Real Lua/C# addon contracts | rr2-fastcandidate-lua-addon-contract-1030-a, 161 Lua and cross-language cases | PASS |
| Complete host Python tests | rr2-fastcandidate-python-with-lua-1030-b, **1155 tests, 2 skipped, zero failures** | PASS |
| Publish | rr2-fastcandidate-publish-win-x64-1030-a | PASS |
| Bundled native smoke | rr2-fastcandidate-native-smoke-ps5-compatible-1030-c, PE header, exact bundle SHA, stale epoch, no-overwrite | PASS |

**Environment limitation:** The normally authoritative PowerShell 7 wrapper (scripts/validate.ps1 via pwsh) was not available as a Workbridge executable. Windows PowerShell 5 altered quoting of the Lua preflight and wrote a BOM to the native request, so the untouched wrapper did not finish. Direct equivalent checks were run separately with the proper Lua-enabled Python. For native smoke only, an ignored test script copy used no-BOM JSON writes and Windows PowerShell 5 compatible stderr treatment and profile path. It printed an explicit PASS; the tracked production smoke script was not modified. Do not claim the standard PowerShell 7 wrapper passed.

**Other limits:** No current-game candidate-region fast observation has been observed from the new bundle. Lab 1 remains NOT qualified after sustained strict telemetry gap 16.214 seconds. Lab 2's prior 480-second PASS belongs to the previous source epoch and does not validate this new binary. No movement inputs or VM/addon/reader deployments were performed during this milestone.

## Next decision and required gates

1. Recheck current Git HEAD and all VM/game/reader/receiver/host identities. Confirm old readers genuinely ended; never run a duplicate reader against the same guest, and preserve prior binaries and no-overwrite evidence. Check per-VM cached credentials on **every** actual guest login.
2. Use existing reviewed launch workflow to deploy the new bundle into a fresh Lab 1 guest directory first, with a new unique nonce; handle shared host console ownership and addon rebind through the reviewed queue/capture/release procedure. Do not force-stop an existing reader or host on PID alone.
3. Confirm a received fastObservation / fastObservationDiagnostic payload with matching reader/game/nonce/provenance, and that the strict feedback parser accepts at least two advancing observations. Run a fixed, no-input 480-second timing window with complete misses/gaps reported. Preserve full-source fallback behavior.
4. If Lab 1 qualifies, repeat independently in Lab 2 (already passed previous-build eight-minute gate), compare equivalent windows, then begin only separately reviewed finite-arm movement calibration/trials. Keep 4.5-second feedback deadline and all existing STOP/input-release gates unchanged.
