# Workbridge workflow

For current project phase and verified foundation status, read
[the status handoff](../status.md). Workbridge is an alternate access path for
browser ChatGPT; it does not change RiftReader2's module boundaries or evidence
requirements.

## Normal Chat workers

Joey authorized normal Chat workers through Workbridge on 2026-10-26, with the
coordinator assigning bounded work, reviewing actual diffs and verifying tests.
Keep one worker per small change; assign explicit file ownership and prevent
concurrent edits to those files. Workers report completed command results, not
just submitted jobs. Live game/VM control is not part of a coding assignment.
The first coding worker, [Casting Readout Update](https://chatgpt.com/c/6adee9ee-a378-83ea-8999-0081c1c1e69c),
implemented range/timing display with 41 focused tests. The coordinator's full
gate passed at `artifacts/validation/20261026T055835Z-891717ad/`. Browser final
response rendering failed, but the local changes and checks were verified.

## Verified access

On 2026-10-18, `workspace_info` reported Workbridge **0.6.0**, write access,
and allowed roots `C:\work` and `C:\rift modding`.
The new project is already beneath an allowed root.

| Argument | Use for this repository |
|---|---|
| `project` or terminal `cwd` | `riftreader2` |
| File path | `riftreader2/docs/status.md` |
| Absolute file path | `C:\work\riftreader2\docs\status.md` |
| Git file filter or commit path | `docs/status.md`, relative to the repository |

No new tunnel, project-specific bridge server, or Workbridge runtime change is
needed for these file/Git/terminal operations. Repository documents are guidance;
they do not register tools or executable command profiles.

## Reliable work sequence

1. At session start, check `workspace_info`, then the project status and
   relevant documents. Use scoped searches and bounded reads.
2. Before replacing existing text, read the actual content and current SHA-256.
   Use `edit_file` or `write_file` with that hash. For a new file, use
   `expectedHash: null`; create its parent directories first.
3. Give each mutation a unique operation ID. After an uncertain response, inspect
   `change_status` and the affected file; reuse an ID only for the same request.
4. Review returned changes. Use Git status/diff to inspect repository state.
5. For a command, pass an explicit executable, literal argument array, and this
   repository's working directory to `terminal_run`. This is noninteractive
   execution with closed stdin, without an implicit shell.
6. Poll `command_status` until complete and read stdout/stderr through
   `command_output`. A submitted or running job is not a successful command.
   Reuse its request ID after an uncertain response instead of duplicating work.
7. For `git_commit`, supply the actual expected HEAD and selected file hashes.
   Use a null expected HEAD for an initial commit. Inspect history before
   retrying an uncertain commit.

October 24 operational exception: the dedicated `git_commit` call hung twice
without advancing HEAD. After checking `git_status` and `git_history`, the
scoped fallback through `terminal_run` succeeded: Git `add -- EXACT_FILES`,
`diff --cached --name-status`, `diff --cached --check`, then
`commit -m MESSAGE -- EXACT_FILES`. Poll for exit code zero, then recheck HEAD
and the clean worktree. This committed `374170d` without touching unrelated
files. Never blindly retry an uncertain commit or stage the whole repository.

Workbridge currently allows two concurrent command jobs. Batch independent
reads when useful; keep dependent edits, commits, and recovery sequential.

## Current commands

Git inspection is available through dedicated tools. No application command
profile is required: `terminal_run` can invoke an authorized installed tool with
literal arguments and `C:\work\riftreader2` as its working directory.

Node was reachable during setup, and REA's direct Node entry worked. The
attempted PowerShell 7 launchers were not reachable through that earlier route.

Separate October 18 browser-chat evidence now establishes a working Windows
`powershell.exe` route (5.1.26100.9711), .NET SDK 10.0.302, and an independently
authored .NET 10 helper that built and ran with overall/build/helper exit codes 0.
The retained report identifies runtime .NET 10.0.10 and marker
`CHATGPT_AUTHORED_HELPER_OK`. These are observed prior-workflow results, not a
helper rerun during this documentation review.

Source: `C:\work\workbridge-mcp\docs\local-pc-roadmap.md`, lines 84–92 and
150–173; retained report:
`C:\work\workbridge-authored-helper-browser-20261018-01\report.json`.

RiftReader2 now selects .NET 10 and its authoritative gate requires PowerShell
7. Use an observed working `pwsh` executable path and inspect the terminal job's
actual exit code. Windows PowerShell 5.1 availability does not establish that
the gate can run. If PowerShell 7 is unavailable through a particular bridge
route, report that access limitation rather than substituting a partial check.

October 24 live resolution: PowerShell **7.6.8** was installed as the Store
package `Microsoft.PowerShell`, but the shell's `pwsh.exe` WindowsApps alias
and the assumed `C:\Program Files\PowerShell\7\pwsh.exe` did not resolve
through `terminal_run`. A read-only PowerShell 5.1 query,
`Get-AppxPackage -Name Microsoft.PowerShell`, returned `InstallLocation`.
The true executable was
`C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.8.0_x64__8wekyb3d8bbwe\pwsh.exe`.
The real package binary accepted `-NoProfile -File scripts/validate.ps1`
and the full native milestone gate passed. Discover the **current** package
location each session because Store versions can change; never infer that
PowerShell 7 is absent from the zero-byte WindowsApps alias failure.

When available, the intended terminal invocation is equivalent to:

```text
executable: pwsh
arguments: -NoProfile, -File, scripts/validate.ps1
cwd: C:\work\riftreader2
```

The latest local foundation gate is recorded in
[the validation index](../validation/README.md). A historical helper result or
a submitted Workbridge job is not evidence for the current checkout.

## Generated data and recovery

Workbridge can inspect saved raw or prepared gzip snapshots. That capability
does not itself capture a live process. RiftReader2 now has an independently
verified, bounded **guest native game-memory read** path and original-byte
transfer; it does **not** yet have a continuous, synchronized live XYZ stream
or a motion-qualified field. Keep bulky output under `artifacts/` and request
only relevant portions.

Recoverable file edits and Git history serve different purposes. Workbridge's
undo records do not provide a full backup of the project or ignored artifacts.

## Local primary references

- `C:\work\workbridge-mcp\docs\coding-workflow.md`
- `C:\work\workbridge-mcp\docs\workspace-roots.md`
- `C:\work\workbridge-mcp\docs\snapshots.md`
- `C:\work\workbridge-mcp\docs\local-pc-roadmap.md`
- Current `workspace_info` and tool descriptions.

Use the live tool contracts when a later Workbridge version changes behavior.
