# Live addon preparation: waiting for RIFT

Date: 2026-10-18 (America/New_York).

Status: historical host-only preparation. The later
[actual-client addon record](addon-live-client-2026-10-18.md) supersedes its
waiting state and documents the successful guest RIFT-Lab gate. The four files
and matching hashes below describe the separate host installation; they are not
guest-deployment evidence.

Joey authorized actual-client validation, then a minimal live transport with
reliable freshness and reload/session identity. He requested a prompt if RIFT
needs launching. This supersedes the earlier offline-only scope for this task.

## Completed and verified

- The starting repository was clean at `bcb8f44`.
- No `rift_x64` or `rift` process was present on the host in two checks.
  VMware service/tray processes were present, but no running VM process was
  observed. This is host process evidence, not a guest inspection.
- The host executable exists at
  `C:\Program Files (x86)\Glyph\Games\RIFT\Live\rift_x64.exe` (59,963,840 bytes).
  Executable identity has not yet been bound to a running process.
- Created only the new host addon directory
  `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\AddOns\RiftReader2` and copied
  `RiftAddon.toc`, `wire.lua`, `producer.lua`, and `main.lua` from V2. All four
  installed SHA-256 hashes matched their sources. Other addons were unchanged.
- Installation receipt:
  `artifacts/live-validation/20261019T014815Z/installation.json`.
- Asked Joey to launch RIFT, log into a character, keep it visible, and identify
  host versus RIFT-Lab. No answer or running game was observed before handoff.

Installation is not evidence that RIFT loaded or executed the addon. No live
frame, reload, restart, freshness, or transport test passed in this preparation.
No transport code was built ahead of the requested actual-client gate.

## Resume without repeating discovery

1. Verify the running location. If it is the VM, host installation does not
   establish guest deployment. Verify the intended target before proceeding.
2. Confirm RiftReader2 is enabled. Record process creation identity, executable
   hash/build, addon version and installed file hashes. Observe actual API
   availability and at least two advancing complete frames.
3. Verify UI reload behavior and source-load identity before selecting a live
   contract. Keep v1 decoding unbound; a new identity envelope requires its own
   version and shared fixtures.
4. Implement the smallest verified adapter and a separate freshness state
   machine. Use receiver monotonic timing, invalidate on process/load change,
   reject replay/conflicts/regression/expiry, and require independent advancement.
   Validate disappearance, reload, and process restart separately.

## Read-only evidence and unresolved choice

V1 `docs/workflow/typed-acquisition-three-roadmaps.md` describes bounded
read-only memory acquisition and live reload evidence. Its generation is
observer-inferred and depends on a continuing frame clock; it is not a proven
globally unique addon-load ID. Typed relaunch/power-cycle qualification remained
open in that record. Do not inherit stronger claims or application architecture.

The local RIFT API documentation under the installed `RIFT_API_Docs` addon
describes `Inspect.Time.Frame` as frame game time and `Inspect.Time.Real` as a
different high-resolution time space. Neither API documents load identity.
`Command.Console.Display` documents console output, not a file transport;
`Command.Storage.Set` is game player/guild storage, not arbitrary filesystem I/O.

A bounded read-only scanner is a candidate technique. Selecting a current value
among old heap strings and establishing reload identity remain explicit design
questions. Load-start time/counters are candidate discriminators, not accepted
identity proof. A live adapter must withhold verified freshness until its
source-generation and current-value assumptions are established. No debugger,
injection, process writes, or player automation is needed for the proposed scope.
