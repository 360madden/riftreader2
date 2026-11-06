# Two-lab Codex handoff — 2026-10-29

## Purpose and current state

Joey is developing RiftReader2 as a practical hybrid of the RIFT Lua addon
and an external application. The main PC repository at `C:\work\riftreader2`
is authoritative. The two VMware guests are available for complementary
research and validation. Native Codex remote connections and automatic
startup were the focus of the latest work.

As observed on 2026-10-29, both guests retained their distinct Windows names
and native remote environments. Their Codex servers started automatically
after a fresh Windows logon, and the main PC could read an existing chat via
each exact host. These are point-in-time results; reacquire current state.

| Guest | Native environment ID | Scheduled task | Latest verified boot (UTC) |
| --- | --- | --- | --- |
| RIFT-LAB-1 | `env_e_6ae359123e7c83218b3d11753a7278b4` | `RiftReader2-CodexRemote-Lab1` | 16:29:22 |
| RIFT-LAB-2 | `env_e_6ae3592b79408321aa1a8cb7dfc2d81a` | `RiftReader2-CodexRemote-Lab2` | 16:37:30 |

Each task uses a limited interactive user logon and an Explorer handoff. Lab-1
uses 5-second task and worker delays; Lab-2 uses 20 and 15 seconds. The user
must log on and Explorer must run; this is not a pre-login service. Tracked
launcher sources are in `scripts/guest-lab1-codex/` and
`scripts/guest-lab2-codex/`.

## Duplicate-server fix and limits

On Lab-2's first test reboot, its remote server connected, then the packaged
desktop app started a second server and produced six HTTP 409 log rows. The
per-user `OpenAI.Codex` startup task `App` was disabled, matching the prior
Lab-1 fix. The desktop app is still installed and can be opened manually.
On the final boots, zero 409s and zero warning/error remote-control log rows
were observed at 116 seconds for Lab-1 and 143 seconds for Lab-2. Later manual
desktop launch and longer-term stability have not been tested.

RIFT and the guest game-control agents were absent during the latest checks.
Codex connectivity does not establish game or control readiness. Prior control
hosts require their normal reconciliation and fresh VM/game identity before
game work; do not infer readiness from historical evidence.

## Continuing work

1. Start with [repository instructions](../../AGENTS.md),
   [current status](../status.md), and the relevant task documents. Preserve
   unrelated work and check Git status before editing.
2. For guest Codex jobs, use the existing [lab job workflow](lab-codex.md),
   distinct lab identities and cached VM-specific guest credentials. Do not
   copy authentication files or expose passwords. Native remote connections
   are preferred; SSH was not needed for this verification.
3. Before live RIFT work, confirm current VM, game process and build identities
   and applicable single-controller access. The existing bounded console
   helpers remain subject to the repository's guards; direct ChatGPT Computer
   Use inside RIFT is deferred. Patch recovery remains deferred until requested.
4. Select the next work based on Joey's instruction and the current project
   status. Do not treat this handoff as authorization to launch games or
   conduct a new experiment.

## Evidence

- [Combined reboot verification](../validation/two-lab-codex-reboot-2026-10-29.md)
  records the initial Lab-2 failure, fix, final boots and test boundaries.
- [Lab-1 startup details](../validation/lab1-codex-autostart-2026-10-29.md)
  and [Lab-2 startup details](../validation/lab2-codex-autostart-2026-10-29.md)
  document their original implementation; use the combined record for the
  latest Lab-2 repair and verification.
- Sanitized local receipt: `artifacts/native-codex-pairing-20261029/preflight/two-lab-reboot-autostart-verification-20261029.json`
  (ignored by Git; SHA-256 `d99afe5b7791d23db72ff339f7e25aa4c6e849a0340d755521a1aae685563fa2`).
- The combined verification checkpoint was committed as `bb36e3f`.
