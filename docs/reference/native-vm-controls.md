# Native supervised VM controls

Status: implemented and exercised on RIFT-Lab-1. The
[October 20 live record](../validation/native-vm-controls-2026-10-20.md)
demonstrates windowed capture, movement/chords, orbit, yaw/pitch, stop, and idle
reconnect. The [native zoom record](../validation/native-zoom-2026-10-20.md)
demonstrates wheel zoom in both directions in the identified windowed session.
Sustained panel usability and numerical camera calibration remain open. The
[follow-up record](../validation/native-vm-controls-followup-2026-10-20.md)
adds browser-compatible camera drag, revised timing, and release feedback.

This path provides supervised movement and camera experiments for RIFT-Lab-1
without importing or running original RiftReader source. It is intentionally
small: a loopback operator page sends strict commands to a host hub, the RIFT
guest opens an authenticated outbound connection, and the guest executes one
bounded action in its existing interactive Windows session.

Dedicated navigation, combat, unattended input, process writes, injection, and
debugger attachment remain outside this repository.

## Runtime boundary

| Component | Responsibility |
|---|---|
| `RiftReader2.Domain/Control` | Machine-readable action and result records. |
| `RiftReader2.Application/Control` | Validate and execute one bounded action through `IControlInput`; it knows nothing about Windows, VMware, files, or networking. |
| `RiftReader2.Live/Control` | Bind an exact RIFT process/window, capture its client area, send guest-local Windows input, retain pending release intent, and host the outbound control agent. |
| `scripts/control_host.py` | Authenticate one expected guest, sequence commands, retain sanitized evidence, enforce the VMware process epoch when configured, and expose a loopback HTTP API. |
| `scripts/control_panel.html` | Require a reviewed screenshot, hold the short arm token, collect supervised keys and Pointer Lock deltas, and expose stop/recovery controls. |
| `scripts/vm_console_native.py` | Repository-owned VMware identity, console-capture, and bounded bootstrap helper. It is not the movement transport. |

The current runtime has no V1 Python or .NET imports. The older
`scripts/rift-experiment.py` workflow remains as legacy evidence tooling; it is
not part of this native control path. The existing private agent port `49712`
is reused. Do not add a firewall rule, listener, service, scheduled task, or
global Git/Codex setting for this workflow.

## Control contract

One action has this JSON shape:

```json
{
  "keys": ["w", "a"],
  "holdMilliseconds": 100,
  "mouseButton": null,
  "deltaX": 0,
  "deltaY": 0,
  "wheelNotches": 0
}
```

The strict bounds are:

- `keys` is a unique subset of lowercase `w`, `a`, `s`, `d`, `q`, and `e`;
  `w+s`, `a+d`, and `q+e` conflict and are rejected by the guest before I/O.
- movement and camera holds are 20 through 250 milliseconds;
- `mouseButton` is `null`, `left`, or `right`;
- `deltaX` and `deltaY` are relative values from -200 through 200;
- wheel input is a standalone action with no keys, button, or deltas and a
  zero-millisecond hold. The guest contract accepts -3 through 3 notches; the
  current host API deliberately narrows an operator request to -1 through 1;
- an empty action is invalid.

Examples of valid action payloads for `POST /api/action` follow. Substitute the
current short-lived arm token; never retain it in documentation or source.

```json
{
  "armToken": "REPLACE-WITH-CURRENT-ARM-TOKEN",
  "action": {
    "keys": ["w", "d"],
    "holdMilliseconds": 100,
    "mouseButton": null,
    "deltaX": 0,
    "deltaY": 0,
    "wheelNotches": 0
  }
}
```

```json
{
  "armToken": "REPLACE-WITH-CURRENT-ARM-TOKEN",
  "action": {
    "keys": [],
    "holdMilliseconds": 20,
    "mouseButton": "right",
    "deltaX": 24,
    "deltaY": -8,
    "wheelNotches": 0
  }
}
```

The executor validates the complete action before consulting the target or
sending input. It checks cancellation and exact target state before every new
press/move/wheel operation, checks the target at intervals no longer than the
requested 10 milliseconds during a hold, and uses a monotonic deadline rather
than accumulating timer requests. The hold budget starts after the first
successful press; subsequent chord/button/move setup consumes that same budget.
Expired setup rejects further presses or motion and still attempts release.
Its result distinguishes delivery, release,
cancellation, target loss, uncertain state, and the need for caller disarm.
`responseVerified` remains false: successful `SendInput` insertion is not proof
that RIFT moved or changed its camera.

`result.observedDuration` is the whole Application executor duration. It starts
before the first target/cancellation check and ends after all `finally` release
attempts. It therefore includes input calls, repeated process/window checks,
the requested hold, timer overrun, and release calls; it is not a measured hold
duration. The guest action envelope's separate `elapsedMilliseconds` begins
earlier in the action handler and also includes guest preparation through result
assembly, but it is recorded before response persistence.

The guest also returns `inputEvents` in call order. Each successfully inserted
key-down, key-up, button-down, button-up, or relative move records
its stable `kind`, the value, guest `timestampUtc`, and monotonic
`elapsedMilliseconds` relative to creation of that action's Windows input
adapter. The record is appended after `SendInput` reports complete insertion.
It is insertion evidence with guest timing, not the exact kernel event time and
not proof that RIFT consumed the event. A failed insertion has no success event;
use the executor error and release result as well.

Wheel actions use one targeted `WM_MOUSEWHEEL` message rather than `SendInput`.
The tested RIFT session ignored the latter wheel path despite successful
insertion. The adapter revalidates the reviewed process, HWND, foreground, and
client geometry immediately before dispatch. It requires the cursor inside
the client and rejects sampled held control keys, modifiers, or buttons.
It encodes signed wheel delta and screen coordinates according to Microsoft's
[message contract](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-mousewheel).
The host still caps each action at one notch.

`SendMessageTimeoutW` uses a 100 ms timeout with BLOCK, ABORTIFHUNG, and
ERRORONEXIT. It sends once, with no retry or alternate backend. Failure or timeout
means delivery is unknown and disarms the session; a wheel has no held state to
release. See the [Windows dispatch semantics](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendmessagetimeoutw).
A successful `wheelMessageDispatched` event records `notches`, backend
`WM_MOUSEWHEEL`, and `timeoutMilliseconds: 100`. This proves dispatch, not that
RIFT zoomed; `responseVerified` stays false in the transport result. Later visual
evidence is recorded separately.
The synchronous dispatch cannot be cancelled mid-call, but has no pressed key or
button and is bounded by its timeout.

Every intended key and mouse-button release is attempted individually in
`finally`, including after partial input failure, cancellation, or loss of
foreground. Cleanup is key-up/button-up only. Loss of focus never authorizes a
new press, mouse move, wheel event, focus steal, or automatic focus recovery.
There is an unavoidable small check-to-send race at the Windows API boundary;
the stop response waits for the active action and its release attempts.

Before a mouse-button or wheel action, the guest preserves an in-client cursor
with at least `32 + max(abs(deltaX), abs(deltaY))` pixels of edge clearance.
Otherwise it centers and verifies the cursor, rejects repositioning when a
mouse button is already down, and waits at least 50 ms before pressing, checking
cancellation and target identity between short waits. Preparation is outside
the hold budget. `cursorPreparation` records the original/prepared positions
and whether repositioning occurred.

The agent never restores the cursor after an action. This avoids extra warps
and, especially, moving the cursor after an unsuccessful button release.
The game retains cursor control. Placement is operational routing, not camera
orientation restoration. Status includes `desktopInputsDown`, a read-only
sample of Windows key/button high-bit state; it proves neither RIFT consumption
nor which person/process owns a held input.

## Build and guest deployment

Restore with the repository's locked dependencies, then publish the existing
self-contained Windows x64 single-file project into ignored artifacts:

```powershell
dotnet restore --locked-mode
dotnet publish src/RiftReader2.Live/RiftReader2.Live.csproj `
  --configuration Release --no-restore `
  --output artifacts/native-vm-control/publish
```

The publish output contains `RiftReader2.Live.exe`. Record and compare its
SHA-256 before running it in the guest:

```powershell
Get-FileHash -Algorithm SHA256 `
  artifacts/native-vm-control/publish/RiftReader2.Live.exe
```

The host can serve one authenticated bundle when `bootstrapFile` and
`bootstrapPort` are both present, and the VMware helper can perform bounded
Windows Run setup. The current one-time download/deployment composition and its
secrets are artifacts-only; there is no reusable tracked guest-bootstrap script
to cite as a supported end-to-end installer. Manual transfer through an
operator-controlled channel followed by guest-side `Get-FileHash -Algorithm
SHA256` comparison is the supported fallback. Do not place either token in a
normal command argument, Git, or this document. Treat the printed operator URL
as a secret and do not retain it in shared logs.

Create a private, absolute guest configuration beside the transferred bundle.
The parser rejects missing, duplicate, unknown, null, or incorrectly cased
properties. Replace every placeholder with the inspected values for the current
guest and RIFT executable:

```json
{
  "schemaVersion": 1,
  "hostAddress": "192.168.80.1",
  "port": 49712,
  "token": "REPLACE-WITH-RANDOM-SECRET-AT-LEAST-32-CHARS",
  "expectedMachineName": "RIFT-LAB-1",
  "processName": "rift_x64",
  "executablePath": "C:\\Program Files\\RIFT Game\\rift_x64.exe",
  "executableSha256": "REPLACE_WITH_64_UPPERCASE_HEX_CHARACTERS",
  "outputDirectory": "C:\\RiftReader2\\control-evidence"
}
```

`hostAddress` must be a literal RFC 1918 IPv4 address, `port` must be 1024
through 65535, the machine name must equal the guest's current Windows machine
name, and both paths must be absolute. The agent permits exactly one local
instance for `rift_x64`, starts disarmed, and opens the connection outward; it
does not expose a guest listener.

Launch from the logged-in interactive guest session that owns RIFT:

```powershell
& 'C:\RiftReader2\RiftReader2.Live.exe' control-agent `
  --config 'C:\RiftReader2\control-agent.json'
```

The guest must run at an integrity level permitted to insert input into RIFT.
The agent will not elevate, switch desktops, regain focus, or launch the game.

The guest permits up to 120 seconds with no host command before treating the
connection as idle. This must exceed the operator panel's 45-second screenshot
review window plus the possible 15-second arm window; a shorter connection idle
deadline could reconnect and disarm the guest during an otherwise valid human
review. This is only a command-read liveness deadline. It does not change the
15-second arm lifetime, the 20--250 millisecond action bound, target checks, or
input hold and release behavior.

## Host configuration and startup

`control_host.py` itself uses the Python standard library. Enabling the
repository-owned VMware epoch guard loads `vm_console_native.py`; console image
and VNC operations use the pinned packages in `requirements-control.txt`.
Install them into a repository-local ignored environment rather than global
Python:

```powershell
py -3 -m venv artifacts/native-vm-control/venv
& artifacts/native-vm-control/venv/Scripts/python.exe -m pip install `
  --requirement requirements-control.txt
```

Create a private host configuration under `artifacts/`. This is the complete
strict shape for the normal VM-guarded path without the optional bundle server:

```json
{
  "schemaVersion": 1,
  "bindAddress": "192.168.80.1",
  "agentPort": 49712,
  "uiPort": 49713,
  "guestAddress": "192.168.80.128",
  "expectedMachineName": "RIFT-LAB-1",
  "token": "REPLACE-WITH-THE-SAME-GUEST-SECRET",
  "operatorToken": "REPLACE-WITH-A-SEPARATE-RANDOM-SECRET",
  "outputDirectory": "C:\\work\\riftreader2\\artifacts\\native-vm-control\\host",
  "vmx": "C:\\PATH\\TO\\RIFT-Lab-1.vmx",
  "vmrun": "C:\\Program Files\\VMware\\VMware Workstation\\vmrun.exe",
  "vncPort": 5905
}
```

`bindAddress` and `guestAddress` must be literal RFC 1918 IPv4 addresses. The
VMX, `vmrun`, and VNC values are optional only as a group; omitting the group
also omits the host-side VMware process-epoch guard. `agentPort`, `uiPort`, and
an optional `bootstrapPort` are integers from 1 through 65535. If the optional
bundle endpoint is deliberately used, add both fields:

```json
{
  "bootstrapFile": "C:\\work\\riftreader2\\artifacts\\native-vm-control\\publish\\RiftReader2.Live.exe",
  "bootstrapPort": 49714
}
```

Those two properties extend the preceding object; the fragment is not a valid
standalone configuration. Use only an already permitted private port. This
workflow does not authorize a firewall change.

Start the host before the guest:

```powershell
& artifacts/native-vm-control/venv/Scripts/python.exe `
  scripts/control_host.py `
  --config artifacts/native-vm-control/control-host.json
```

The process prints JSON containing its agent endpoint, evidence path, and an
operator URL. The URL places the operator bearer token after `#`; fragments are
not sent in the HTTP request. The page loads the token, immediately removes the
fragment from the address bar, and sends it only in the `Authorization` header.
The UI server binds to `127.0.0.1`, requires its exact loopback origin for API
requests, disables caching, and must not be exposed remotely.

## Supervised lifecycle and helper API

The helper API is JSON over loopback HTTP:

| Request | Meaning |
|---|---|
| `GET /api/status` | Inspect host connection plus current guest target, arm, busy, and recovery state. |
| `POST /api/capture` with `{}` | Capture the bound client area, retain exact bytes, and return a review ID. |
| `POST /api/arm` | Accept `captureId` plus a 12-512 character `reviewNote`; issue a 15-second token only while the exact reviewed target still matches. |
| `POST /api/action` | Submit one validated action with that arm token. |
| `POST /api/release` with `{}` | Cancel the active action and wait for its `finally` releases. It does not disarm a still-valid session by itself. |
| `POST /api/stop` with `{}` | Disarm, invalidate the reviewed capture, cancel the active action, and wait for release attempts. It does not silently recover a journal left by a hard crash. |
| `POST /api/recover` with `{}` | Disarm and explicitly send only retained key-up/button-up intent when the recorded process epoch still matches. |

All POST bodies are strict JSON. Capture, release, stop, and recover accept only
the empty object. Commands use unique request IDs and increasing connection
sequences. The guest rejects replay, concurrent actions, unexpected response
artifacts, changed target identity, expired review/arm state, and a pre-existing
pending journal.

The normal sequence is:

1. Confirm the expected VM and authenticated guest connection.
2. Confirm `recoveryRequired` is false.
3. Capture a current frame. GDI client capture is provisional: a black, stale,
   obscured, wrong-window, or full-screen-incompatible image blocks arming.
4. Visually confirm RIFT is in-world and text/chat entry is closed, then arm.
5. Submit one bounded action and inspect the complete result. An HTTP 200 or a
   green panel message alone is not success; require delivery and release
   success, no cancellation/target loss, no recovery requirement, and the
   expected successful `inputEvents`. Treat `observedDuration` as whole-executor
   time rather than key/button hold time.
6. Acquire later independent visual and, when available, fresh addon/API
   observations before describing a game response.
7. Stop and disarm when the supervised trial ends.

The browser control surface can issue repeated finite actions while the operator
physically holds a supported key and the 15-second arm remains valid. For a
first qualification pulse, submit one action rather than relying on repetition.
Review has a visible 45-second countdown and requires a confirmation checkbox
plus a note of at least 12 characters. Arming consumes that review.
The default game bindings are W/S move, A/D turn, and Q/E strafe; inspect the
current game's bindings before attributing a different response to the transport.

Select Right yaw/pitch or Left orbit, then hold the left mouse button on the
control surface and drag. This default uses browser pointer capture and works
without Pointer Lock. Camera and movement pulses use 100 ms; pointer deltas
coalesce for 16 ms and remain bounded to ±200. Releasing or losing the captured
pointer clears queued deltas and requests release. Camera mode Off keeps
movement available without adding a mouse-button press.
For zoom, scroll over the focused control surface while armed. Camera drag
mode may remain Off; each wheel event requests one standalone notch.
Horizontal-only wheel events do not request zoom.

Pointer Lock is optional for compatible browsers. The Codex in-app browser
rejected it during the October 20 follow-up; use bounded drag there. Changing
mode during a drag/lock stops and disarms. Pointer Lock loss, browser blur,
page hiding, and arm expiry request stop. They do not prove that a guest hard
crash received key-up. The panel displays the last action outcome separately
from release/disarm status; successful insertion still does not prove game response.

The [usability pass](../validation/native-control-usability-2026-10-20.md)
adds serialized capture/arm/recovery transitions. A new screenshot from an
active session first stops it and clears held keys, queued deltas, wheel input,
timers, and pointer capture. Leaving the control surface releases active input;
Ctrl/Alt/Meta shortcuts do not become movement commands. Status has a separate
display and cannot replace the last action result.

Focus loss during a pending arm invalidates the local request and requests STOP
both immediately and after the pending arm settles. Guest STOP invalidates the
old reviewed capture, so an ARM sequenced after STOP cannot reuse it even if the
browser closes before sending its second STOP. Page exit makes a best-effort
keepalive STOP request; browser/network/OS failure can still prevent delivery.
The guest's bounded actions and arm expiry remain independent limits.

## Recovery and evidence meaning

Before a potentially stateful press, the guest atomically publishes
`pending.json` with the exact target and intended action. Normal completion
deletes it only after every intended key/button release succeeds. A failed
release marks state uncertain and requires disarm. A hard agent, guest, VM, or
OS failure can prevent `finally`; recovery is therefore explicit, not automatic
and not guaranteed.

`recover` validates the saved action and exact game process epoch before sending
keyup/button-up. A changed process retains the journal for manual review and
sends nothing. Recovery success records an attempted Windows input release; it
does not prove RIFT's internal key state or restore a camera orientation.

Keep evidence sources distinct:

- the reviewed BMP is visual evidence from a provisional GDI client capture;
- command/request, timing, and `ControlExecutionResult` fields are input intent,
  transport, insertion, and release evidence;
- guest `inputEvents` provide UTC and monotonic timestamps after successful
  input insertion or wheel-message dispatch; they do not show game consumption;
- a later screenshot may support a visible-response observation but supplies no
  numerical heading, pitch, or zoom by itself;
- addon/API observations require their own nonce, process/reload generation,
  sequence, freshness, and receiver identity checks;
- native memory remains separate raw acquisition and field qualification.

The new native control path does not currently acquire a fresh addon/API sample
as part of an action. Never infer one from a successful command, and do not call
movement or camera behavior live-qualified until a dated validation record pins
the exact bundle, identities, frames, results, limitations, and independent
observations used for that claim.
