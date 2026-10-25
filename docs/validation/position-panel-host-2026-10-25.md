# Position window: implemented and host verified, guest validation pending

**Later live progress:** [actual host button/visual checks now passed and guarded
guest maintenance is underway](position-panel-live-progress-2026-10-25.md).
The earlier permission-only block below is historical; use that later record
and current status for controller ownership and remaining work.

Joey authorized building a Start / Read / Stop interface around the existing XYZ
sampler and validating it through complete RIFT exit and relaunch on 2026-10-25.
Patch recovery remains deferred under [ADR 0008](../decisions/0008-full-game-restart-durability.md).

## Implementation

The existing Windows Live executable now offers `position-panel`; see
[usage and defaults](../reference/position-panel.md) and the
[acceptance plan](../planning/position-panel-roadmap.md). Windows Forms uses the
installed .NET 10 desktop framework/reference pack and self-contained publishing.
No project, third-party package, service or game-input capability was added.
The pinned position profile is published as a real sidecar file, excluded from
the single-file bundle so the default profile path is usable on a clean install.

Start schedules serialized fresh reads for at most ten minutes. Read takes one
sample without requiring monitoring. Stop cancels, clears XYZ immediately and
invalidates late completions. A private physical-read exclusion prevents overlap
even when an old operation ignores cancellation across Stop/Start. Each read
reuses the existing exact-build process discovery and pointer sampler; old PIDs
and absolute owner addresses are not imported. The console sampler's report
contract remains unchanged.

Values clear on reading/failure/cancellation and expire after three seconds,
measured monotonically from both read invocation and completion. Slow results
are never relabeled fresh. Partial, nonfinite, wrong-build and malformed/null
results fail closed. UI rendering uses current controller state when marshaling
back to the window thread, so an old queued render cannot restore stopped values.
The compact native candidate qualifications and exact SHA guards remain intact.

Evidence uses a new session directory: a session header, append-only event
journal, and never-overwritten original per-read sampler reports with hashes.
An existing evidence directory is rejected before opening the window.

## Host checks and evidence

The controller has **15 focused cases** covering the actual lifecycle boundaries:
fresh reads, concurrency, cancellation/late completion, Stop/Start exclusion,
new-process replacement, one-shot reads, monotonic expiry, bounded monitoring,
invalid values, wrong-build failures, and five independent malformed/null cases.

An initial full repository gate completed with exit 0 at
**2026-10-25T12:46:59Z**: 460 .NET tests, 669 Python, 108 Lua, 22 real Lua-to-C#
cases, zero-warning build, native published synthetic-host smoke, replay,
formatting and 541 links. That initial gate preceded the final profile-sidecar
and malformed-report hardening. Its evidence is
`artifacts/validation/20261025T124557Z-5af4d69c`; logs/results are
`artifacts/validation/position-panel-host-full-gate*`.

The **final hardened full gate passed with exit 0 at 2026-10-25T13:00:38Z**:
**465 .NET tests** (311 portable + 154 Live), **669 Python, 108 Lua and 22 real
Lua-to-C# cases**, locked restore, zero-warning build, formatting, deterministic
replay and **547 relative links**. The published-native smoke also verified the
exact physical profile sidecar and the public panel command's default-profile
load plus existing-directory refusal without opening a window.
Evidence: `artifacts/validation/20261025T125935Z-c3184d1d`, plus
`position-panel-final-recheck-full-gate.log` and its result under
`artifacts/validation/`.

Final published executable: **116,924,768 bytes**, SHA-256
`E1E6A5FB4D3C82F91DCBF8BD5FD8395A42A03FA1766380E12614B4A077C7D647`.
Its physical 395-byte profile sidecar retains SHA-256
`FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8`.
The separate pending-guest deployment record is
`artifacts/update-recovery-20261023-01/xyz-interface-restart-oct25-01/deployment.json`.

The preceding final-gate attempt had one unrelated disposable receiver fixture
failure: Windows File.Replace could not remove the fixture's replaced file.
The three focused receiver-startup tests immediately passed on rerun, followed
by the complete successful final gate above. No fixture or production retry
policy was changed. The failed attempt remains preserved as
`artifacts/validation/position-panel-final-full-gate.log` and result.

Two actual native window/message-loop instances created their session journals
on the host. The second was enumerated with title `RiftReader2 · Player position`.
Both were closed normally using WM_CLOSE targeted to their exact owned process
IDs/start ticks, without terminating processes. Their final stopped/closed events
are retained in `artifacts/validation/position-panel-host-window-01/` and
`position-panel-host-window-02/`. This proves startup/normal close only;
button clicks, visual layout and live game values were not established by it.

## Live gate: blocked by native desktop permission

The Computer Use tool could enumerate windows but rejected selecting/inspecting
the panel with **`Computer Use was not approved to use live`**. Joey explicitly
approved enabling live Computer Use, but the subsequent actual call returned
the same refusal. A text confirmation did not change the native tool's runtime
permission. The available plugin permission manager did not expose a working
control for this bundled native desktop capability.

After Joey explicitly requested that the agent enable it, the documented local
Computer Use app-approval setting was updated for **`riftreader2.live.exe` only**,
preserving all prior entries and the installed configuration layout. The saved
setting was read back successfully. A third actual panel launch accepted its
default sidecar profile. Selecting/inspecting its window still returned the same
refusal, including after refreshing the JavaScript tool session. Therefore the
saved app entry is **not proof that live control is enabled in this session**.
No global default or other app grant was broadened, and the refusal was not
bypassed with another desktop-control route. The supported setting is described
in [OpenAI's Computer Use documentation](https://learn.chatgpt.com/docs/computer-use).

**No new guest deployment or RIFT exit/relaunch was performed.** A fresh
authenticated read-only V20 status still found connected/ready supervision and
RIFT PID 9704 / start ticks 639285237698112372 on the existing exact build.
That is the earlier game epoch, not proof of a new restart.
The response is preserved in
`artifacts/update-recovery-20261023-01/xyz-interface-restart-oct25-01/preflight-status.json`.

A fresh ignored maintenance helper was prepared under that same directory,
requiring V20 fully exited, V21 not started, exact unchanged VM identity and
canonical queue quarantine before any console action. Its preparation did not
create a V21 plan, stop V20, connect a second console, launch a transfer listener,
or send guest input. It must not be invoked until the live permission is actually
available and fresh preflight succeeds.

## Resume

1. Resolve the native desktop tool permission and verify a real panel inspection
   succeeds before treating live access as available. The reader's local app
   entry is already saved; this session still rejects live access. Complete the
   app's actual live-control enablement/approval instead of repeatedly changing
   configuration or broadening global permissions.
2. Use the final published bundle/profile pins, not the earlier intermediate
   executable; prepare the same-VM V20-to-V21 recovery before maintenance.
3. Deploy into a new guest directory and exercise actual Start / Read / Stop.
4. Exit RIFT normally, prove zero game processes and no current XYZ, relaunch
   normally, enter the world and verify fresh PID/start/owner coordinates.
5. Preserve original evidence and restore sole coordinated supervision.

The earlier sampler movement/restart observations remain valid only for their
recorded scope. They are not substituted for this new interface's pending live
acceptance. Patch recovery remains deferred throughout.
