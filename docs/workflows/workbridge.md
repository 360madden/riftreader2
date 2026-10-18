# Workbridge workflow

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

Workbridge currently allows two concurrent command jobs. Batch independent
reads when useful; keep dependent edits, commits, and recovery sequential.

## Current commands

Git inspection is available through dedicated tools. No application command
profiles exist for RiftReader2 yet. A missing profile does not prevent using
`terminal_run` for an authorized installed tool.

Node was reachable from Workbridge during setup. REA's direct Node entry worked;
the attempted PowerShell 7 launchers were not reachable through that route.
This does not establish that PowerShell is absent from the machine. Resolve
actual executable paths before depending on a shell.

## Generated data and recovery

Workbridge can inspect saved raw or prepared gzip snapshots. That capability
does not itself capture a live process. Keep bulky output under `artifacts/`
and request only relevant portions.

Recoverable file edits and Git history serve different purposes. Workbridge's
undo records do not provide a full backup of the project or ignored artifacts.

## Local primary references

- `C:\work\workbridge-mcp\docs\coding-workflow.md`
- `C:\work\workbridge-mcp\docs\workspace-roots.md`
- Current `workspace_info` and tool descriptions.

Use the live tool contracts when a later Workbridge version changes behavior.
