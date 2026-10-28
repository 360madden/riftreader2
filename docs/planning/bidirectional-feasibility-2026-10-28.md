# Bidirectional feasibility and first two-lab increment

Assessed October 28, 2026 (America/New_York). Scope follows the
[accepted roadmap](bidirectional-hybrid-two-lab-roadmap.md). This is an
implementation/evidence checkpoint, not completion of phases 1 through 8.

## Fresh baseline and assignments

| Lab | Fresh evidence | Initial assignment and limit |
| --- | --- | --- |
| RIFT-Lab-1 | VMX `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`; monitor port 5905 belongs to VMware PID 60472, log epoch `2026-10-28T23:38:26.950Z`. Two cached-login VMware Tools process-list requests timed out. The old host controller endpoint refused connection. A corrected read-only console capture at about 19:50 ET shows Atank, level 45, in Sanguine Shores. | Intended discovery lab; authenticated guest discovery blocked. Current RIFT PID/start/build, addon runtime version and exact unit ID are **unavailable**. Console capture works using the repository control Python runtime. Do not reuse historical game addresses or assume human/controller ownership. |
| RIFT-Lab-2 | At 23:42 UTC, VMX `C:\rift modding\VMs\RIFT-Lab-2\RIFT-Lab.vmx`, monitor 5906, VMware PID 42160/log epoch `2026-10-28T01:23:53.486Z`. RIFT PID 2700, start `2026-10-28T18:05:39.4270240Z`, SHA-256 `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`; two file hashes agreed. | Validation baseline; use as first discovery trial while Lab-1 is blocked. Casting 0.4.0 installed hashes agree with handoff, but loaded Lua version/player identity remain unverified. No guest reader/listener or matching host repository controller/mutex was found. Human ownership still needs confirmation before input. |

Separate raw evidence lives under ignored
`artifacts/bidirectional-20261028/lab1-baseline/`, `lab1-console/` and
`lab2-baseline/`, with successful captures in
`lab1-console-correct-runtime/` and `lab2-console-correct-runtime/`.
Lab-2's screenshot shows Bolinao, level 43, in Sanguine Shores; different
characters are useful comparative evidence, not equivalent unit identities.
Initial capture failures came from using a Python runtime without vncdotool,
not a demonstrated VM console fault. These are dated observations, not permanent endpoint settings.
Lab-2's executable file hash does not establish loaded module byte identity.

## Reuse and transport feasibility

- Keep the existing RR2A1 API observation and nonce-bound RR2L1 envelope.
  Their producer/decoder, strict bounds and read-only acquisition are reusable.
  Earlier live success is scoped to its recorded process/build; current-process
  advancement must be observed again.
- Use current API XYZ as the calculation reference. Lab-2's prior post-patch
  typed API recovery is useful locating evidence, not a current observation.
  Historical native XYZ/Power profiles are incompatible with this changed build;
  patch recovery remains deferred.
- Reuse `GuestSession` for authenticated file/query operations, VM identity
  helpers, no-overwrite reports, Lua 5.1 tests and the existing .NET CLI.
- A bounded slash handler is the smallest return-channel candidate. The external
  app generates an exact result command; an operator types/pastes it into RIFT.
  This is manual information transfer, not an automatic external input service.
- Retained client documentation exposes addon messaging, but messages travel
  through RIFT player/addon contexts. No external ingress endpoint was proved.
  The captured API index predates the October 27 patch. Its messaging/clipboard
  capabilities require fresh runtime verification before use.
- SavedVariables are persisted evidence. File edits plus reload are installation,
  not live feedback. No arbitrary file/network/clipboard-read facility was
  established. Memory writing/injection and arbitrary Lua execution are excluded.

## First mechanism and concrete demonstration

The prepared manual guidance slice uses `/rr2guide bind lab1|lab2 NONCE` to
bind both the existing live publication and the guidance receiver to one addon
load. The reader's current `latest.json` goes to `guide-addon --snapshot`;
an explicit offline `--frame` mode also accepts raw RR2L1. It calculates planar X/Z
distance, signed X/Y/Z deltas and coordinate-axis bearing. The returned
`/rr2guide result ...` command carries lab/nonce, result/source counters,
source clock/player and source coordinates. See the
[manual guidance protocol and procedure](../reference/addon-guidance.md).

The addon displays external distance/deltas, source age and manual-delivery
status. It rejects malformed/cross-lab/session/expired/duplicate results, requires
advancing source observations, and invalidates results after displacement over
0.5 on any coordinate axis or source age over 10 seconds. These are configurable
future choices only after measured need; the first slice fixes them explicitly.
Neither component sends movement or ability actions. Bearing describes axes,
not player facing, camera direction, cardinal direction or line of sight.

Live acceptance requires:

1. Confirm exclusive ownership for the named lab and reacquire exact game and
   player/session identity. Install hash-checked files and load the addon through
   an authorized manual reload. Preserve Casting's baseline.
2. Bind a new random reader nonce and inspect advancing current-process API
   observations. Capture a harmless external result for a fixed nearby point;
   deliver it manually while within the source deadline.
3. Record the intended lab's displayed values, acceptance/source-to-receipt age
   and eventual unavailable display. This age includes acquisition, computation,
   transfer and human delay; it is not a pure network-latency measurement.
4. Reject wrong lab/nonce, replay, expired input and reload-old-session input;
   check external silence and current-source failure. Keep receipt and screenshot
   evidence separate from source/unit/counter provenance.
5. Repeat at two manual movement checkpoints, then independently reproduce on
   the other lab. Only then advance to ordered destinations. Stale coordinates
   must never advance a route or imply arrival.

## Coordination and dependency gates

Root owns shared contracts, main addon wiring, CLI dispatch, integration and
tracked docs. The calculator worker owns its new .NET files/tests. A Lua-test
worker owns the new guidance test module; a separate reviewer inspects the
combined result. Lab-2's inventory worker owns only its raw-evidence directory.
No worker acquires input control. Each lab needs a distinct binding nonce,
receipt directory and any future endpoint; no shared controller or absolute
memory address is transferred between labs.

Run one bounded memory acquisition at a time on this host. Offline math/tests
and read-only inventory may run alongside it. Controller startup/reconfiguration
is not a prerequisite for the manual channel. All game input still requires the
existing fresh-identity, sole-controller, review/arm/release protections or a
physical operator; direct ChatGPT Computer Use remains deferred.

Lab-2's active addon inventory also verified core RiftReader2 0.1.0 (five
installed files, no guidance module), ReaderBridge 0.3.2, and existing read-only
reader/observer executables. Its RIFT_API_Docs OneDrive documents are metadata
only: content hashes fail because the guest cloud-file provider is not running.
Do not treat them as a new current-client API capture.

Missing dependencies: Lab-1 guest access; current player/runtime source evidence
in both labs; live reload/command delivery with confirmed human ownership;
measured transfer age; manual movement and independent second-lab reproduction.
Camera research, projection, overlay and coordinated actions depend on later
evidence. No gameplay-input expansion or patch-recovery resumption is assumed.
