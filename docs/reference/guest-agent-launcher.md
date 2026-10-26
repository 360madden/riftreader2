# Guest agent launcher

The guest control agent now has a small PowerShell launcher in the signed-in
Windows session. It owns one agent, verifies its executable hash, and creates a
fresh run directory for every start. It sends no game input. Existing host
authentication, exact-game identity and control-queue checks still apply.

The installed root is `C:\RIFT_TRANSFER\RiftReader2Control\managed`. A per-user
Startup shortcut runs `Launch-Agent.cmd`; `Install-Startup.cmd` installs that
shortcut and launches it. Both entrypoints verify the launcher script hash.
The one-time migration also used a manually started Windows task with the
existing interactive-user token, without storing another password. It does not
change NAT, firewall settings, shared folders or the game installation.

## Normal use

With the controller and managed agent ready, use the cached guest login:

```powershell
python scripts/guest_agent_launcher.py restart --output artifacts/agent-restart-UNIQUE
python scripts/guest_agent_launcher.py update --release artifacts/next-release.json --output artifacts/agent-update-UNIQUE
```

For an update, stage the new executable under `managed\releases\<release>\`
first. The descriptor contains exactly `release` (a lowercase name) and `sha256`
(the executable's full SHA-256). `prepare_guest_agent.py` creates the initial
bundle, pinned entrypoints and descriptor from a published executable:

```powershell
python scripts/prepare_guest_agent.py --executable PATH-TO-PUBLISHED-EXE --output artifacts/agent-package-UNIQUE
```

The host helper takes an idle control-queue lease. The launcher validates the
replacement before stopping anything. It writes `shutdown.request`, waits for
the agent to disarm and finish cleanup, and checks the matching process identity
in `shutdown-complete.json`. A pending input journal blocks replacement. The
next process must authenticate and write `ready.json` before `current.json` is
switched. Each operation retains its request, result and process/run identities.

No forced termination or automatic rollback is performed. A wrong hash leaves
the existing agent running. An uncertain stop or failed startup is reported as
blocked; inspect the saved result before doing anything further. A client timeout
does not prove failure: retrieve `results\<request-id>.json` before retrying.
The first live update completed after the original client deadline; the bounded
wait was extended, and the repeat completed normally.

The current launcher expects the host to become available within its 30-second
initial readiness window. Startup registration was inspected; a fresh Windows
logon/VM reboot has not been tested. This is separate from the existing full-game
exit/relaunch qualification. Agent updates do not qualify game patch recovery.

## Transfer measurements

```powershell
python scripts/benchmark_guest_transfers.py --skip-http --output artifacts/transfer-benchmark-UNIQUE
```

This measures three copies per direction at 512 KiB and 8 MiB, with random
payloads and SHA-256 round-trip checks. Timings include the real VMware command
and identity-check overhead. Omit `--skip-http` to also attempt the temporary,
guest-restricted HTTP path; it changes no network settings and closes its
listener afterward. HTTP stopwatch timings measure file/network work inside the
guest, so they must not be treated as directly equivalent to command wall time.

See [the live results](../validation/guest-agent-launcher-2026-10-25.md).
