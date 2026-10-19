# Current status

Updated: 2026-10-18 (America/New_York).

## Phase and direction

Modular hybrid foundation and minimal live transport, explicitly
authorized by Joey. RiftReader2 is independently developed around its own goals;
V1 remains reference evidence and lessons. See [ADR 0001](decisions/0001-modular-offline-foundation.md).
Joey explicitly requires a hybrid Lua addon plus external .NET application;
[ADR 0002](decisions/0002-hybrid-addon-and-reader.md) makes that product boundary
explicit. Joey subsequently authorized the minimal Lua addon, C# decoder, and
shared contract tests; that increment is complete offline under
[ADR 0003](decisions/0003-addon-observation-contract.md). The bare addon has
since passed one identified actual-client gate. Joey then authorized the
nonce-bound live increment selected in
[ADR 0004](decisions/0004-nonce-bound-addon-transport.md); its implementation,
final-build runtime gate, game restart, and VM restart qualification are complete.

## Implemented

- .NET 10 solution with Domain, Application, Infrastructure, CLI, isolated
  Windows Live executable, and separate portable/Windows tests.
- Strict versioned config and capture manifests; bounded UTF-8 JSONL replay with
  SHA-256 verification, same-session checks, and explicit gaps.
- Streaming derived motion analysis, cancellation, deterministic JSON reports,
  and publication that preserves existing evidence.
- Central build/package settings, exact SDK pin, package locks, and one local
  validation command enforcing module boundaries and behavior.
- Lua 5.1 package with separate encoder, bounded API sampler, and event hookup;
  typed player/position/health/combat observations, clock/lifecycle handling,
  and a strict 4096-byte contract.
- Typed C# decoder and `decode-addon --frame PATH [--output PATH]`, with exact
  frame hash, `unbound` source binding, and `unverified` freshness.
- Shared producer/consumer fixtures and a mandatory actual-Lua-to-C# gate;
  repository-local development runtime under ignored `artifacts/tools/`.
- Nonce-bound RR2L1 addon publication, strict selection and freshness tracking,
  a bounded read-only Windows scanner, atomic guest receipts, optional private
  IPv4 delivery, and a fail-closed host snapshot gate.
- Git initialized; local author `360madden <360madden@gmail.com>`; implementation
  branch `codex/modular-foundation`. Use Git for current commit/working-tree state.

## Verified

The [addon validation record](validation/addon-contract-2026-10-18.md) records
138 passing C# tests, 85 Lua assertions, and 11 actual Lua-to-C# shared cases.
The full gate passed locked restore, clean Release build, formatting, dependency
checks, links, and the existing deterministic synthetic replay. The 36 rejected
wire fixtures are included in the C# total. Earlier evidence remains in the
[foundation record](validation/foundation-2026-10-18.md).

The [actual-client record](validation/addon-live-client-2026-10-18.md) separately
records a controlled RIFT-Lab load after `/reloadui`. Bare RR2A1 advanced from
sequence 26 at clock 1109.16796875 to sequence 58 at clock
1125.2628173828125. Health and maximum health were 18208, matching the visible
UI; combat was unavailable. The guest-visible historical package contained four
files, but guest hashes were not collected. This proves the bare producer only
in that identified session; it does not validate RR2L1 or transport freshness.

The later [live transport record](validation/live-transport-2026-10-18.md)
records the complete RR2L1 gate in the same RIFT process: 12 consecutive fresh
snapshots, stale-copy rejection, `/reloadui` clearing, first-reader termination,
new reader instance/nonce remaining unbound until `/rr2bind`, old-nonce
rejection, and eight retained fresh rebound snapshots. Delivery remained
`gameReady: false`; host freshness is snapshot-only under an explicit 250 ms
guest/host UTC skew bound.

The final repository gate passed 173 C# tests (167 core and 6 Windows), 108 Lua
assertions, 11 RR2A1 plus 11 RR2L1 actual-Lua-to-C# cases, 9 Python host-gate
tests, a zero-warning Release build, locked restore, format and dependency
checks, deterministic replay, and 145 relative links. Evidence is under
`artifacts/validation/20261019T023621Z-e8a2a3f3`.
This final gate includes a conservative cancellation/deadline check after the
scanner's last read. The final executable, SHA-256
`42C02CB07886D6108ED84188263E1D1CEB99DBF59D605CABA90BE8AA3A210A08`,
subsequently passed the [restart recovery gate](validation/restart-recovery-2026-10-18.md).
The unchanged V1 console and receiver were reused only as lab infrastructure.

The recovery gate observed an ordinary RIFT process restart while the reader
remained running, then a graceful VM power cycle followed by manual RIFT and
reader relaunch. Each transition withheld observations, required a new nonce
binding, and returned to fresh advancing snapshots. The addon and final reader
persisted across the VM restart without reinstall. Delivery remains
`gameReady: false`; host freshness remains snapshot-only under the explicit
250 ms guest/host UTC skew bound.

At teardown, the reader reported termination, the temporary host receiver was
stopped, and the original VM DVD was restored. RIFT was left running and logged
in. Full process/build identities and evidence are in the recovery record.

## Next work

The RR2L1 increment is complete for the retained restart gates. The current
package has five files because `live.lua` was added; the earlier four-file guest
deployment remains historical evidence of the bare gate. Hard-crash recovery,
VM snapshot restore/resume, update recovery, loaded-module byte verification,
scan-performance optimization, and a production remote consumer remain
unqualified. VM recovery currently requires manual relaunch and binding.

Follow the [roadmap](planning/implementation-roadmap.md). Independently
reproducing the saved V1 wall-motion conclusion remains the next saved-evidence
case; it can proceed without a live bridge. Neither capability is established
by the synthetic demo.

The next highest-value choices are independently reproducing the saved V1
wall-motion result or qualifying update recovery. The durable field catalog,
native-field qualification, update measurement, and experiment runner remain
future increments. Start with one bounded task;
use [development guidance](workflows/development.md) to hand routine work to
cheaper models while retaining the same validation. Strong review remains
appropriate for semantics, provenance, schemas, native access, and concurrency.
