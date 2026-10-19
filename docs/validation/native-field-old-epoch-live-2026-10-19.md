# Live native old-epoch rejection — RIFT-Lab, October 19, 2026

This record closes the two **field-lab Windows native-session** negative
checks that remained untested after the first same-build game restart. It
does not claim a direct live invocation of the public follow-pointer CLI,
game-field semantic qualification, or update survival.

## Source identity and setup

RIFT-Lab remained running throughout. The earlier retained, completed
field-lab capture from the retired game process is:

- Prior report: artifacts/field-discovery/runs/d8d0c66fdb954d6590962e529f3858a3/report.json
- Prior SHA-256: 2D2120DCC8E2986BB284F3401B6EBBB7E49BBC0790E3B4AD1E3A144910B676B9
- Prior game PID/start ticks: 11620 / 639279813293755454.

The current game was a distinct process epoch, PID 8356, start ticks
639279978665141458. Both used executable build SHA-256
7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD.
The existing unmodified guest field-lab executable had SHA-256
114D2ADA540AA5F54357DE9E1C5DCF06AEC7DD98B4DFF2ED7BE3D3DDDC5B2A28.
The live GuestObserver instance was
8a948623-f4ff-4353-a0c1-80522dc312f3. Its observations were fresh,
bound to the current game, and advancing.

The scanner's copied guest-local plan and executable were under
C:\Users\mrkoo\AppData\Local\Temp\rr2epoch8356oct19. The ISO itself was not
rewritten. An earlier negative-test attempt had unintentionally loaded the
original plan, so it did **not** test the old PID. In the new run, the
existing copied plan was found to be read-only (R attribute inherited from
ISO). The original was preserved as plan-prior.json; the read-only attribute
was cleared on that **temporary plan only**, and the modified plan was copied
into place. The command prompt displayed the resulting plan before each
run. No changes were made to the RIFT executable, installed addon, V1
source, or Windows-wide settings.

The field-lab plan used root RVA 0x32E0200 and explicitly disabled its
health scan. Each test retained a raw report and receiver receipt.

## Test A: no longer openable retired PID

Planned old PID/start ticks: **11620 / 639279813293755454**.

- Report: artifacts/field-discovery/runs/6bc134fe956849868682f7fe2d82e37e/report.json
- Raw SHA-256: 851966F50BFB974C0EF0C29F1B9C23BA35D2C6E0FB8E8C600F955C24E079C357
- Raw length: 28,515 bytes; plan SHA-256:
  E4D809F2481B029833407671F6431C3521FA2D3C7DF27773AA2FA39B42E9E920
- Explicit oldEpochRejected: **true**; oldEpochError:
  "OpenProcess failed with Win32 error 87."
- Current PID/start: 8356 / 639279978665141458. Stable root reread,
  fresh typed-Lua sequences 30524 -> 30530, native XYZ within 0.004
  of typed Lua, complete report.

This tests rejection of an unavailable retired PID. Win32 error 87 does
**not** alone establish PID reuse or a mismatched creation timestamp.

## Test B: live current PID with the old creation timestamp

Planned old PID/start ticks: **8356 / 639279813293755454**.
This deliberately requests a live process ID with the incorrect,
previous-epoch creation timestamp.

- Report: artifacts/field-discovery/runs/8ef7aeb23a424803afb1f76416d46cdf/report.json
- Raw SHA-256: 7DD28B1C367E54548369F2183A2992616DB86B950607DC3DA87F55E43A293B11
- Raw length: 28,511 bytes; plan SHA-256:
  DA6F57320C0BCA55FFA6590C23AD9917AF714A1A5980AD86B0D60FAC08158434
- Explicit oldEpochRejected: **true**; oldEpochError:
  "The process start identity does not match the capture request."
- Current PID/start: 8356 / 639279978665141458. Stable root reread,
  fresh typed-Lua sequences 31024 -> 31030, native XYZ within 0.004
  of typed Lua, complete report.

This is the stronger creation-time negative check: the PID exists, but
opening it with the prior creation ticks is rejected.

Both reports record the exact planned old identity, prior build, and current
game identity. Neither promotes the native XYZ candidate into a durable
field definition.

## Deterministic offline recheck

Run from C:\work\riftreader2, substituting the prior and each probe path:

    python scripts/native-field-evidence.py --verify-old-epoch --prior-report artifacts/field-discovery/runs/d8d0c66fdb954d6590962e529f3858a3/report.json --report artifacts/field-discovery/runs/6bc134fe956849868682f7fe2d82e37e/report.json --root-rva 0x32E0200 --output artifacts/field-discovery/old-epoch-retired-pid-review-20261019.json

Repeat for the second current-PID probe, using the separate
old-epoch-stale-start-review-20261019.json output name. The reviewer
validates exact report hashes, stable pointer-root rereads, fresh Lua,
matching player/build, distinct PID/start epochs, the prior start and
planned PID, and the explicit rejection reason. It does not write to
RIFT or to the original raw reports.

- Retired-PID review SHA-256:
  8A4748EBA53E9029BE30DA66AD0B52743D8429447449929F10279AF0D9995614
- Wrong-start review SHA-256:
  BAB5D851031108639B995E970555276A17E8A07FF832AFE2EFFF69AD6BB3D341

Both deterministic review outputs explicitly retain candidate-only field
qualification and unassessed game-update survival.

## Validation gate

The new portable old-epoch reviewer passed **20 focused regression tests**,
including missing/replaced identities, mismatched builds, unstable roots,
stale Lua references, conflicting rejection reasons, malformed plans, and
atomic no-overwrite output. The updated full PowerShell 7 validation gate
(job rr2_old_epoch_real_full_validation_20261019_46) passed with exit code
0: **242 C# tests, 93 Python tests**, 108 Lua assertions, 22 actual
Lua-to-C# shared cases, locked restore, a zero-warning .NET 10 Release
build, published native synthetic smoke, deterministic replay, format checks
and 220 relative documentation links. Ignored local gate evidence:
`artifacts/validation/20261019T134827Z-2978d1a9`.

## Cleanup and next work

The temporary guest plan was restored from plan-prior.json; its displayed
JSON again contains healthScan true without oldPid or oldStartTicks. Only
the test command prompt and project temporary Explorer window were closed.
At 13:36:44 UTC the live receiver observed foreground RIFT, current PID
8356, the unchanged current process start, and fresh typed observations.

A separate host-side [pointer-follow regression](native-pointer-epoch-regression-2026-10-19.md)
already tests the actual public command with synthetic and disposable Windows
process identities. The two new live tests exercise the underlying Windows
native-memory session through the existing field-lab executable, **not**
a direct live follow-pointer command. These findings complement, but do not
replace, that command-level evidence.

Next: distinguish current health versus maximum and raw resources using
genuinely changed-state typed Lua references and targeted read-only captures.
The repeated static health-marker structures are candidates and cannot be
qualified from unchanged values alone. Preserve the parallel movement-control
roadmap and its exclusive VM-input ownership.
