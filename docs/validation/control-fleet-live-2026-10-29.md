# Two-lab native control fleet validation — 2026-10-29

Status: **implementation, both initial live read-only paths, and managed
reconnect/isolation passed.**

This checkpoint records the practical boundary reached while restoring one
native control host per lab. Generated evidence is under
[`artifacts/control-fleet-repair-20261029`](../../artifacts/control-fleet-repair-20261029/).
The result is scoped to the running hosts and managed guest-agent maintenance
tested here; it is not an automatic host/VM boot or unlimited durability claim.

## Implemented and reviewed

- [`control_fleet.py`](../../scripts/control_fleet.py) permits cloned guests to
  share the same reported Windows machine name. A machine name is descriptive,
  not a unique lab identity. The fleet still requires distinct VMX resources,
  guest addresses, endpoints, output directories and guest/operator secrets.
  The live hosts also use separate coordination resources in the shared queue.
- [`vm_console_native.py`](../../scripts/vm_console_native.py) now follows the
  Windows API table contract: rows returned by
  `TCP_TABLE_OWNER_PID_LISTENER` are already listener-classified. It still
  requires one exact loopback row and the exact current VMX owner. It does not
  accept wildcard, duplicate, non-loopback or wrong-process ownership.
- The listener change is deliberately minimal. No extra live RFB probe was
  added to normal helper requests. Host diagnostics had independently shown
  that Windows placed both VMware endpoints in the listener-only table even
  while reporting inconsistent per-row state metadata.
- Both source changes received independent review. Focused tests cover the
  retained uniqueness and identity rules, duplicate cloned machine names, the
  listener-table contract, wrong addresses and duplicate/wrong owners.
- The final full gate passed **973 Python tests** and **539 .NET tests**. This
  establishes the repository checks for the implementation; it is not a
  substitute for each lab's authenticated live connection.

## Diagnostic boundary

Lab 2 underwent two orderly full VM stop/start cycles while isolating the VNC
failure. The first replaced VMX PID 50544 but port 5906 still appeared in the
Windows listener-only table with noncanonical state metadata. A second cycle
moved VNC to unused loopback port 5962 and produced current VMX PID **52072**;
the same metadata behavior remained.

The restarts and port change did not repair the state field. Read-only API and
protocol evidence instead established that both endpoints were unique,
loopback-only, owned by their exact current VMX processes, accepted a connection
and returned the RFB 3.8 greeting. The implementation fix therefore uses the
explicit listener-table classification rather than weakening VMX ownership,
loopback or uniqueness checks. The detailed sanitized analysis is in
[`transport-audit/host-transport-diagnostic.md`](../../artifacts/control-fleet-repair-20261029/transport-audit/host-transport-diagnostic.md).

## Lab 1 live pass

Lab 1's host runs as `pythonw.exe` PID **52064**, process-start FILETIME
**134377351859468501**. Its private endpoints are:

- guest agent: `192.168.56.1:49810`;
- operator API: `127.0.0.1:49811`.

Authenticated live status reported the expected guest source
`192.168.56.128`, exact Lab 1 VMX PID **49392** and epoch
`2026-10-29T07:44:28.498Z`, and a foreground RIFT target PID **6988** with
start ticks **639288582195539972** and the pinned executable hash.

The bounded read-only verification passed:

- initial and final status were connected, disarmed, idle and without sampled
  desktop input down or recovery required;
- an unleased capture request was denied as required;
- one leased screenshot capture succeeded and retained exact bytes and SHA-256;
- no arm, action or recover command was issued;
- STOP/release completed, the request finished `succeeded`, and the coordination
  resource ended free with no holder;
- journal review found zero arm/action/recover operations in the new records and
  in the current host journal.

Evidence: [`lab1-live-verification`](../../artifacts/control-fleet-repair-20261029/lab1-live-verification/),
including `summary.json`, initial/final status, queue result, journal proof,
unleased denial and the retained capture.

This proves one authenticated, coordinated Lab 1 read-only capture lifecycle.
It does not prove movement, camera input, long-idle reconnect durability or the
second lab.

## Lab 2 initial live pass

The planned Lab 2 agent bind at `192.168.56.1:49820` failed with Windows error
10013 even though that port was not in the reported excluded ranges. No firewall
or system setting was changed. The replacement endpoints were independently
bind-tested before launch:

- guest agent: `192.168.56.1:49920`;
- operator API: `127.0.0.1:49921`.

The Lab 2 host runs as `pythonw.exe` PID **6996**, process-start FILETIME
**134377361878398354**. Its process receipt is
[`artifacts/control-fleet-live/lab2/process.json`](../../artifacts/control-fleet-live/lab2/process.json).
Authenticated status reported source `192.168.56.129`, exact VMX PID **52072**,
VNC port **5962**, epoch `2026-10-29T08:03:57.939Z`, and foreground RIFT PID
**11896** with start ticks **639288583877737737** and the pinned executable
hash.

The same bounded read-only verification passed for Lab 2:

- initial and final status were connected, disarmed, idle and without sampled
  desktop input down or recovery required;
- an unleased capture request was denied;
- one leased screenshot capture succeeded and retained exact bytes and SHA-256;
- no arm, action or recover command was issued;
- STOP/release completed, the request succeeded, and `vm:rift-lab-2` ended free
  with no holder;
- journal review found zero new arm/action/recover operations.

Evidence: [`lab2-live-verification`](../../artifacts/control-fleet-repair-20261029/lab2-live-verification/).
The reused verifier accidentally retained a `lab1-readonly-...` request prefix
and wrote a static Lab 1 journal-path label into the derived proof. The actual
queue lease/resource, supervisor epoch, host status and hashed journal were all
Lab 2. [`artifact-label-correction.json`](../../artifacts/control-fleet-repair-20261029/lab2-live-verification/artifact-label-correction.json)
records the discrepancy and correction transparently; no Lab 1 receipt is being
used as Lab 2 evidence.

Lab 2 had the same cloud-backed `guidance.lua` read failure previously seen in
Lab 1. Root preserved the unreadable file under a unique backup, repaired it,
verified all six installed addon-file hashes against the pinned source, and
completed the guarded in-client reload. A subsequent native capture showed no
visible Lua error. This establishes the repaired installed bytes and one clean
post-reload view; it does not yet reproduce a guidance result in Lab 2.

The VMware Lab 2 console is also visibly open in the ordinary Workstation GUI.
Lab 1 and Lab 2 are tabs in the same Workstation window. This resolves the
earlier no-GUI confusion but is not additional control-host evidence.

## Guest read-only audits

Ephemeral guest Codex CLI audits completed with exit code 0 in both labs. They
were sandboxed read-only, sent no game input, launched no target process or
network service, retained no raw authentication material and left no diagnostic
task running. The audits inventory existing files and metadata only; they do
not establish deployment readiness. See
[`guest-codex-audit-summary-20261029T0418Z.json`](../../artifacts/control-fleet-repair-20261029/guest-codex-audit-summary-20261029T0418Z.json).

## Managed reconnect and isolation pass

The terminal
[`reconnect-isolation-v3`](../../artifacts/control-fleet-repair-20261029/reconnect-isolation-v3/)
run exited 0 and reports `passed`. It restarted only the deployed control agent
in one guest at a time; neither VM nor RIFT was restarted.

For Lab 1:

- the old agent shut down cleanly and the new agent reached ready;
- the guest instance changed while the host instance remained unchanged;
- the host connection counter increased exactly once, from 8 to 9;
- VMX PID/epoch and RIFT PID/start/hash remained unchanged;
- Lab 2's host, guest instance, VM/game identity and released input state stayed
  unchanged during the Lab 1 transition.

For Lab 2:

- the old agent shut down cleanly and the new agent reached ready;
- the guest instance changed while the host instance remained unchanged;
- the host connection counter increased exactly once, from 1 to 2;
- VMX PID/epoch and RIFT PID/start/hash remained unchanged;
- Lab 1's host, guest instance, VM/game identity and released input state stayed
  unchanged during the Lab 2 transition.

Final status showed both hosts connected and ready, both guests disarmed and
idle, no sampled desktop input down, no recovery required and no in-flight
console work. The coordination queue was idle, and whole-journal review found
zero arm/action/recover commands. Each maintenance operation succeeded; its
short maintenance request was revoked by the expected guest-session transition
rather than left held or pending. See `summary.json`, `final-status.json`, the
per-lab before/after records and the two `*-restart` receipt directories.

An earlier harness attempt rejected a stale XYZ memory profile before any VM
input. The successful v3 trial used only the deployed control executable/game
hash, guest source/runtime and host/VM process pins. It did not modify, load or
depend on a native memory profile.

## Practical maintenance boundary

This proves that, with both current host processes already running, each managed
guest control agent can be cleanly replaced and authenticated again without
changing its VM/game identity or disturbing the other lab. It also proves the
tested queue and release state remained clean throughout those two transitions.

It does **not** install or validate automatic startup after a physical-PC boot,
VM boot or Windows login. It does not establish every future VM/game restart,
long-idle/network-failure recovery, movement, camera, typing or gameplay action.
The initial captures and reconnect test also do not reproduce a live guidance
calculation/result loop in either lab.
