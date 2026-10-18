# Existing RiftReader reference

Reviewed: 2026-10-18. These are reference observations, not V2 validation.

## Source location and state

Existing repository: `C:\rift modding\RiftReader`.

Observed branch: `codex/reliable-vm-control`.
Observed HEAD: `a13bab171a2d86b3f5f6c3e437ccd11f13359187`
(`fix(v1): qualify guest yaw and guard movement recovery`).

The working tree contained modified and untracked native-motion/observer work
when inspected. HEAD alone does not represent all current local files. The new
repository does not copy, freeze, or modify that working tree.

## Useful dated evidence

Primary source:
`C:\rift modding\RiftReader\docs\workflow\riftreader-v1-freeze-qualification-2026-10-18.md`

SHA-256 of that report at review:
`5e672dc89b79f6b059f9106a8b7d0afdfb0e68c1b2c0ef13a4d7d1bc20886795`.

| Observation from the report | Applicability and limit |
|---|---|
| Guest build `STABLE-1-1169-a-1256556`. | Identifies the qualified guest build, not all installations. |
| Executable SHA-256 `7C356C9DDE9E12FCBFF3C08D953B0630B48B1510A0FFB36E4EC164606E7B17BD`. | Compare actual target identity before reusing its findings. |
| Root RVA `0x32E0200`; coordinate offset `0x320`. | Historical locating clues; not a complete V2 recipe or a current resolved address. |
| Guest restart changed process identity and owner pointer while the qualified layout remained applicable. | Evidence for the recorded transitions on that build. |
| 20 selected successful VMware cycles in 23 attempts. | The report preserves failed attempts and selection lineage; this is not a general reliability percentage. |
| One post-input artifact capture failed with `PermissionError`; the original exception stack was unavailable. | Useful diagnostic lesson; its precise cause was unproven in the report. |

The report also records source checks, two stale-capture rejections, and limits
on host-native movement and input observation. Read it before relying on those
results. This setup did not rerun V1 tests or live qualification.

## Reuse candidates to inspect when relevant

V1 includes a .NET 10 C# reader, Lua validation/reference tooling, saved captures,
pointer resolution, and experiment/control helpers. Its root README identifies
the memory reader as the current focus.

Potential lessons include maintaining field semantics with offsets, recording
read failures and timing, distinguishing intended input from observed behavior,
and separating session addresses from durable locating knowledge.

Code reuse, migration, and changes to V1 remain undecided. Its large agent policy
and historical workflows are not copied into this project's instructions.

## Source references

- `C:\rift modding\RiftReader\README.md`, opening project and qualification sections.
- Qualification report above, especially build/layout and acceptance sections.
- Workbridge Git status and history read on 2026-10-18.

External local references can change independently of this repository.
