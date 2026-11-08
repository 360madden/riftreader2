# Jimmy RR2 lease, location-context and tracking review — November 7, 2026 (a087)

**Scope:** independent read-only review of the current RR2 XYZ lease/tracking checkpoint. No source-code edits, status/handoff edits, Git commits, guest/VM/game/controller access, input, reload, deployment or new native capture. Main RR2 coordinator retains integration, commit and live-operation ownership. This is a continuation of `docs/xyz-jimmy-findings-2026-11-07-anchor-review-a086.md`.

## Verdict

The new cooperative lease is a meaningful improvement: participating current-build readers and the supervised action path now serialize against one another using a real Windows exclusive file handle. The focused offline tests pass. It is **not yet a fleet-wide exclusion guarantee**, because legacy/generic readers and previously deployed agents do not participate, the ProgramData ACL has not been accepted in either guest, and no new binary has been deployed or verified in a live lab.

The strongest remaining data-quality issue is the location-context pair: XYZ is sampled first, zone context later, but there is no maximum permitted cross-field age and no final XYZ reread after the potentially longer TLS/zone search. The result must remain two sequential candidates, not a single current-location snapshot.

## 1. NativeReadFileLease review

Inspected current source and tests:

| File | SHA-256 |
| --- | --- |
| `src/RiftReader2.Live/NativeReadFileLease.cs` | `F057BB6065304E3A50C8C904C653587BA4636BBA1033C622FF2078F31E603258` |
| `tests/RiftReader2.Live.Tests/NativeReadFileLeaseAdversarialTests.cs` | `DA39481F02F2CF4226371DC377D5B64CC7545A33CB3F37A30C767AFCBCC735A6` |
| `tests/RiftReader2.Live.Tests/ControlActionNativeLeaseTests.cs` | `09CD807C42FF85CD0390A9F4D9A248D6CC706C89C740F710BB997868F29DAFBB` |
| `src/RiftReader2.Live/Control/ControlAgent.cs` | `8763C8B46BCE94D6BEE615177115DF6CDEC7934F7E9FB2A1C3DD880F1B433775` |

**Positive findings**

- The lock identity is keyed by game PID, process-start ticks and exact executable SHA, preventing unrelated process epochs from sharing the same lease key.
- The implementation uses `FileShare.None`, a bounded wait/cancellation path, and leaves the stable lock file in place. A process crash releases the OS handle rather than leaving a permanent logical lock.
- Current-build command wrappers acquire before opening the native session and dispose the session before releasing the lease.
- The supervised action body acquires the same lease after admission, rechecks arm/target state after waiting, and retains the lease through pending-journal creation, input release and journal outcome. STOP/release cancellation of a lease wait and release-before-dispose ordering have focused tests.
- Static search of the current source found **28 CurrentBuild CLI sample-command lease callsites**, plus the ControlAgent lease path. The new `sample-current-position-refresh-branch` command is registered in `NativeCommandRunner.cs` and accounts for the increase from the earlier handoff's 27-command count. The handoff count is now one behind this source checkpoint.

**Limits that remain real**

- This is cooperative exclusion only. The legacy `sample-position` / `sample-power` routes, generic capture/scout/snapshot/follow-pointer tools and previously deployed agents are not proven to participate. Do not describe the lease as global input/read exclusion.
- The default lock directory is under CommonApplicationData (ProgramData). The production guest ACL has not been checked or provisioned in this review. Access denial should fail closed, but a guest deployment must verify that the actual agent account can create/open the lock file and that other users cannot replace the directory/file.
- Ancestor/final-lock reparse checks are useful, but the implementation documents that final symlink prevention is non-atomic and depends on trusted directory permissions.
- The directory-symlink test catches any `IOException` as an unavailable symlink-creation environment. That can silently treat an unrelated I/O failure as “not exercised.” Narrow the skip condition to known privilege/platform errors and let unexpected I/O errors fail the test. The current checkpoint reports the symlink exercise as skipped internally, not passed.
- `nativeReadLeaseVersion=1` is a source capability/status field, not installed-binary attestation or proof that the ProgramData lock actually works in a guest. The host wrapper's `cooperativeExclusionStatus=unverified-not-acquired-by-wrapper` is appropriately honest. Require exact deployed reader/agent SHA plus a guest-side contention check before claiming live acceptance.

## 2. Location-context cross-field skew remains unbounded

Reviewed:

| File | SHA-256 |
| --- | --- |
| `src/RiftReader2.Live/CurrentBuildLocationContextCandidateReader.cs` | `79DDBFED66B5EE2CD0CCC92C4F315587C3ACF9B2DE4867A1BE05954559E94121` |
| `src/RiftReader2.Live/CurrentBuildLocationContextSampleCommand.cs` | `33466C8A5602CAD2771C751AA7D3723A0F64A606DFF6C6730D534ACABC397789` |
| `scripts/sample_current_native_location_pair.py` | `55C24973ECDCB8628D01DE25821795A348A8D5FB6FEF3C3E2B1B742C05D9C3C4` |
| `tests/test_sample_current_native_location_pair.py` | `4771C707CF6F4A2484F350FB8FFD8DBD7382AC317E251EB7F554724971E0A8E2` |

The native reader records a position interval, then calls the zone/TLS candidate reader. At completion it revalidates process and owner anchors, but it does **not** reread XYZ or prove the position bytes remained unchanged during the zone search. The host validator now correctly requires the zone interval to start at or after the position interval's completion. That fixes ordering, but it does not cap the positive gap.

**Recommendation:** before a navigation consumer can treat these fields as one location sample, add an explicit maximum cross-field skew (separate from each field's own acquisition duration) and either:
1. reread the self position component/XYZ after the zone search and require owner/XYZ stability, or
2. retain the fields as separately timed candidates and forbid combining them into a waypoint/track identity.

The current test `test_zone_capture_must_follow_position_even_within_outer_interval` proves ordering only. Add a large-positive-gap case that is rejected by the new bound. Keep `worldInstanceStatus=unavailable`; a zone key/ID candidate is not world-instance identity.

## 3. Branch-input sample command

Reviewed current branch reader, sample command and tests:

| File | SHA-256 |
| --- | --- |
| `src/RiftReader2.Live/CurrentBuildPositionRefreshBranchCandidateReader.cs` | `5091A9DC691DBD603D3083D365399DD8FF9B984818F2F48849C22BD291D2F31F` |
| `src/RiftReader2.Live/CurrentBuildPositionRefreshBranchSampleCommand.cs` | `1E617360FE4ED8AAA4EDE09352EF9143A8C5895F9B1CD28515D20F6AE3F1A4F6` |
| `src/RiftReader2.Live/NativeCommandRunner.cs` | `7A217DA309B85FA0F528AE3F88EB1491C32DBE85C5AFF274DEBD7F11E340A689` |

The earlier branch-reader review issues are now addressed in source: classification is ordered by the guards actually needed; a verified nonzero handle does not require reading the unused flag/selector; zero handle plus zero flag is classified ineligible without a selector read; and owner mismatch has a distinct status. The production sample command serializes player key and addresses as decimal/hex strings rather than unsafe JSON numbers. It acquires the shared lease and brackets the sample with session/process identity checks.

**Remaining provenance improvement before any live capture:** the sample report identifies the game executable SHA but does not embed the reader executable SHA/source revision or explicitly emit the selector RVAs (`0x2F588A0` and `0x2F57918`). Use a host wrapper that pins the exact reader binary and records its SHA, or add an implementation identity and the two selector RVAs to the report. Do not treat game SHA as reader provenance. The internal candidate record still exposes some raw `ulong` address/handle properties; production output is safe because it emits hex strings, but keep direct serialization of that internal record out of the public JSON contract.

## 4. Offline tracking tools and validation

- `scripts/summarize_native_xyz_track.py` SHA-256: `DEA085C0A5825F642B6EF08096EA1ECC25E9734F2E4212F817285E7CB5D443B9`. The retained Lab1 30/30 replay still has **29 zero sampled deltas and zero candidate path**. The summary correctly withholds path totals across gaps/identity boundaries; this is not motion or passive-freshness evidence.
- `scripts/summarize_native_orientation_track.py` SHA-256: `0F260BFEEDF2B37EACD384AC89C0D86E46F8720FE073DE380B9528671678C615`.
- `tests/test_summarize_native_orientation_track.py` SHA-256: `3121885F2969B0ACA55D291662F076B0AC8D37D7B4EF799C7F04A28ED375566D`.

The orientation comparer correctly requires same process epoch, sampled unit and component, nonoverlapping intervals, and creates boundaries on component changes or excessive gaps. It labels matrix arithmetic as structural candidates only and leaves facing/world/freshness unavailable. Its output carries per-input hashes but not source paths; retaining relative source paths alongside hashes would make evidence easier to reopen without relying on the original command line.

**Independent offline test runs in this review**

| Test group | Result | Workbridge job |
| --- | ---: | --- |
| Python XYZ track, orientation track and location-pair modules | **40/40 passed** | `rr2-jimmy-offline-xyz-python-tests-20261107-a086` |
| .NET lease, action-lease, branch-reader and branch-sample tests | **51/51 passed** | `rr2-jimmy-offline-native-lease-branch-tests-20261107-a086` |

These are offline tests only. No VM/game operation or live lease acceptance was performed.

## Recommended next order for the coordinator

1. Keep all new outputs candidate-only; do not promote stationary XYZ or matrix changes to movement/facing.
2. Add and test the location-context cross-field skew bound (or explicitly keep position and zone as independent samples).
3. Tighten the symlink-test skip filter; record that the reparse case is not yet exercised on this Windows host.
4. Add reader-binary/source provenance and selector RVAs to the branch-sample evidence contract.
5. Before deployment, provision and verify guest ProgramData ACLs, verify the exact installed agent/reader SHA, test cross-process contention in the guest, and inventory/quiesce all legacy/unleased readers. Do not claim global exclusion while any remain unleased.
6. Only after those gates, schedule a separately authorized cooperative one-lab window for a same-player changed-state XYZ/zone comparison and full RIFT-process restart requalification.

**Coordination:** This continuation report is shared-repository evidence only. It does not claim direct cross-chat delivery, implementation by Jimmy, Git commit, guest deployment, or live validation.
