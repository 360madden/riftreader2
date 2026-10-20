# Native supervised VM control validation — October 20, 2026

## Outcome and scope

The repository-owned guest input agent, host hub, CLI, and operator panel worked
on RIFT-Lab-1 without importing or running original RiftReader source. Separate
reviewed trials demonstrated backward movement, opposite A/D turns, a W+Q
movement chord, left-button camera orbit, and right-button yaw/pitch. Earlier
trials in this implementation pass also demonstrated forward W movement.
These are qualitative visual observations, not numerical position, heading,
pitch, zoom, or field qualification.

Windows accepted wheel input in both directions, but before/after frames did
not show a clear zoom change. Zoom remains unverified. Do not describe a
successful insertion result as a successful zoom.

The [roadmap](../planning/native-vm-control-roadmap.md) and
[usage contract](../reference/native-vm-controls.md) define the bounded scope.
No autonomous navigation, combat, injection, debugger, process writes, V1 source
changes, VM configuration changes, or firewall changes were used.

## Bound identities and retained evidence

- VM: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`, display name RIFT-Lab-1.
  VMware PID `39056`, start ticks `134369666367568339`,
  log epoch `2026-10-20T10:43:56.803Z`, loopback VNC port `5905`.
- Guest: `DESKTOP-8632QPL`, `192.168.56.128`.
- RIFT: PID `3400`, process-start UTC ticks `639280390564351086`,
  HWND `0x401F2`, `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`.
- RIFT executable SHA-256:
  `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
- Movement/camera trial agent instance: `219fecb462f84099b9bfc9bb66e34016`.
  The earlier instance was `df4f09edd3ac4f0da89d284c00778a42`; it was
  explicitly stopped and replaced while disarmed.
- Movement/camera trial executable SHA-256:
  `ED5094E6DCB476DA7B699677F96B3BF124DA9859FA3B30B7FFBD94679851FE3F`.
- Hash-checked deployment ZIP SHA-256:
  `E5A1B730AD6E70C209A45C390FCAC6C1F3B97E514BF23414FD0DB3779061BAAC`.
  Guest directory: `C:\RIFT_TRANSFER\RiftReader2Control\build-e5a1b730ad6e`.
- Final timeout-fix agent instance: `7e3e7dde18294bd2a072d2d908501154`.
  Executable SHA-256:
  `252DBFDD0E1761FC347DCC77E185A69C7682A21A57C1B482832627AC88EDED43`;
  deployment ZIP SHA-256:
  `E222E763C3809001C7B1AA6C78B67F34CDF0C96EEB57FAC8E8E86DD20F8BF7AB`.
  Guest directory: `C:\RIFT_TRANSFER\RiftReader2Control\build-e222e763c380`.
  The final full-gate published executable has the same hash.
- Local artifacts: `artifacts/native-control-20261020/`. Its
  `evidence-index.json` pins retained trial results, captures, and native
  control source hashes. Index SHA-256:
  `3B47B2F3E43D0FF23C4945A366A7B9DCB0DC0606F7820209D774B5C80B74FFED`.
  Secret-bearing host/guest configuration and arm artifacts are excluded from
  that index and Git.

The movement/camera trial executable supplied all rows below except the
explicitly earlier W trial. The final timeout-only change received the separate
review-age and panel-input checks below; the prior trials are not relabeled as
final-binary trials. The windowed client was 1211 × 686 at desktop origin `(0,23)`.
GDI client captures matched the visible RIFT scene in Thontic's Row. This does
not establish fullscreen or arbitrary graphics-mode capture support.

## Individual trials

Paths below are relative to `artifacts/native-control-20261020/trials/`.
Each input followed an inspected fresh frame, explicit review note, and a
short arm session. Captures disarm and require a new review.

| Trial | Before / result / after | Observed response |
|---|---|---|
| W 100 ms, earlier bundle | `move-before`, `move-result.json`, `move-after` | Forward movement relative to nearby ground/objects. |
| S 100 ms | `s-before`, `s-result.json`, `s-after` | Backward movement relative to ground and nearby NPC. |
| A 100 ms | `a-before`, `a-result.json`, `a-after` | Visible turn/viewpoint rotation. |
| D 100 ms | `a-after`, `d-result.json`, `d-after` | Rotation in the opposite direction. |
| W+Q 100 ms | `d-after`, `chord-result.json`, `chord-after` | Position change with lateral component consistent with the chord; exact strafe vector unmeasured. |
| Right drag `(10,-15)`, 100 ms | `final-look-before`, `final-look-result.json`, `final-look-after` | Yaw and pitch changed; the view exposed the stairs/horizon. |
| Left drag `(-10,0)`, 100 ms | `final-orbit-before`, `final-orbit-result.json`, `final-orbit-after` | Visible horizontal orbit. |
| Wheel `+1`, zero hold | `zoom4-before`, `zoom4-result.json`, `zoom4-after` | Windows insertion confirmed; no clear visual zoom. |
| Wheel `-1`, zero hold | `zoom-negative-before`, `zoom-negative-result.json`, `zoom-negative-after` | Windows insertion confirmed; no clear visual zoom. |
| S 250 ms interrupted by STOP | `stop-before`, `stop-result.json`, `stop-after` | Cancellation, successful key release, no pending release. |

All completed action results above reported successful release and no pending
recovery. The interrupted action correctly reported cancellation rather than
successful full delivery. The core deliberately retains `responseVerified:
false`; this document is the independent visual assessment.

Stale review attempts were rejected before input. A host request for three
wheel notches was rejected locally; the host deliberately permits only one
notch even though the core permits up to three. These rejected attempts were
not retried automatically.

## Timing and interruption

The final agent records monotonic timestamps immediately after each successful
Windows insertion. Down-to-up differences for the 100 ms requests were:

| Input | Insertion interval (ms) |
|---|---:|
| S | 114.1450 |
| A | 110.8527 |
| D | 106.5862 |
| W in W+Q | 111.1859 |
| Q in W+Q | 103.7808 |
| Right button | 127.6021 |
| Left button | 115.8296 |

The proposed ±20 ms target was met in these keyboard samples and the left
button sample, but not the right button sample. The executor's requested hold
starts after input setup; button-to-release also includes relative-move setup
and target checks. Scheduler delays and Windows checks are not hard real-time.
This is a small observed sample, not a latency distribution or a performance
guarantee. `observedDuration` includes the entire executor call and must not
be substituted for a measured key hold.

The stop trial submitted STOP about 75 ms after starting the host action
request. Stop round trip was **39.19 ms**, under the proposed 250 ms target.
The guest recorded key-down to key-up of **54.03 ms**, successful release, and
no pending recovery. Exact game key-state readback was not available.

The host was also terminated and restarted while the guest was armed but idle.
`reconnect-before-status.json` records armed state; after reconnect the same
guest instance was disarmed before its original arm deadline elapsed, with no
pending release. `final-stop.json` records the final stopped state. Active
disconnect cleanup is covered by offline tests, not a live host-loss-during-key
trial. Agent/OS/hypervisor hard-crash cleanup remains unqualified.

## Operator workflow and local validation

The local browser panel successfully authenticated, displayed a fresh RIFT
capture, accepted explicit review, armed for 15 seconds, delivered one brief S
keyboard action, released it on key-up, and stopped/disarmed.
`operator-panel.png` retains the observed panel. CLI trials exercised the same
host/guest action path. Browser Pointer Lock dragging and sustained keyboard
interaction still need a human usability pass; they are not claimed as
live-qualified from the CLI trials.

Review fixed two UI evidence defects: action outcomes are nested under `result`,
and JavaScript cannot represent the exact process-start tick value as a Number.
The panel now reads nested action outcomes and labels unsafe integers instead
of displaying a rounded identity as exact. Retained Python/.NET JSON evidence
preserves the exact integer.

The first panel pass exposed a 30-second guest idle-read timeout that could
invalidate the advertised 45-second review. The final executable raises only
that timeout to 120 seconds; the 15-second arm and bounded action deadlines are
unchanged. `idle-review-before`, `idle-review-arm.json`, and
`idle-review-stop.json` retain a successful arm after **35 seconds** of idle
review followed by stop, with no gameplay input in that test.

The final binary then completed the panel S action with successful insertion
and release, no pending recovery, and a **113.58 ms** insertion interval for
the requested 100 ms hold. See `panel-before`, `panel-result.json`,
`panel-release.json`, `panel-stop.json`, and `panel-after`. The game frame
changed consistently with movement. The sanitized host transcript is pinned as
`host-evidence-retained.jsonl`; the live log can continue growing separately.

The full local gate covers the new Python host/client/VM-console tests as well
as the existing .NET, Lua, replay, smoke, format, dependency, and link checks.
The final gate result and evidence directory are recorded in
[current status](../status.md).

The final host and guest remain available and disarmed. The former V1 receiver
and GuestObserver were stopped; their source remains unchanged. The temporary
bootstrap HTTP server was stopped. The native runtime imports only repository
code and its declared dependencies. Its VNC credential derivation label is
retained solely for compatibility with the existing VM credential.

## Remaining limits

- Wheel-to-zoom behavior is unverified; inspect actual RIFT bindings and input
  consumption before changing or advertising it.
- Numerical camera angles, zoom distance, and movement vectors are unqualified.
- Mouse-button timing did not consistently meet the proposed ±20 ms target.
- A/D and Q/E retain the user's game bindings; no bindings were changed.
- Text-entry detection is unknown; human review remains necessary.
- GDI fullscreen behavior, sustained panel usability, and hard-crash recovery
  are not established by these checks.
- Initial guest deployment used a private artifacts-only composition. The
  tracked guide supports manual hash-checked transfer; there is no unattended
  installer or service.
