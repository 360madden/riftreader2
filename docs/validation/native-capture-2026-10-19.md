# Bounded native capture validation

Date: 2026-10-19, America/New_York. This completes roadmap step 4's remaining
raw native acquisition slice. It does not qualify a native game field.

## Implementation and local gate

The [native capture contract](../reference/native-capture.md) adds finite
`inspect-native` and `capture-native` commands to the existing Windows Live
executable. Domain holds values, Application owns sampling and its read-only
session port, Infrastructure owns strict JSON, and Live owns Win32 access.
The addon transport remains a separate source and the no-argument entry point.

`pwsh -NoProfile -File scripts/validate.ps1` passed on the final code:

- 196 C# tests: 187 portable and 9 Windows;
- 108 Lua assertions, 22 actual Lua-to-C# cases, and 9 Python host-gate tests;
- locked restore, zero-warning Release build, dependency and format checks,
  deterministic replay, and 158 relative links before the final documentation;
- a published single-file executable smoke against a synthetic host process:
  exact bundle hash, PE header read, stale-epoch rejection, and no overwrite.

Evidence: `artifacts/validation/20261019T043104Z-a6f572d3` and
`artifacts/native-validation/final-gate.log`. Focused tests include checked
address arithmetic, strict requests, failure/partial results, deadlines,
cancellation, same-handle process exit invalidation, and preservation of output.
All 160 final documentation links passed separately. Independent static review
covered native rights, identity, enumeration errors, terminal validation,
bounds, module ownership, and the final packaging fix.

The first live attempt exposed a packaging defect: assembly locations are empty
in a single-file deployment, so inspection correctly failed without a report.
The final code explicitly identifies either assembly files or the actual bundle
executable. It does not enable compatibility extraction or fabricate assembly
hashes. See Microsoft's [single-file guidance](https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/).
The published smoke is now mandatory in the local gate.

## Exact runtime identity

Final `RiftReader2.Live.exe`: 73,868,707 bytes, SHA-256
`7D095CCBB8826ACC62F6C788158F278DBF1ED77CE64157272D7D338C11EA6C52`.
The guest harness hashed the actual DVD executable; each capture report's
bundle hash matched. ISO contents were byte-compared with their source files.

RIFT-Lab VM: `C:\rift modding\VMs\RIFT-Lab\RIFT-Lab.vmx`.
Host VMware UI PID 42556; VM process PID 54820, start FILETIME ticks
`134368524235244532`, VM log epoch `2026-10-19T03:00:23.557Z`.
The VM identity remained unchanged through this gate. Character Atank was
logged into Sanctum; no movement or gameplay actions were sent.

Guest executable: `C:\RIFT_TRANSFER\RIFT\rift_x64.exe`, disk SHA-256
`7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`.

| Identity | Before RIFT restart | After RIFT restart |
|---|---|---|
| PID | 11884 | 11620 |
| Process start UTC ticks | 639279786867411885 | 639279813293755454 |
| Main module base | `0x7FF6B6EE0000` | `0x7FF6B6EE0000` |
| Main module size | 62,611,456 bytes | 62,611,456 bytes |
| Host receipt UTC | 04:34:19.443969Z | 04:36:44.788455Z |

The unchanged address is not evidence of an unchanged process. The request
must bind PID, creation time, and executable hash.

## Actual-client checks

Each session ran the production commands headlessly from an ignored lab-only
GUI harness. Two header captures each requested three 512-byte reads at RVA
zero, 200 ms apart, within a 10-second budget. Both sessions also ran a mixed
header/unmapped-address capture, wrong epoch, wrong build, and overwrite checks.

| Check | Observed result in both sessions |
|---|---|
| Inspection | Exit 0, exact process/build/mapping identity retained. |
| Header and repeat | Exit 0; 3/3 successful samples each; distinct capture UUIDs. |
| Unmapped 16-byte range at `0x7FFFFFFFF000` | Exit 3; partial capture; header retained; failed range unavailable, zero bytes, Win32 998. |
| Wrong creation time | Exit 2; no report published. |
| Wrong executable hash | Exit 2; no report published. |
| Existing output | Exit 2; original file hash unchanged. |
| Original request after actual restart | Exit 2, OpenProcess error 87; no report published. |

The restart used the normal RIFT window close, Glyph Play, and the existing
character's Play button. The second harness run loaded the exact pre-restart
request from its retained guest directory. The verifier compared that request
with the first receipt, checked the changed process epoch, and confirmed fresh
captures against the new request. This proves explicit reacquisition after one
ordinary game restart. It does not prove PID-reuse behavior in the live game;
wrong-epoch rejection is additionally covered by tests and the live mutation.

Every transferred report was reconstructed from its exact file bytes and
checked against its file SHA-256. Every returned byte array matched its count
and SHA-256. The 512-byte memory header matched the disk header except the
eight-byte PE32+ ImageBase field at offset 440: disk preferred base
`0x140000000`, observed memory value `0x7FF6B6EE0000`, equal to mapping metadata.
No other header byte differed. Field location follows Microsoft's
[PE format specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format).
This is a measured difference, not a claim that the complete loaded image
matches disk or that all builds behave this way.

| Report | Before: bytes / elapsed ms | After: bytes / elapsed ms |
|---|---|---|
| Header | 7,227 / 488.4021 | 7,227 / 530.3001 |
| Unreadable | 4,878 / 68.8478 | 4,878 / 70.7895 |
| Header repeat | 7,226 / 496.1138 | 7,227 / 492.9988 |

These times cover sampling and terminal revalidation, including configured
delays. They exclude initial attachment, first executable hash, publication,
and network transfer; they are not a throughput benchmark.

## Retained evidence and tool reuse

Everything below is under ignored `artifacts/native-validation/`:

- `before-restart/` and `after-restart/`: receipt, acceptance check, three exact
  report files, and VM identity;
- `restart-check.json`: request equality, old-request rejection, new epoch,
  unchanged build/bundle, and stable VM identity;
- `check-live.py`: receipt, exact bytes, hashes, header comparison, status,
  sample-count, bundle identity, and no-overwrite verifier;
- `media-receipt.json`, `harness/`, `receiver/`, `rift-exited.png`,
  `rift-restarted.png`, and `final-rift.png` retain lab provenance.

Before-restart receipt SHA-256:
`12E886D0122D5180B07D6A556DA00F7FC4ABA469B7FD605AAC99533473049E00`.
After-restart receipt SHA-256:
`540A27058B2F1DA7E3EC5E67393A08B41E80DE9D50632C5340F944FFFF3C9BF8`.
Guest report directories are recorded inside each receipt under
`Documents\RiftReader2NativeValidation`.

Unchanged V1 tools were used only as lab infrastructure: `lab_vmcli.py` for
DVD backing changes, `lab_console.py` with the VM identity/mutex guard for
console clicks, and `guest_observation_receiver.py` for private-LAN delivery.
Use the existing `C:\rift modding\VMs\RIFT-Lab\controller-env\Scripts\python.exe`.
For future media swaps, VMCLI's `Disk ConnectionControl sata0:1 disconnect`,
`Disk SetBackingInfo sata0:1 cdrom_image <absolute-ISO> false`, and
`Disk ConnectionControl sata0:1 connect` worked; query the disk afterward.
No V1 source or REA installation changed. No debugger or binary analysis tool
was needed for this bounded acquisition task. Credentials remain private and
are not retained in tracked documentation.

At teardown, the owned receiver PID 50624 was stopped after checking its
command line. VMCLI confirmed `sata0:1` connected to the original
`C:\RIFT MODDING\Media\RIFT-TypedObserver-017c.iso`. RIFT was left logged in;
the lab harness exited after each run. `teardown.json` records receiver exit.

## Qualification limits

Raw captures remain `native-memory-semantic-unqualified`. This gate adds no
native coordinate/velocity locator, native-to-addon alignment, durable field
claim, player control, process write, or injection. Reads are sequential;
neither global snapshot atomicity nor cross-machine freshness is established.
Delivery remains `gameReady: false`.

The final native bundle was tested through one ordinary RIFT restart. The
earlier [VM recovery gate](restart-recovery-2026-10-18.md) belongs to the earlier
addon-transport executable; it is not a new VM-restart qualification of this
native bundle. VM restart, snapshot restore, crash, update recovery, and
automatic native reacquisition remain separate gates.
