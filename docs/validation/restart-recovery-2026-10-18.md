# RIFT and VM restart recovery validation

Date: 2026-10-18 (America/New_York; evidence timestamps use 2026-10-19 UTC).
Scope: final published
reader, ordinary RIFT process restart, and a graceful RIFT-Lab VM power cycle
followed by manual relaunch and nonce binding.

## Identified build and path

The deployed final reader was
`artifacts/live-validation/reader-final/RiftReader2.Live.exe`, SHA-256
`42C02CB07886D6108ED84188263E1D1CEB99DBF59D605CABA90BE8AA3A210A08`,
built from commit `2cfbee1`. The seven-file deployment ISO was byte-verified
against its sources. Replacement was observed in the guest, but an independent
guest-file hash was not collected.

RIFT remained at `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`; the reader reported the
same on-disk file SHA-256 before and after both restarts:
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
This identifies the file at the process MainModule path, not the bytes already
loaded in memory. Delivery used the unchanged V1 host receiver instance
`d625e200d3d24efdabe57fdf2517ded6` as lab infrastructure.

Operational tools were reused unchanged: `lab_console.py` and `lab_vmcli.py`
under `C:\rift modding\VMs\RIFT-Lab`, plus `vm_console_windows.py` and
`guest_observation_receiver.py` under
`C:\rift modding\RiftReader\tools\riftreader_workflow`. The console wrapper
reacquired and checked VM identity around each action; its Python runtime was
`C:\rift modding\VMs\RIFT-Lab\controller-env\Scripts\python.exe`.

Before restart, reader instance `f85531ee-669d-454c-9b3e-33868384bdc3`
attached to RIFT PID 9428, start UTC ticks `639279712871697793`, using nonce
`5dc9cda7e3574ce6bb53e4804b9fa560`. Four accepted fresh snapshots advanced
through inner sequences 29, 32, 35, and 38. The nine-sample window also retained
conservative unavailable and warming results rather than exposing an observation.

## RIFT process restart

RIFT was closed and relaunched while the same reader process remained running.
During absence the reader published no observation and the host gate rejected
the old nonce. The replacement process had PID 5572 and start UTC ticks
`639279753523085080`. The reader generated nonce
`c5770df36958483b9d85d43fa7b31ec2`; its unbound output was rejected before the
new local `/rr2bind` command.

After binding, the reader passed through warming and produced 11 consecutive
host-accepted fresh snapshots with inner sequences 107, 109, 112, 114, 117,
120, 122, 125, 127, 130, and 133. The reader instance stayed the same while the
RIFT PID and start time changed, demonstrating process reacquisition rather than
a reader restart.

## Graceful VM power cycle

Windows was shut down gracefully with RIFT and the reader running. The host
then verified `vmrun` reported zero running VMs, old `vmware-vmx` PID 51176 was
absent, and the VNC listener was absent. A retained pre-shutdown receipt was
rejected as stale while the VM was off.

The VM was powered on through the VMware UI because CLI power-on required local
administrator or `__vmware__` group membership. The VM identity changed from
PID 51176, start ticks `134368480287222354`, log epoch
`2026-10-19T01:47:08.781Z`, to PID 54820, start ticks
`134368524235244532`, log epoch `2026-10-19T03:00:23.557Z`. Windows returned to
the desktop; Glyph, RIFT, and the reader were relaunched manually. The addon and
reader executable persisted without reinstall.

The new RIFT process was PID 8808 with start UTC ticks
`639279757602808423`. New reader instance
`45c23acf-2ede-4a4f-b2f8-575ab1f4e5e0` generated nonce
`9d502eebbe6d4ebe97a168a1281fa5d1`. Before rebinding, observations remained
unavailable. After the local bind, the reader warmed and produced nine accepted
fresh snapshots with inner sequences 153, 156, 158, 161, 163, 166, 173, 175,
and 178. One conservative read failure interrupted the run; the reader withheld
the observation, warmed again, and returned to fresh output.

The final retained gate accepted the new nonce and expected receiver with an
effective inner age of 1233.6373 ms under the 5,000 ms freshness limit. Applying
the pre-VM nonce to the same fresh receipt failed with a reader-nonce mismatch.

## Result and limits

The final build passed both restart gates without carrying an old process,
nonce, or observation into the replacement session. Recovery was fail-closed:
absence, unbound state, read failure, and warmup exposed no observation. The
same host receiver accepted the new, explicitly expected nonce only after a
complete selected scan and advancing source evidence.

Host acceptance remains a snapshot gate. It requires a receipt no older than
two seconds and assumes guest and host UTC differ by no more than 250 ms;
delivery remains `gameReady: false`. This record qualifies an ordinary game
restart and one graceful VM power cycle with manual application relaunch and
binding. It does not qualify automatic startup, hard-crash recovery, VM
snapshot restore/resume, game or reader updates, loaded-module bytes, native
fields, or a production remote consumer.

Retained non-secret evidence is under `artifacts/restart-validation/`, including
`vm-before.json`, `vm-powered-off.json`, `vm-after.json`,
`verified-identities.json`, `final-steady-summary.json`,
`game-rebound-summary.json`, `vm-rebound-summary.json`, `vm-final-fresh.json`,
`vm-final-gate.json`, and `vm-old-nonce-rejected.json`. Private delivery
configuration and tokens are excluded from this record. `acceptance-check.json`
records successful cross-checks of distinct epochs/nonces, pre-bind absence,
freshness rejection, final executable hash, and teardown, with hashes of the
retained evidence files. Application sources were unchanged during this gate;
the earlier full repository test results remain applicable. The documentation
check passed 149 relative links, whitespace checks, and a check that all seven
changed files were Markdown; see `documentation-check.json`.

## Teardown

The reader terminated cleanly at outer sequence 100; `final-terminated.json`
records `readerStatus: terminated`. Receiver PID 13652 was absent afterward and
host port 49712 was closed. The original VM DVD,
`C:\RIFT MODDING\Media\RIFT-TypedObserver-017c.iso`, was restored. RIFT remained
logged in; that continuing game state is not continuing reader or receiver
freshness. `teardown.json` retains the non-secret teardown checks.
