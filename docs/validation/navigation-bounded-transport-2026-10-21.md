# NAV-SCHED-02C — Bounded authenticated-session transport

Date: 2026-10-21 (America/New_York). Implemented and qualified offline; no live
host restart, new listener, guest deployment, ARM or game input.

## Reproduced gap and delivered behavior

The old AgentSession used blocking sendall while holding its send/control locks.
A disposable Windows loopback TCP peer that stopped reading held that path past
the test deadline. The original failing assertion is retained in
`navsched02c-send-red-20261021-01`; cleanup closed the disposable sockets and
joined the test threads. This is a controlled reproduction, not a claim of a
spontaneous incident in the live game.

Authenticated sessions now use a single fixed nonblocking socket mode. A frame
is written in bounded chunks with one **two-second monotonic send budget**;
partial progress does not reset the budget. Send-lock acquisition also has a
two-second timeout. The existing separate eight-second response wait remains.
The initial handshake retains its existing timeout through the welcome write.

A send timeout, zero-progress write, socket failure or uncertain partial frame
closes that session and fails its pending local requests. The error explicitly
states delivery is uncertain and no retry occurred. The host never appends STOP
or a new command into an incomplete frame and never replays a frame under a new
identity. A successful socket write alone is not an acknowledgment or game result.

The single receiver uses readiness polling and bounded buffering instead of a
blocking file wrapper. It retains fragmented/coalesced frames and the existing
16 MiB framing, JSON, envelope and request-ID checks. Closing an idle or partial
receive can settle the owned reader without waiting for a new incoming byte.
There are no per-request socket-mode changes racing the reader.

The queue fence still covers the admitted frame send, not the reply wait. The
control lock preserves the sequence/generation boundary during that bounded send.
STOP/release can therefore wait behind an admitted frame; if that frame cannot
finish, the session closes rather than falsely claiming STOP was delivered. The
watchdog retains the blocked resource after that uncertainty. This does not
promise to deliver STOP over a broken connection or interrupt an OS that itself
has stopped scheduling normally.

## Verification

Focused acceptance passed **195/195**, including **32 new transport tests** and
163 prior watchdog/queue/control checks. The new cases use real disposable TCP
sockets, small send/receive buffers and narrow fault wrappers. They cover actual
backpressure, the production two-second deadline, STOP behind a stalled send,
partial/zero writes, progress without deadline extension, send-lock contention,
external close, pending waiters, exact/oversized frames, malformed/fragmented/
coalesced input, concurrent framing, invalid outbound values, and watchdog cleanup
remaining blocked. Shorter test-specific deadlines accelerate some cases; the
production default is exercised separately.

The full isolated gate passed **364 C# tests, 316 Python tests, 108 Lua checks and
22 shared Lua/C# cases**, with zero-warning Release, locked restore, formatting,
synthetic native smoke, deterministic replay and 278 links before the final docs.
Job: `navsched02c-full-gate-20261021-01`. Generated candidate evidence:
`artifacts/validation/20261021T202017Z-7e58220f`.

The focused tests are included in the full Python count. Three additional runs
passed all **96/96 executions** of the same 32 transport tests; inspect
`transport-repeat-result.json`. These are repetitions, not extra unique tests. Final main-checkout regression,
link checks, preservation and live read-only status are recorded separately in
`milestone-complete.json` under `artifacts/navsched02c-20261021-01/evidence/`.

## Boundaries and next integration

The limits govern transport progress and send-lock waiting. They are not a single
end-to-end deadline covering queue/database access, encoding, evidence storage,
VM identity checks or arbitrary external locks. They are not hard real-time
scheduling guarantees. An unavailable network, failed release or missing durable
evidence remains uncertainty; the resource must not be offered to another owner.

This increment does not enable the admission policy or watchdog on the currently
running host. The next step is fresh trusted startup identity/authority binding
and policy/watchdog lifecycle composition, followed by manual panel/CLI and
VM-console/bootstrap/legacy ownership participation. Reviewed activation and a
bounded live trial still need current screenshots and independent observation.
The unchanged live host is not retrospectively protected by these source edits.

No package, C# runtime, lockfile, global setting, Workbridge configuration or
unrelated project is changed. Inherited uncommitted work and the main Git index
are preserved. Diff review is by the implementing assistant, not an independent
reviewer or AI worker. No commit or push is created.

## Developer reproduction and references

From the repository root:

```powershell
python -m unittest tests.test_control_transport tests.test_nav_control_watchdog tests.test_nav_gateway_fence tests.test_nav_access_queue tests.test_control_host tests.test_control_client tests.test_vm_console_native -v
```

The transport tests are included in `scripts/validate.ps1`. Python's documented
[socket modes and file-wrapper limitations](https://docs.python.org/3.14/library/socket.html)
and [Windows socket readiness support](https://docs.python.org/3.14/library/select.html)
were checked on 2026-10-21. Those API documents are design references, not substitutes
for the Windows test results.

Resume from [current status](../status.md) and the
[access roadmap](../planning/navigation-access-queue.md). The
[watchdog report](navigation-watchdog-cleanup-2026-10-21.md) remains historical evidence.

Model: GPT-6 Astra Pro. Reasoning level:
