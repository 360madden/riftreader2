# Native typed-prefix scout guest-transfer readiness — October 24, 2026

Scope: **host-side, read-only preparations only**. This is not evidence that the new binary was downloaded into RIFT-Lab-1 or that any RIFT process memory was scanned. The [scout contract](../reference/typed-prefix-scout.md) and [Windows-host tests](typed-prefix-scout-host-validation-2026-10-24.md) are separate evidence.

## Reuse-first transport decision

- Existing `scripts/serve_guest_receiver_bundle.py` and `artifacts/receiver-milestones-20261022-01/transfer_server_pythonw.py` both deliberately cap the older receiver ZIP at **65,536 bytes**. Reusing them for a **74,209,699-byte** native scout would violate their tested scope. The previous [guest map POST receiver](guest-map-report-transfer-2026-10-24.md) transfers *guest-to-host* reports, not a host executable.
- Added **`scripts/serve_guest_native_scout.py`**, a separate single-purpose, streaming 64 KiB-chunk HTTP GET handoff. It reuses Python's standard `HTTPServer` and the already established host-only VMware VMnet8 address **192.168.56.1:8765**. The only permitted client is **192.168.56.128**; the only route is `/rr2-scout-oct24-01.exe`; only one successfully streamed, hash-verified GET is accepted.
- Source is pinned to ignored `artifacts/validation/rr2-scout-publish-20261024-01/RiftReader2.Live.exe`: **74,209,699 bytes**, SHA-256 **`C34D1C9BC5EC134D50AE38FBE6A16D13B0DBAC9EC412D9C4F4714E3DDFD9876C`**. Before listening the full source is hashed through a held-open read-only file handle. The streamed bytes are hashed again; wrong/missing bytes, wrong source, wrong route and unsupported methods cannot count as delivery. No executable memory-sized buffer or arbitrary file router is created.
- Live `--serve` requires installed Windows **`pythonw.exe`**; it does not open firewall rules, bind public addresses, send guest commands or manipulate the current coordinator. The server has a maximum 600-second life and records a fresh ignored `transfer-events/<uuid>.json` receipt. This receipt only proves successful **host write**, never guest file verification or execution. Guest must independently check the SHA-256 and length.
- A plain Python invocation **without `--serve`** is a safe, no-listener preflight. It passed on the actual Windows host with the pinned SHA and size, returning `verified-not-serving`.

## Validation and live preflight

- Focused `python -m unittest -v tests.test_serve_guest_native_scout`: **10/10 passed**, including the entire real 74 MB bundle fingerprint, >64 KiB streaming, exact peer/path gating, HEAD not consuming a download, unsupported methods, mismatched digest, declared-length truncation and deadline rejection.
- The same-VM-epoch **V13 successor plan** was prepared with the existing `scripts.prepare_native_host_handover --previous v12 --successor v13 --same-epoch`. Output was `handover-prepared-not-executed`, `queueStatePreserved=true`, `queueBlockedAtPreparation=false`, `shutdownMarkerNotCreated=true`, `guestInputSent=false`, VMX PID **38044**, log epoch **2026-10-24T05:41:51.833Z**.
- V12 remains the current console owner. Its authenticated coordination was most recently read **connected/ready**, supervisor running/cleanup verified, guest PID **6940** foreground and disarmed/idle. Read-only SQLite snapshot reported an unheld resource, **zero** pending requests and a cleanup receipt. Neither V12 nor the guest was stopped or controlled by the host-only transfer development.
- A complete test is **not** equivalent to reaching the guest VMnet8 address. No listener has been started, the guest has not downloaded the file, and no current `RRAPIVAL2|` prefix has been found.

## Controlled next acceptance

1. Recheck VM/process exact identities, guest readiness, canonical queue and V12 owner. Keep the existing V13 plan only if its pinned same-epoch assumptions still hold.
2. Request legitimate V12 normal STOP; require exit receipt, disappeared owner process, closed ports and **blocked=1 / unheld / zero pending** queue. Never connect VNC around a held console mutex or unquarantine by hand.
3. Start this one-use server through an independent signed-in normal-user `pythonw.exe` launch; verify its receipt/listener. Open guest PowerShell under the repository's exclusive VNC mutex. Download only the exact route to a new file in `$env:TEMP`; verify the guest's full executable SHA-256 and byte count.
4. Recheck guest game PID/start/build, generate a matching `native-typed-prefix-scout-request/1`, execute one bounded 512 MiB / 30 s read-only pass, and retain both guest report and its full SHA-256. A partial pass is expected to need more windows; never turn zero local matches into a global absence claim.
5. Hash-pin and transfer the report over the already tested one-use guest-to-host POST receiver, without overwriting old evidence. Close the guest PowerShell, verify return to Rift, then launch pinned V13 only after fresh preflight; require authenticated `connected/ready`, disarmed/idle, supervisor running/cleanup verified and authority no longer blocked.

All guest and coordinator actions in this list remain **pending**, not completed by this checkpoint.
