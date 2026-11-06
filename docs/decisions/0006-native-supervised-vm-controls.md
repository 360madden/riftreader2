# 0006: Guest-local native supervised VM controls

Status: accepted implementation choice under Joey's 2026-10-20 authorization;
live movement, camera, capture, and recovery qualification remains pending.

Date: 2026-10-20.

Authorized by: Joey requested a greatly improved, repository-native way to
control movement and camera interaction in VMware RIFT-Lab-1, then authorized
the resulting roadmap through completion with coherent commits.

## Question

How should RiftReader2 provide responsive supervised movement and camera input
without depending at runtime on original RiftReader tools, while preserving
bounded execution, exact target identity, release recovery, and honest evidence?

## Decision

Use a guest-local .NET input agent in the existing logged-in RIFT Windows
session. The guest opens an authenticated outbound connection to a
repository-owned Python host hub. A loopback-only browser surface supplies
reviewed, short-lived operator intent. The guest uses exact process, executable,
window, foreground, and geometry identity plus bounded Windows scan-code and
relative-pointer input.

Keep the portable boundary explicit:

- Domain owns the action and result records;
- Application validates and executes exactly one finite action through an input
  port, with cancellation/target checks and exhaustive release attempts;
- Live owns Windows process/window inspection, GDI capture, `SendInput`, the
  outbound agent protocol, and the durable pending-release journal;
- the host owns authentication, request IDs/sequences, sanitized evidence,
  optional VMware process-epoch checks, and the loopback operator API.

Movement and camera actions last 20 through 250 milliseconds. A standalone
wheel action has a zero hold. Arms expire after 15 seconds and require a current
reviewed capture. Stop disarms and waits for active release attempts. Release
cancels the current action but can leave a still-valid arm for continued
supervised input. Hard-crash cleanup requires explicit same-process recovery;
it is not automatic and cannot be guaranteed.

Do not steal or regain focus. After target loss, cleanup may send only intended
keyup/button-up events; no new press, relative move, or wheel input is allowed.
Input delivery and release remain distinct from visual response, addon/API
observations, native reads, and semantic field claims.

Record successful guest-local input insertions individually with post-call UTC
and monotonic timestamps. Keep `ControlExecutionResult.ObservedDuration` as the
whole executor duration, including target checks, delivery, the bounded hold,
and release attempts; do not label it measured hold time.

Center the guest cursor before button and wheel actions. Restore the original
point only when it was inside the same still-matching RIFT client rectangle.
When it began outside that client, leave it centered so subsequent wheel input
continues to route to RIFT. Cursor placement and restoration are not camera
orientation evidence.

The existing private port `49712` is reused for the outbound guest connection.
No firewall or global configuration change is part of the decision. The new
runtime imports no V1 source. The old guarded experiment script remains legacy
evidence tooling rather than the interactive architecture.

## Alternatives and reasons

Repository-owned VNC remains useful for bounded bootstrap, VM identity, and
fallback screenshots. Standard RFB pointer input is absolute, however, and the
current control problem needs guest-local relative camera deltas and release
timing. It is therefore a fallback, not the primary movement/camera transport.

Sending Windows input to the VMware console on the host was rejected because it
adds a second focus and pointer-capture layer and weakens the binding between an
input and the intended guest game window.

Continuing to import the original RiftReader controller was rejected because it
preserves the measured per-pulse setup cost and V1 runtime dependency that this
repository was created to replace. V1 remains read-only reference and retained
historical evidence.

A new service, driver, process injection path, debugger, or automation framework
was unnecessary and outside the authorized scope.

## Consequences

The timing and release loop now runs beside the game rather than across VNC.
Movement chords, relative mouse deltas, left/right drag, wheel, short arm
expiry, stop, and explicit recovery share one bounded contract. Request and
response evidence can be replayed without treating it as proof of game behavior.
Per-input guest events improve insertion timing evidence, while the executor's
whole-call duration remains unsuitable as a direct hold-accuracy measurement.

The operator must keep RIFT foreground and visually review a current frame. The
agent will not launch RIFT, switch desktops, elevate, or repair focus. GDI client
capture may be black or incomplete in full-screen/composited modes; such a frame
blocks review instead of silently falling back. Windows timer, `SendInput`,
UIPI, game input handling, camera semantics, and hard-failure key state still
require empirical qualification.

The control panel may generate a sequence of separate finite actions while a
human holds a key, but the Application executor itself has no autonomous loop,
path planning, navigation, combat, or action replay. The 15-second arm bounds
the interactive session; each action remains independently validated and
journaled.

## Validation and follow-up

Portable executor tests cover bounds, opposing/duplicate keys, chords, partial
press failures, release failures, cancellation, target loss, relative camera
and wheel flows, timer rounding, and the final target check. Windows adapter and
host protocol tests cover strict configuration, scan-code/layout bounds,
authentication, request correlation, ordered sequences, release passing an
active action, evidence sanitization, strict HTTP payloads, and bundle hashing.

Those tests establish software behavior only. No decision record currently
claims that the new path has moved the player, controlled the RIFT camera,
produced a correct non-black live capture, met a latency target, or recovered a
real hard failure. A live validation must pin the published executable hash,
VM/process/window/receiver identities, reviewed before/after frames, action and
release results, independent fresh API observations when used, and every
material limitation. See [the operating reference](../reference/native-vm-controls.md).

## Supersedes or is superseded by

This decision supersedes original RiftReader runtime control as the recommended
interactive path for RiftReader2. It does not supersede the hybrid addon/live
transport decisions, native read-only capture, field qualification, or retained
legacy movement evidence.
