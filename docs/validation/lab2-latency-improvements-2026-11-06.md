# Lab 2 latency improvements — November 6, 2026

Lab 2 now serves a read-only, fresh-byte game identity operation over its existing
authenticated controller connection. Cached guest logins use a fixed authenticated
file-existence probe instead of enumerating every guest process. Both changes were
measured live against the unchanged Lab 2 VM and game epoch.

## Observed before and after

| Operation | Before median | After median | Samples |
| --- | ---: | ---: | --- |
| Open a VM-specific cached guest session | 5.325 s | 0.580 s | 3 before / 3 after |
| Fresh game PID/start/SHA query | 4.299 s | 0.112 s | 3 before / 5 after |

The session improvement is approximately 89%; the fresh identity improvement is
approximately 97.4% (38.3 times faster). During the initial activation, interleaved
legacy identity queries still took 4.415 s median (3 samples; range 4.317–5.380 s).
Final-build persistent queries ranged from 0.092–0.143 s after the validation load
finished. These are small, warm-filesystem operation samples, not percentile
estimates or an end-to-end ChatGPT speedup. Connector routing and model time
between calls are outside these measurements.

The VM remained `RIFT-LAB-2`, VMX `C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx`,
VNC 5962, vmware-vmx PID 17848/start ticks 134383662779267832. RIFT remained
PID 9752/start UTC ticks 639294897826627677, executable SHA-256
`1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`.
These are evidence identities, never reusable authority for a later run.

## Identity and ownership guarantees

`POST /api/identity` accepts exactly `machineName`, `processId`,
`processStartUtcTicks`, and `executableSha256`. The host authenticates the caller,
matches the authenticated guest machine, and retains the transport's unique
request ID/sequence correlation. The guest checks its configured executable path
and build, expected machine and process epoch, then hashes file bytes on every
request. It holds a read-only handle denying concurrent writes/replacement and
checks file metadata and process epoch/path around the hash. It returns
`identityVersion: 1`, `hashMode: fresh-bytes`, an observation time, and the target.
The Python client additionally checks the VM before and after, matches the
authenticated host session's VM epoch, and validates capability, receipt
freshness, and exact expected identity. The guest rejects identity requests while
an input action is active, before parsing or hashing, preserving STOP handling.
It never falls back to cached status or a legacy operation after rejection.

The login probe still rereads that VM's cached credentials on every login and
retains before/after VM checks. It invokes authenticated `fileExistsInGuest` for
the fixed Windows PowerShell executable and requires the positive success
receipt. A synthetic nonexistent account was rejected live; the real cached login
continued working without modifying Credential Manager. Missing files, ambiguous
receipts, invalid credentials and unavailable Tools fail closed.

Live wrong-PID and wrong-hash identity requests were rejected. Final status was
ready, disarmed, idle, without sampled held inputs or pending recovery. No game
input or focus command was issued; no game/VM restart, host power/security change,
or Lab 1 guest operation occurred. The early foreground observation was false
and the final one true; the cause of that state change was not established.

## Use

Acquire the current expected game epoch independently, then call:

```powershell
python scripts/fresh_game_identity.py `
  --host-config artifacts/control-fleet-live/lab2/host.json `
  --expected-machine RIFT-LAB-2 `
  --expected-game-pid <CURRENT_PID> `
  --expected-game-start-ticks <CURRENT_START_TICKS> `
  --expected-game-sha256 <CURRENT_BUILD_SHA256>
```

For several related local operations, use one bounded developer command or the
existing authenticated shared-service connection rather than one remote tool
round trip per field. The fresh query itself introduces no service, input lease,
arm, automatic fallback or dependency on the older RiftReader checkout.

The VNC addon console retains its existing identity route. It owns the same console
mutex as the persistent controller, so silently switching its identity checks to
the live host would conflict with ownership. Its cached-session startup benefits
from the cheaper login probe; accelerated console input was not tested or claimed.
Movement/input paths continue to require foreground by default. Only explicit
read-only managed guest maintenance opts out of that movement precondition.

## Activation and rollback

The old host's exact process/task/config/VM and original source hashes were
verified against clean baseline commit `00b9efdc`; this was shutdown-only proof,
not permission to act through changed source. Its authenticated STOP, process
exit and console release were verified before the normal managed successor
started. An initial start using the console venv was refused by the existing task
contract; the registered `C:\Python314\pythonw.exe` path was then used, and its
new managed receipt/source hashes were independently verified.

Only the new guest executable was staged. A raw 117,274,464-byte transfer timed
out; the incomplete unreferenced file was inspected and subsequently removed.
A SHA-pinned, single-entry ZIP was checked before extraction and produced the
exact expected executable hash. The final 47,766,443-byte archive transferred in
26.797 s. Launcher
entrypoints and private configuration were preserved.

The existing guest launcher performed a queue-leased, graceful update using the
new managed-controller adapter. It verified old-agent cleanup before starting the
new agent. Postflight required the same host and game epoch, an advanced
connection, a new guest instance/supervisor epoch and verified initial cleanup.
The maintenance lease was revoked through the verified session transition.

Active final release: `agent-379637a8d2c0-zip`, executable SHA-256
`379637A8D2C058F61B4B601FB909D2C250F9F5DEBC12D6B9B245300350441F07`.
The previous executable release and its exact two-field descriptor are retained.
A rollback uses the same guarded update command and saved descriptor, after
checking the current request result and cleanup state; never overwrite
`current.json` or force-kill an uncertain owner.

Local evidence is under `artifacts/latency-implementation-20261106/`: before/after
identity and login timings, live negative checks, managed host receipts, launcher
update/cleanup proof, staged-file hashes and the rollback descriptor. Tokens and
private agent configurations are not included in tracked documentation.

## Validation

The full gate `pwsh -NoProfile -File scripts/validate.ps1` passed with exit 0:
380 portable and 317 Live .NET tests, 1,630 Python tests (2 skips), formatting,
published native synthetic smoke, real Lua/C# contracts, helper ownership mocks,
deterministic demo and 1,019 relative links. Evidence:
`artifacts/validation/20261107T012913Z-be52f075`.

Final live acceptance is in `artifacts/latency-implementation-20261106/final-acceptance.json`:
five new uncached identity responses, mismatch rejection, unchanged VM/game,
current managed source/task proof, and ready/disarmed/idle/unheld final state.
`guest-update-final/` records the final release transition; `rollback-release.json`
retains the original pre-change release descriptor. The broader gate is offline
validation; the exact Lab 2 acceptance above is the separate live evidence.
