# NAV-SCHED-02G - Native caller ownership and denied-first sessions

Date: October 21, 2026 (America/New_York). This source increment connects the
native HTTP, command-line and browser-panel callers to the existing queue's
send-boundary lease check. It also supplies a denied-first gateway construction
option. **The recovered live host has not been restarted or activated with these
changes.**

## What changed

A protected HTTP request can use the explicit JSON envelope
`{"access":{"request_id":"...","token":"..."},"payload":{...}}`.
The host authenticates the operator first, validates the envelope, validates the
original operation payload, and passes only the private capability pair to the
existing gateway/session admission policy. The guest sees the original payload,
not the queue credential. The host journal does not record that credential.

Capture, ARM, action and recovery share this path. STOP, release and status remain
credential-free and usable even after a lease expires or a local credential file
is missing. A lease is not an ARM token: both ownership and the existing fresh
capture/review/15-second ARM protocol are still required for input.

An explicit envelope was chosen instead of a header that an older host might
ignore. Existing strict handlers reject the new envelope. New callers never
retry a rejected owned request as an unleased request. A new host also rejects
lease credentials when no dispatch policy is installed. Legacy unwrapped calls
retain existing behavior only on an uncoordinated host; they do not bypass an
installed policy.

`control_client.py --lease <private.json>` accepts either the exact access pair
or a saved queue-dispatch grant, capped at 8 KiB. It copies and forwards only the
pair. Imported owner/resource/expiry metadata is not trusted as authorization;
the authoritative queue still checks current ownership, epochs, generations and
expiry at send time. The client does not acquire, renew, replay or repair leases.
Private parse failures omit input payloads, and console output continues token
redaction. The lease file is deliberately not read for STOP/release/status.

The browser panel can load the same file into memory. It does not store the token
in browser storage or display it. Importing, rejecting or clearing credentials
invalidates the old capture/review and never silently falls back to legacy mode.
A pending import cannot take effect after STOP; ownership cannot be switched while
requests or armed controls are active. The panel preserves ordinary STOP/release
and existing pointer/key cleanup. A loaded credential is explicitly described as
unverified until the host accepts it. Its keyboard help now says bindings belong
to the guest, rather than asserting Q/E are always strafing keys.

## Fresh-session boundary

`AgentGateway(..., require_supervisor=True)` creates every authenticated session
with protected calls suspended before publishing it. A reconnect gets a fresh
suspended session, never the former policy or privilege. Clearing the local latch
without installing a policy is not enough to enable protected calls. An existing
queue resource still requires explicit reconciliation, rather than being reset
by a new supervisor. A gateway that is closing rejects a late authenticated
connection.

This is an internal composition option, not a new live configuration flag. The
ordinary host entry point remains unchanged. The integration owner must still
construct and supervise `OwnedSupervisor` for each session and handle known
resource reconciliation; constructing a denied-first gateway alone leaves it
blocked. A supplied static shared policy is rejected in denied-first mode.

## Verification

The expanded focused run passed **259 tests**, including **22 new Python cases**.
The existing asynchronous panel harness now also exercises **eight new ownership
scenarios**, including stale file completion, clearing/rotating credentials,
private data display, rejection without fallback, and credential-free STOP.
Those browser cases run inside an existing Python test; they are not eight more
unique Python tests.

The original HTTP test failed against the baseline because it could not carry a
valid owned request. That expected failure remains saved. Updated tests use real
disposable loopback HTTP/guest connections, queue grants and the owned supervisor;
no game input is sent to the real VM. CLI transport and parser tests verify the
same envelope and bounded private-file handling. The isolated full repository
gate passed **364 C# tests, 380 Python tests, 108 Lua checks and 22 shared Lua/C#
cases**, with a zero-warning Release build, published synthetic native smoke,
formatting and deterministic replay. Job: `navsched02g-full-gate-20261021-01`.
Evidence: `artifacts/validation/20261022T030048Z-b50ed271` in the isolated candidate.
Post-promotion focused and preservation checks are separate; inspect the final
completion record for their actual results. Focused and browser counts overlap
this full suite.

## Use and limits

From the repository root, an already-issued private lease can be supplied as:

```powershell
python scripts/control_client.py --config <host.json> --lease <grant.private.json> capture --output <new-capture-directory>
```

The host must have an installed, ready owner and matching live authority. This
command does not create either. Browser loading is also transport only: queue
submission, grant acquisition, heartbeat, finish/cancel and cleanup remain owned
by the coordinator. Protect grant files as credentials; no secrets are embedded
in these examples.

Tests ran in disposable local authorities and simulated guests. No new native
host, VM restart, guest deployment, live capture/ARM/STOP/movement, dependency,
credential, firewall, global setting, commit or push is part of this increment.
The recovered host remains a normal user process with its previously loaded
code. Copying updated source does not hot-reload that process.

Remaining work: reconcile VM-console/bootstrap and legacy control paths with the
same authority, wire denied-first per-session supervision into the reviewed
production startup, implement explicit reconnect/restart reconciliation, then
activate and validate one bounded live trial. Full multi-controller exclusion is
not claimed. The local queue/management contract remains cooperative, not a
barrier against direct SQL, older callers or independently selected databases.

Evidence: `artifacts/navsched02g-20261021-01/evidence/`.
See [current status](../status.md), [queue roadmap](../planning/navigation-access-queue.md),
[native controls](../reference/native-vm-controls.md), and
[owned supervisor](navigation-owned-supervisor-2026-10-21.md).

Model: GPT-6 Astra Pro. Reasoning level:
