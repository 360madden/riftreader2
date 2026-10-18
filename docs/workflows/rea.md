# REA reference and workflow

## Existing installation

Reviewed on 2026-10-18:

| Item | Observed value |
|---|---|
| REA folder | `C:\work\tools\rea` |
| Installed package | `rea-agents` 6.5.0 |
| Public CLI entry | `C:\work\tools\rea\node_modules\rea-agents\scripts\rea.mjs` |
| Node executable used through Workbridge | `C:\Program Files\nodejs\node.exe` |
| Ghidra | 12.1.2 |
| Ghidra location | `C:\work\tools\ghidra_12.1.2_PUBLIC` |
| Java accepted by the scoped doctor | Temurin 21.0.11 |
| Codex integration | Existing REA MCP registration; scoped doctor reported it aligned. |

## What was actually verified

Before creating this repository, REA's installed `--version`, `--help`, and
`doctor --provider ghidra --json` completed through Workbridge with exit 0 and
empty stderr. The scoped doctor returned `healthy: true`.

The doctor used per-process defaults for the provider, Ghidra directory, and
Java home. Its result establishes readiness, not successful RIFT analysis.
No RIFT binary import/decompilation was performed in those checks.

Workbridge job references:

- `rea-chat-direct-version-20261018-1938`
- `rea-chat-direct-help-20261018-1938`
- `rea-chat-doctor-ghidra-20261018-1940`

## Use when binary research is authorized

Read the installed usage guidance and confirm provider capabilities before
choosing commands. Reuse this installation rather than installing another copy.

Codex has a registered direct MCP route. Browser ChatGPT can use Workbridge
terminal jobs with the installed CLI. Confirm the tools exposed by the actual
active session; registration alone does not establish that it has refreshed.

Separate CLI commands run as separate processes. A persistent REA session can
retain analysis state and evidence across related calls. Bounded requests and
saved evidence can reduce repeated work. Windows Ghidra has a limited,
experimental provider surface; not every advertised REA tool is supported.

For RiftReader2, possible uses include studying functions, references, and field
access patterns. Live observations would still be needed to qualify proposed
meanings. The exact integration is an open design choice.

## Reuse completed analysis

The installed 6.5.0 guidance already provides ways to avoid repeating expensive
analysis. For a completed native function dossier, use its retained Evidence ID
with `inspect_analysis_view` to request selected pseudocode, references, callers,
or value-flow pages. Use filtered evidence summaries to find an existing record
when its ID is unknown.

A truncated preview or oversized response does not necessarily mean analysis
failed. Retrieve a smaller view or export a portable evidence bundle instead of
repeating the producer. Retained MCP IDs are session-specific; preserve exported
results when they need to remain available across sessions. Reading a portable
bundle still requires adequate local memory.

Use the installed CLI help for the equivalent file-based commands. Repeat
readiness diagnostics when a changed environment or an actual blocker warrants
it; a healthy installation need not be rechecked before every focused query.
These are existing tool workflows, not a new V2 evidence interface.

## Primary sources

- `C:\work\tools\rea\README.md`
- `C:\work\tools\rea\node_modules\rea-agents\skills\reverse-engineer-anything\SKILL.md`, including evidence guidance at lines 251–271.
- `C:\work\tools\rea\node_modules\rea-agents\skills\reverse-engineer-anything\references\native-and-artifacts.md`, native dossier views at lines 80–96.
- [REA CLI guide](https://github.com/morluto/rea/blob/main/docs/cli.md)
- [REA MCP contracts](https://github.com/morluto/rea/blob/main/docs/mcp-contracts.md)
- [Windows Ghidra scope](https://github.com/morluto/rea/blob/main/docs/windows-ghidra-p0.md)

Upstream main can be newer than the installed package. Installed help and actual
diagnostics govern precise commands and local capability claims.
