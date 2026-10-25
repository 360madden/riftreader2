# Position window: full game restart and startup issue, October 25

The new Start / Read / Stop window was installed and exercised in RIFT-Lab-1.
One normal complete game exit and relaunch established automatic same-build
process/owner reacquisition. **Acceptance remains open:** the retained journal
also exposed a startup display defect. Corrective work and a new live trial are
required before calling the window fully validated. Patch recovery stays deferred.

## Installed build and actual UI behavior

Production implementation: `8a9f894`. The final host gate passed 465 .NET,
669 Python, 108 Lua and 22 Lua/C# cases, with zero-warning build, publish smoke,
replay, formatting and 547 documentation links. This gate preceded the live trial.

Read-only media `RR2_XYZ_UI` was observed in guest File Explorer after Joey
manually selected the ISO using VMware's Browse button. ValidationCourier
verified the reader/profile hashes before creating a new installation at
`C:\RIFT_TRANSFER\RR2-XYZ-Interface-oct25-01\` at **14:01:39 UTC**.

| Payload | Bytes | SHA-256 |
| --- | ---: | --- |
| Reader | 116,924,768 | `E1E6A5FB4D3C82F91DCBF8BD5FD8395A42A03FA1766380E12614B4A077C7D647` |
| Profile | 395 | `FFA948C24170070F7A0E7A986273BEF7E0774D953DFEA4ECABB14112FCCF88C8` |
| Validation-only courier | 37,888 | `3F7E81E187AD4A34C9ACA6C07EF9E800BC4CAA07403DA4DB1397A9506E1B97DD` |

The courier ran from the read-only disc and was not copied into the installation.
It invoked fixed existing read-only CLI commands and retained their originals.
Guarded VM-console clicks/keys were explicitly authorized; no guest terminal,
debugger, process-memory write or gameplay automation was used.

Actual buttons and screenshots established Read while stopped, monitoring Start,
Stop clearing XYZ, and subsequent Start. RIFT exited through **Exit Game** and
its normal countdown. The still-running window displayed **Waiting for RIFT**,
no current game identity and no XYZ. The courier independently proved zero RIFT
processes and sampler exit 2 without a report. Normal Glyph Play and Atank's Play
returned to the world. The same panel process, **6944**, automatically displayed
the new game identity without another Start action. After relaunch, Stop cleared
the display, Read worked independently, and its result expired. Normal close
returned exit 0 at **14:09:04 UTC**.

## Exact restart and original-byte verification

| Identity | Before | After |
| --- | --- | --- |
| Game PID | 9704 | 11712 |
| Process start UTC ticks | 639285237698112372 | 639285339497136209 |
| Session-local owner | `0x1D610AC0010` | `0x1C233730010` |

Both epochs use game SHA
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.
The locating recipe remained RVA `0x32E0200`, one dereference, float32 offsets
`+0x320/+0x324/+0x328`. Both independent sampler runs completed **3/3** reads.
The independently acquired 816-byte owner reports agreed exactly at float32
byte level: XYZ **(7460.6298828125, 863.8043823242188, 2976.61669921875)**.
The old process request after relaunch returned exit 2 and published no report.

The original guest ZIP is **385,136 bytes**, SHA
`C3B3A1B95160D3B92DB6EF1B33B1B27CBEF8EAB5C71DB26BB979062970F2E82C`.
Separate fixed-peer one-use declaration/upload services checked the exact epoch,
reader SHA, archive bytes and SHA. Actual independent Windows session-2
`pythonw.exe` owners were claim PID **54140** and upload PID **68264**, both
`inJob=false`, then exited normally. Port 8765 was verified closed afterward.
Windows WMI/CIM process creation provided the successful independent launches.
A temporary Scheduler attempt inherited a job, failed the unchanged service
guard and opened no listener; its task registration was removed. The failed
probe and removal receipt are retained. No Scheduler task remains for this trial.

Offline verification safely extracted **260 files** into a new directory and
verified all **259** manifest-declared original lengths and hashes. The remaining
file is the manifest itself. All **226** report references and hashes in the
**868-event** panel journal verified. Originals are never rewritten.

## Startup defect found in the journal

The panel recorded **83 old-process reports**, then **87 unavailable states**
that cleared identity/XYZ, followed by **143 new-process reports** in the same
monitoring run. The first new-process report at **14:05:51 UTC** occurred with
zero intervening Start actions.

However, **48** new-process reports (`read-00171.json` through `read-00218.json`)
were labeled live while XYZ contained finite subnormal initialization values:
approximately `(9.918325e-39, 1.63e-43, 4.2245e-39)`. Finite numeric values and a
fresh exact process identity did not establish that the coordinate structure was
ready. The first correct coordinate report was `read-00219.json` at
**14:06:43 UTC**, followed by **94 stable correct reports** through the final read.

The corrective scope is to withhold these observed subnormal values in the
panel, preserve raw acquisition reports unchanged, and test later recovery
without another Start. This numerical guard is not general proof of world-entry
readiness. A fresh deployment and full restart trial are still required.

## Evidence and remaining work

Ignored working evidence:
`artifacts/update-recovery-20261023-01/xyz-interface-restart-oct25-01/`.
It contains `restart.zip`, claim/upload receipts, `verified-originals/`, guarded
action screenshots/receipts, deployment/media pins and `offline-verification.json`.
Verification record SHA:
`5ECDF06B8C5E23F6E090A93B2478F95DB8743E18EC58A180886832AC413F8382`.

V20 remains normally exited and V21 prepared but unstarted; the canonical queue
is quarantined for this maintenance. Original media restoration is not yet
verified: guest File Explorer still showed `RR2_XYZ_UI` during the recheck.
Complete the correction, new live trial, media cleanup and sole-supervisor
recovery before final acceptance. Refresh ownership on every resume.

This stationary UI restart trial adds no new Lua observation or movement
comparison. Prior sampler evidence remains separately documented. One observed
same-build restart does not establish unlimited reliability, host/VM restart
durability, field-catalog promotion or patch recovery.
