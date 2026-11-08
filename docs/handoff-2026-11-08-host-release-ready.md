# Host-only release readiness — 2026-11-08

Source commit: `8381932d7f78f2cc2ddfa42389ba8b79eb1e0b62`. Built from an isolated Git archive using .NET SDK 10.0.302; locked solution restore and Release publish passed without modifying tracked lockfiles.

- Host directory: `artifacts/host-release-8381932-20261108-unique-001`.
- Executable: `publish/RiftReader2.Live.exe`, 118,008,160 bytes, SHA-256 `B837BC396C4F0738EB73C48669C028A9539721B3B499CF01416B6AD2E54E51ED`.
- Bundle: `bundle/agent.zip`, 47,972,059 bytes, SHA-256 `AA9BCCF1E73ECBEC7D60E2DB3DB5E5F63DD83724F0E094353FD4213040F61DF0`.
- Immutable release descriptor: `agent-b837bc396c4f`, executable SHA-256 as above. The ZIP's `current.json` has the two-field descriptor; package `release.json` is metadata, not that descriptor.
- Host `--help`, synthetic native published smoke (bundle identity, PE header, stale epoch, no-overwrite), ZIP CRC and payload SHA checks passed. Jobs: `rr2-host-release-8381932-isolated-20261108-001`, `rr2-host-release-8381932-verify-20261108-001`, both exit 0.

**Host-only: not staged or deployed.** Prior readiness evidence showed both installed agents lacked advertised `nativeXyzVersion` and `nativeReadLeaseVersion`; that historical status is not fresh admission. Before any separately authorized per-lab maintenance, revalidate exact identities, idle/disarmed state, queue and guest release/rollback; verify independently staged immutable bytes and explicitly check both integer v1 capabilities after replacement. The launcher does not stage the executable and its lease option does not itself check XYZ capability.

Foreign/legacy readers may not participate in the file lease. Greeting Jimmy's coordination request is not proof of delivery or relinquishment; current foreign-reader quiescence remains unconfirmed. No guest login, controller, VM, game, staging or deployment action was performed in this build. Host smoke is not live acceptance.
