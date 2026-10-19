# Guarded experiment validation

Date: 2026-10-19. Retained evidence: `artifacts/experiment-validation/`.
The unchanged V1 console/readback tools were reused operationally; their
source was not changed. No new framework or executable was deployed.

RIFT-Lab VM process 54820, start FILETIME ticks `134368524235244532`, log epoch
`2026-10-19T03:00:23.557Z`; RIFT PID 11620, process start
`2026-10-19T04:35:29.3755454Z`, window `0x80400`, guest DESKTOP-8632QPL.
Game path `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, disk SHA-256
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
Character Atank was mounted on a clear bridge in Sanctum. The fresh screenshot
showed the game foreground with chat input closed.

Run `d69f430dc328422a8c077a7650c32029` completed a requested 100 ms `w` pulse.
Recorded hold was 100.7346 ms; key-down and key-up were both sent, guest focus
was retained, and all VM/game identity checks matched. A newer independent
ReaderBridge observation advanced scan 195 → 197 and source clock
2432.442 → 2438.814. Coordinates changed from
`(7298.369629, 876.25, 3054.199951)` to
`(7297.359863, 876.289978, 3054.290039)`.

The post-sample began acquisition at `05:16:08.570224Z`, after recorded key-up
at `05:16:08.333812Z`, subject to unmeasured host/guest clock skew. This verifies
delivery and a subsequent API observation, not calibrated movement speed,
causality, native field meaning, or game key-state attestation.

The actual lab adapter also rejected a changed expected game PID before input,
rejected reuse of the completed run directory, and cancelled a freshly prepared
plan after `stop`, with no pulse. `recover` reported no pending input and left
the controller paused. Failure/cancellation during a pulse, keyboard interrupt,
identity drift, uncertain delivery, and release failure have focused fake-adapter
tests. Mid-hold external stop and hard crash recovery were not exercised live.

A subsequent adapter fix retries transient unavailable post-release readback
within the existing 12-second budget. Its focused tests pass; the successful
live trial above used the preceding adapter revision (retained source hashes
identify it). The fixed path does not change successful pulse delivery.

See [usage and limits](../reference/guarded-experiments.md) and
[current status](../status.md) for the final combined validation gate.
