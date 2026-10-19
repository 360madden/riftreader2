# Nonce-bound live transport validation

Date: 2026-10-18 (America/New_York). Scope: one RIFT-Lab process, addon reload,
guest-reader restart, nonce rebinding, delivery, and host snapshot gating.

## Identified path

- RIFT target: PID 9428, start UTC ticks `639279712871697793`, path
  `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`.
- Target executable file SHA-256:
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
  The reader hashed the file at the process MainModule path under shared read and
  rechecked PID, start time, and path before and after. This does not prove the
  bytes already loaded in memory.
- Live-tested guest executable: 73,714,083 bytes, SHA-256
  `12D5FABA7E9389B07B2A0CEEFBFF30E88AEBA6AADFDC0E3A6BCEA3E1D48850D7`.
  Its copy was visible in the guest; no independent guest-file hash was taken.
- Delivery used the unchanged V1 receiver from guest `192.168.56.128` to host
  `192.168.56.1:49712`. Its token was neither logged nor tracked. The receiver
  was delivery-only and every receipt retained `gameReady: false`.

## Results

The first reader instance `97b147e3-3627-4d9e-80fa-165d0648cf01` used nonce
`e1e5e72339ea4166acd4f0cce27234ed`. A 15-second monitor accepted 12 consecutive
fresh snapshots with inner sequences 134, 136, 139, 142, 144, 147, 150, 152,
155, 158, 160, and 163. A retained example reported a complete 2,266,537,984-byte
private-memory scan in 661.5633 ms and last-advance age 806.798 ms against the
5,000 ms timeout. A frozen copy of that receipt was later rejected as stale.

`/reloadui` at about 02:27:15 UTC cleared the addon binding. A later complete
scan found no matching nonce, published no observation, reported
`lastAdvanceAgeMilliseconds: 18082.2119`, and was rejected by the host gate.
The first reader then exited through Ctrl+C after receipt sequence 172.

The restarted reader instance `df666fd6-85e2-4800-bbb9-82915bec6270`
generated nonce `e2632b6028e64568877fc583b6316bb0`. The RIFT PID, start ticks,
path, and file hash remained the same. Before `/rr2bind` it reported unbound with
no observation. The old nonce was rejected. After binding the new nonce, eight
retained fresh snapshots advanced through inner sequences 212, 215, 217, 220,
223, 226, 228, and 231. The ten-receipt monitor also retained one conservative
`read-failed` unavailable result and one warming recovery before the eight fresh
acceptances. The final retained gate reported effective inner age 1284.1701 ms
under the 5,000 ms limit. The second reader then exited gracefully at outer
sequence 120; `live-terminated-second.json` retains that result.

The host gate accepts a snapshot only when its receipt is at most two seconds
old, nonce and receiver identity match, the guest reports a complete scan and a
bound/fresh selected observation, and effective last-advance age remains below
the guest timeout. Cross-machine age is conditional on guest and host UTC clocks
differing by no more than 250 ms. It is snapshot-only evidence, not exact remote
age, a continuing subscription, or game-readiness proof.

## Scanner and selection limits

A complete scan covers the declared readable, committed `MEM_PRIVATE` domain
within byte, time, read, map, candidate, and region budgets. It is not a claim
to have read all process memory. Budget or read failures produce an incomplete
or unavailable result; occasional conservative read failures were observed.
Complete scans covered about 2.26 GB in roughly 0.5–0.8 seconds in this session.

Malformed candidate byte ranges are rejected and counted; they do not advance
freshness or produce observations. Valid strict candidates may still be chosen
when unrelated or freed Lua strings remain elsewhere. A scan without a valid
matching candidate is unavailable. Fully valid same-sequence conflicts invalidate the
selection. Guest-side freshness is based on last advancement and the remaining
timeout budget on every result; successful HTTP delivery alone never establishes
freshness.

## Repository gate and retained evidence

The full gate passed 173 C# tests (167 core and 6 Windows), 108 Lua assertions,
11 RR2A1 plus 11 RR2L1 actual-Lua-to-C# cases, 9 Python host-gate tests, a
zero-warning Release build, locked restore, formatting, dependency checks,
deterministic replay, and 145 relative links. Evidence directory:
`artifacts/validation/20261019T023621Z-e8a2a3f3`.

After live testing, a final conservative check was added to reject cancellation
or a scan deadline exceeded during the last read/candidate decode. The complete
repository gate above passed after that change. The final published executable
is `artifacts/live-validation/reader-final/RiftReader2.Live.exe`, SHA-256
`42C02CB07886D6108ED84188263E1D1CEB99DBF59D605CABA90BE8AA3A210A08`.
It was not redeployed or retested in RIFT. Live evidence in this record applies
to the earlier executable identified above; no live deadline-overrun scenario
was exercised.

Primary retained live artifacts are `live-fresh-receipt.json`,
`live-fresh-gate.json`, `live-initial-timeline.jsonl`,
`frozen-receipt-rejection.json`, `live-after-reload-receipt.json`,
`live-reader-restart-unbound.json`, `old-nonce-rejection.json`,
`live-rebound-fresh.json`, `live-rebound-gate.json`, and
`live-rebound-timeline.jsonl`, plus `live-terminated-second.json`, under
`artifacts/live-validation/`.

This gate did not restart RIFT, power-cycle the VM, prove loaded-module bytes,
qualify native fields, or establish a remote production consumer.

## Teardown

The second reader terminated gracefully at outer receipt sequence 120. Host
receiver PID 51948 was absent afterward and port 49712 had no listener. The VM's
prior DVD was restored successfully; VMX readback reported
`sata0:1.fileName = C:\RIFT MODDING\Media\RIFT-TypedObserver-017c.iso`. RIFT was
left running and logged in with RiftReader2 installed; that continuing game
state is not continuing reader or receiver freshness.
