# Start / Read / Stop XYZ interface

Authorized by Joey on 2026-10-25: build the interface around the existing XYZ
sampler and validate it through complete game exit and relaunch. Patch recovery
remains deferred under [ADR 0008](../decisions/0008-full-game-restart-durability.md).

**Completed:** [corrected guest full-game restart validation](../validation/position-panel-corrected-restart-2026-10-25.md).
The first trial exposed subnormal initialization values; the corrected build
withheld all 59 observed startup reports and recovered real XYZ automatically.
One corrected-reader same-build restart, original evidence and restored sole
supervision are established. Patch recovery remains deferred.

1. Reuse the existing sampler and exact-build profile. Add a small native Windows
   Forms window to the existing Windows Live executable, using the installed
   .NET 10 Windows desktop SDK/reference pack and self-contained deployment.
   No new project, third-party UI package, service or game-input capability.
2. Start monitors at a bounded cadence for at most ten minutes per activation;
   Read takes one fresh sample; Stop cancels the current read and immediately
   clears displayed values. Only one read can be in flight. Late results after
   Stop cannot repopulate the display. Failed/old reads clear values; age is
   measured monotonically and stale values expire. Each read discovers the
   current game process and resolves the saved pointer recipe afresh.
3. Preserve each completed original sampler report and an append-only panel
   event journal in a new session directory. Keep the native candidate labels,
   process/start/build identity, profile hash, timestamps and failure states.
4. Test lifecycle cancellation, late completion, stale/slow reads, bounded
   monitoring, failures and new-process reacquisition offline. Run the full
   repository gate and a real native-window smoke before deployment.
5. Prepare sole-controller V20-to-V21 recovery before maintenance. Deploy a
   newly pinned executable into a new guest directory. Verify actual buttons,
   normal full RIFT exit, zero-process absence with no current XYZ, normal
   relaunch/world entry, fresh-process coordinates, old-epoch rejection and
   clean Stop. Preserve exact guest evidence and restore sole supervision.

The current host has Microsoft.WindowsDesktop.App 10.0.10 and its reference
pack installed. The guest receives a self-contained bundle, so the interface
does not require installing a desktop runtime there. The existing console
commands retain their contracts and remain independently usable.
