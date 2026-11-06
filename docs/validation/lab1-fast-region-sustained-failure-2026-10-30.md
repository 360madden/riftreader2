# Lab 1 optimized reader: sustained strict-feedback result — FAIL (2026-10-30)

**Verdict:** New fast candidate-region scanner works and passes source pin/short read-only readiness, but **fails** the 4.5-second sustained feedback-gap requirement. No reviewed movement was attempted.

## Exact setup and provenance

- Git source milestone: 4c2af49; source build prior to live test unchanged. Optimized published Windows x64 reader SHA256 A4F6D9329A25695006F23695D776A8904A48FFAD487BA82BBABC4868270DB860, earlier published reader SHA256 322241A454A4685F75964F8DA4576A435DAA98D208CB4502D77B29D26390E268 preserved.
- Lab 1 VMware VMX C:\rift modding\VMs\RIFT-Lab-1\RIFT-Lab.vmx, VM PID 11164. Guest RIFT PID 9928, ticks 639289678898789677, unchanged game SHA 1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8.
- Optimized reader PID **14232**, nonce c0aa788dc0b74abbac7150bd511842dd, TTL through 2026-10-30T21:32:46.5557448Z, receiver PID 24588 at 192.168.56.1:49813.
- Live launcher returned reader-running-postflight-verified, inputSent=false and no agent stop. New addon rebind was reviewed from an exact fresh screenshot and completed with inputSent=true / releaseSucceeded=true; **this was only the command to bind a reader, not movement**. Two earlier stale screenshot attempts were rejected without input.
- Pinned strict source: artifacts/two-lab-resume-20261030/fastcandidate-lab1-source-pin-02.json, SHA256 8E326802A82E31A0C469F7BA66C45986AB2B2EAA50AE4D8712134F20B3C49081. Two advancing strict samples outer 495 to 496, addon 16291 to 16293, source candidate-regions, action-readiness check PASS. Single short qualification does not prove sustained availability.
- The original main-PC Lab 1 control host was gracefully stopped to release console ownership, then restarted from a NEW nine-source-hash/identity-pinned plan as detached Windows Session 2 pythonw PID **11616**. The connected/disarmed/idle/zero-held-input ready gate passed. Lab 2 remains independent; no game controls were used in this qualification.

## Complete eight-minute no-input acceptance result

- Evidence: ignored artifacts/two-lab-resume-20261030/fastcandidate-lab1-strict-480s-01.json
- SHA256: **FAC29EF3E85931505253CA42DF51C38A220E11BDC46E73AC82A637079F1D367E**
- Observer script: ignored artifacts/two-lab-resume-20261030/fastcandidate-lab1-strict-observer.py; exact pinned _movement_receipt strict validator unmodified.
- Job rr2-fastcandidate-lab1-strictobs-480s-1030-a exited **2** with status not-qualified; independent structural verification rr2-fastcandidate-lab1-480s-independent-check-1030-a exited 0, validating this FAIL.

| Metric | Observed |
| --- | ---: |
| Requested / actual duration | 480 / 480.0 seconds |
| Polls | 952 |
| Distinct advancing accepted receipts | 474 |
| Accepted source scope | fastObservation: 474 candidate-region receipts |
| Temporary live-receipt-not-fresh polls | **298** |
| Duplicate polls | 180 |
| Worst no-new-accepted-receipt gap | **7.5649 seconds** |
| Maximum permissible movement gap | **less than 4.5 seconds** |
| Fast scan elapsed median / P95 / max | **131.986 / 149.197 / 514.893 ms** |
| Effective inner age median / P95 / max | 919.665 / 1476.052 / 1615.990 ms |
| Player identity and addon epoch | Stable across all accepted receipts |
| Planar displacement | 0.0 |
| Observer game inputs | None |
| Receipt clock synchronization | Assumed, not independently proved |

Early 60-second checkpoint already exceeded the deadline (4.5373sec); 180-second checkpoint reached 7.5649sec. This failure remains despite substantially reduced **scoped scan duration**, so do not equate fast scan times with continuous source freshness. The observer records only strict accepted receipts as movement evidence. It contains no signed-off motion, no general pathfinding, and no proof of absence of unrelated manual input.

## Action required

1. Run bounded read-only forensic receipt sampler with this exact current pinned reader epoch: log raw full/fast observation freshness, full-scan anchor expiration, selection/warmup reasons, scan durations, and strict gate decisions for each advancing envelope. Do not loosen thresholds or treat raw diagnostic observations as accepted movement samples.
2. Identify the smallest supported source/anchor transition problem; prioritize **correctness and continuous verified feedback**, not artificially increasing anchor lifetime or freshness timeouts.
3. Add focused C#/Python positive and negative transition regressions with exact player/epoch, nonce, scan timing and fail-closed state. Preserve old published bundle; rebuild and full test as required for production code changes.
4. Requalify eight-minute fixed window on a fresh reader and separately on Lab 2 before any movement. Existing Lab 2 prior-build accepted window 4.036s does not qualify this reader or Lab1.

## Offline follow-up — guarded fast-to-full renewal (2026-11-01 04:09 UTC)

A separate review of the existing program loop isolated one credible **handoff** mechanism: while scoped fast scans continuously advance their private freshness tracker, the full-scan tracker only calls `GetCurrent()`, then often has a gap greater than its original 5s timeout at the 10s full-anchor turnover. Full-scan `Observe()` correctly returns warming, while the next private scoped tracker starts with a warming baseline. This mechanism is confirmed by source inspection, **not proven to explain every observed 7.5649s gap**.

Source-only correction in `src/RiftReader2.Live/Program.cs` and `FastObservationSession.cs`:

1. Snapshot identity-bound, genuinely Fresh scoped history **before** a new full scan starts. Never pass scoped data as the new full result.
2. After the full scan completes, accept continuity only if the actual new **completed, uniquely selected full-scan** frame matches exact process/build/nonce, player and epoch, advances sequence and clock, and passes the existing tracker’s original acquisition-gap and clock-skew checks. Only then promote that tracker for **both** the outgoing report and the saved after-delivery snapshot.
3. A scoped read that finishes after the 10s anchor expires is explicitly **withheld** and does not advance continuity. An older still-Fresh private sample may serve as renewal history. Reports of withheld scoped frames omit their candidate IDs/hashes to prevent mixing prior accepted envelopes with expired candidates.
4. Reject incomplete/missing/conflicting scans, wrong identity/nonce, stale or regressed sources, and full scans beyond the original 5s freshness window. **No 10s anchor, 5s freshness or 4.5s movement acceptance threshold was increased.**

Focused positive/negative regressions were added to `tests/RiftReader2.Live.Tests/FastObservationSessionTests.cs`. The offline command `dotnet test tests\\RiftReader2.Live.Tests\\RiftReader2.Live.Tests.csproj --no-restore --nologo --verbosity quiet` passed **200/200 tests, 0 failed**, job `rr2-offline-fresh-renewal-dotnet-tests-20261101-02`, exit0; net10.0-windows, Debug. An independent read-only code review found no blocking state/provenance defect and its recommended nonce, expiry and outgoing/saved parity tests were added.

**Not yet done:** no rebuilt/deployed Windows guest reader, no new addon bind, no current controller action or RIFT input, no eight-minute live Lab1/Lab2 validation, and no full-game restart qualification. The prior 480-second **FAIL** remains the operational gate. The separate native typed-HP Lab2 live read was declined at tool approval earlier and was not retried. This offline fix does not change that authorization boundary.
