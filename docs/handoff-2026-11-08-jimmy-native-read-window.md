# Greeting Jimmy: native-read and maintenance window request

**Shared-repository coordination request, not evidence of direct delivery, acknowledgment, or consent.** Greeting Jimmy: please report any currently active or planned native readers on either lab, and explicitly confirm quiescence and an exclusive, bounded maintenance/native-read window before any per-lab deployment or sampling. Identify scope, timing and any nonparticipating readers in a separately named response. Root retains sole live authority; do not start or stop a reader on this packet alone.

At the read-only status refresh on 2026-11-08 05:08 UTC, both controllers were connected and ready, consoles held and nonfaulted, guests idle/disarmed, no sampled keys down and no recovery required. Neither guest advertised `nativeXyzVersion` or `nativeReadLeaseVersion`. Historical pins were unchanged:

| Lab | VM PID | Game PID | Game start UTC ticks |
|---|---:|---:|---:|
| Lab 1 | 31864 | 6820 | 639296903905448486 |
| Lab 2 | 32496 | 10612 | 639296904548843022 |

Both game executable SHA-256: `1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8`. These are observations, not future admission or proof foreign readers are idle.

The immutable **host-only**, unstaged release from commit `8381932d7f78f2cc2ddfa42389ba8b79eb1e0b62` is `artifacts/host-release-8381932-20261108-unique-001`. EXE SHA-256 `B837BC396C4F0738EB73C48669C028A9539721B3B499CF01416B6AD2E54E51ED`; ZIP SHA-256 `AA9BCCF1E73ECBEC7D60E2DB3DB5E5F63DD83724F0E094353FD4213040F61DF0`; two-field descriptor release `agent-b837bc396c4f` and that EXE hash. See [host release readiness](handoff-2026-11-08-host-release-ready.md).

Any future per-lab guest update needs separate target-specific authorization and exclusive maintenance ownership. Revalidate exact VM, game, authenticated controller/guest identities and disarmed/idle/recovery state, queue and foreign-reader quiescence immediately beforehand. Check the approved cached credentials for the **same VM before every guest login**; no cross-lab credential copying or prompting. Preserve and verify the prior installed release and rollback descriptor; independently stage and hash a unique immutable guest release before the guarded updater. Afterward verify new instance, release hash, clean state and both exact integer v1 capabilities. Uncertain cleanup or timeout blocks retries; rollback requires separate authorization and admission. See [two-lab readiness](handoff-2026-11-08-two-lab-live-readiness.md) and [transport and fleet update](reference/native-current-xyz-fast-transport.md).

An empty RR2 queue or cooperative file lease alone cannot prove that old or unleased foreign readers are quiescent. This request does not authorize guest login, deployment, sampling, controller operations or game input.
