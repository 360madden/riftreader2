<div align="center">

<img src="docs/assets/rr2-hero.svg" alt="RiftReader2 — a practical RIFT discovery and on-demand data retrieval framework" width="100%" />

<br />

[![.NET 10](https://img.shields.io/badge/.NET-10.0-512BD4?style=for-the-badge&logo=dotnet&logoColor=white)](global.json)
[![C Sharp](https://img.shields.io/badge/C%23-Application-6939c6?style=for-the-badge&logo=sharp&logoColor=white)](src/)
[![Lua 5.1](https://img.shields.io/badge/Lua-5.1-2C2D72?style=for-the-badge&logo=lua&logoColor=white)](addon/)
[![Python](https://img.shields.io/badge/Python-Tooling-3776AB?style=for-the-badge&logo=python&logoColor=white)](scripts/)
[![Windows](https://img.shields.io/badge/Windows-Live_Reader-0078D4?style=for-the-badge&logo=windows11&logoColor=white)](src/RiftReader2.Live/)

![Stage](https://img.shields.io/badge/STAGE-Research_Preview-8e6be8?style=flat-square)
![Native](https://img.shields.io/badge/NATIVE-Read--Only-21a88a?style=flat-square)
![Evidence](https://img.shields.io/badge/EVIDENCE-SHA--256_Pinned-1689bc?style=flat-square)
![Scope](https://img.shields.io/badge/SCOPE-Independent_RIFT_Tooling-f29c46?style=flat-square)

**A practical framework for discovering RIFT data and retrieving it again on demand.**

*Native readers. In-game Lua references. Reusable retrieval paths. Shared research.*

[🚀 Quick Start](#-quick-start) · [🧠 Architecture](#-architecture-at-a-glance) · [📊 Capability Map](#-capability-map) · [🧪 Research Tools](#-explore-the-toolkit) · [📚 Documentation](#-documentation-hub)

</div>

---

## ✨ What is RiftReader2?

**RiftReader2 (RR2)** is a practical **discovery and retrieval framework** for wide-ranging data from the **RIFT MMORPG**. It brings together a versioned **in-game Lua addon**, a modular **.NET 10** codebase, read-only native readers, repeatable acquisition commands, and retained research artifacts for other tools and programs.

Its central question is simple:

> **How do we find useful information, retrieve it again when requested, and know what the result represents?**

A useful finding feeds a working retrieval path: resolve the current source and owner, acquire the requested data, and return **structured values or a clear unavailable reason**. Results retain their *source*, *game build and session*, *acquisition time*, and any *meaning, freshness or restart claims that remain unverified*. Prefer small useful capabilities and actual use; refinement is optional.

<table>
<tr>
<td width="33%" align="center"><strong>🔍 DISCOVER</strong><br /><sub>Inspect API observations, read-only memory candidates, pointer paths, and patterns.</sub></td>
<td width="33%" align="center"><strong>📡 RETRIEVE</strong><br /><sub>Use repeatable readers and commands to acquire requested data on demand.</sub></td>
<td width="33%" align="center"><strong>🧬 VERIFY</strong><br /><sub>Check source, identity and freshness; keep candidates and qualified fields distinct.</sub></td>
</tr>
</table>

### Parallel work with RRE

**RR2 and RRE are parallel, complementary efforts:** similar subject matter, different approaches and separate owners. The **RRE repository is a valuable information source** for RR2, including findings, readers, captures and retrieval techniques. Reuse useful peer work rather than repeat completed discovery, preserving its source, build and capture provenance and coordinating shared lab access.

Reports distinguish **what was discovered**, **what can be retrieved on demand**, and **what still needs qualification**. An imported historical capture can guide the next reader without establishing current live data. See the [native-discovery handoff](docs/handoff-2026-11-07-1700-native-discovery.md) for concrete peer comparisons and the [repository guidance](AGENTS.md) for the working policy.

## 🧠 Architecture at a glance

<img src="docs/assets/rr2-pipeline.svg" width="100%" alt="Three evidence streams — Lua API references, read-only native reader candidates, and saved hashed evidence — feed the .NET core and reporting pipeline" />

**Three deliberately separate evidence paths:**

- 🩵 **Lua API reference** — the in-game addon samples supported RIFT APIs and publishes bounded, versioned frames. Nonce binding supports a live observation lifecycle.
- 💜 **Native discovery** — a Windows-only reader investigates game-process data, with read-only acquisition and explicit executable/process identity.
- 🧡 **Saved evidence** — hashed capture manifests, offline replay, assessments, and reproducible comparison artifacts remain useful without a running game.

They feed the **Domain → Application → Infrastructure** core, composed by either **CLI** or the isolated **Live** executable. See the [architecture guide](docs/architecture.md) and [hybrid design decision](docs/decisions/0002-hybrid-addon-and-reader.md).

## 📊 Capability map

<sub>Legend: 🟢 implemented/verified within the linked scope · 🔵 available in controlled workflows · 🟡 active research or further acceptance needed · ⚪ deferred/not part of current scope</sub>

| Capability | State | What you can expect |
|:--|:--:|:--|
| 📦 Versioned capture validation and offline analysis | 🟢 | Verified inputs, derived movement metrics, gap detection, and reproducible reports |
| 🧩 Lua addon encoding and .NET contract decoding | 🟢 | Shared fixtures, strict framing, and typed API-reference structures |
| 🔗 Nonce-bound live addon acquisition | 🔵 | Lab 1 and Lab 2 have returned fresh, identity-bound addon-backed HP/XYZ observations; sustained 480-second continuity and movement eligibility remain unverified |
| 🧬 Standalone RR2R1 typed API reference | 🟡 | Lab 1 loaded-addon validation passed **64/64 advancing RR2R1 comparisons** on November 6; the distinct Lab 2 and physical RR2R1 typed-snapshot acceptance remains pending |
| 🛰️ Current-build native XYZ acquisition | 🔵 | Build-pinned candidate sampling was exercised in both VMware labs; fresh movement/semantic qualification is separate |
| 🧮 Memory discovery and field catalog | 🟢 | Read-only snapshots, value/pattern/pointer searches, content-pinned review and status reporting |
| 📡 Native catalog, player, target and buff retrieval | 🔵 | Repeatable readers have captured ability catalogs/names, player context/stats/XP, selected-target data and raw buff fields; these remain build/session-bound candidates with per-field qualification limits |
| 🔋 Player health, Mana/Power, casts, cooldowns | 🟡 | Native/API candidate correlation and baseline research; individual fields require changed-state and ownership evidence |
| 🖥️ Lab controller and addon-sync workflow | 🔵 | On-demand host/guest prerequisites and compare/sync/verify tools; operational readiness is checked per run |
| 🎮 Supervised movement/turning experiments | 🔵 | Bounded research actions with explicit control/stop checks; **not** an autonomous player |
| 🖱️ Reviewed Lab 1 mouse operations | 🔵 | Host-only capture, pointer movement and Browse/Close clicks passed [live acceptance](docs/handoff-2026-11-07-lab1-mouse.md), with identity, ownership, screenshot review and release checks |
| 🔄 Arbitrary game-patch survival | ⚪ | Not claimed; changed executable builds require new evidence |

> [!IMPORTANT]
> **This is a research preview, not a turnkey bot or a promise of live, qualified telemetry on every RIFT build.** A candidate value, valid saved wire frame, working reader, and independently confirmed live game field are **different states**. For the latest exact results and blockers, use [Current Status](docs/status.md).

## 🖥️ Current live target: physical RIFT

As of **November 10, 2026**, RR2's active live workflow uses the actual
`rift_x64` process running on **AMD-DESKTOP or LEGION**. VMware RIFT labs are
retired from active RR2 operation; older lab scripts and results remain for
historical research. Physical observation already supports strict host routing
and explicit PID selection for multibox sessions. See the
[physical-first development workflow](docs/workflows/development.md#current-live-workflow-physical-rift-only-2026-11-10).

Live native telemetry and input require separate host/process/freshness and
control qualification; a captured physical screenshot alone does not prove them.

## 🚀 Quick start

For the physical waypoint prototype, double-click **[`Waypoints.cmd`](Waypoints.cmd)**
on the local RIFT host. Save or click nearby points and choose **Walk + Record**
to teach their actual path, or use **Record / Stop Recording** to observe normal
movement. **Save Route / Load** retain the path; **Play Forward / Play Reverse**
replay it from the appropriate endpoint. **F8** stops playback, and **Resume**
explicitly continues unfinished progress after a stop or same-build/player RIFT
restart. The window reconnects while idle and freshly pins the new game process.
Routes support up to 1,000 world units and 500 waypoints on a known clear path,
without obstacle avoidance. The longer envelope is implemented and offline
verified; earlier short-route live evidence remains scoped to those trials.
For console control of the open app, use **[`rr2-waypoints.cmd`](rr2-waypoints.cmd)**:
`rr2-waypoints status`, `rr2-waypoints radar show`, or `rr2-waypoints help`.
PowerShell prefixes the launcher with `.\`. The [CLI reference and examples](docs/planning/five-hour-recorded-routes-2026-11-12.md#waypoints-cli--november-13)
cover route edits, passive guide/trail, beacons and guarded movement. Use `--json`
for automation; movement requires explicit `--execute` and retains STOP/release.

See the [waypoint guide](docs/workflows/physical-waypoints.md) for setup, measured
results and restart/obstacle limitations. Launching the window sends no game input.

### 1. Prerequisites

| Tool | Version / purpose |
|:--|:--|
| 🪟 **Windows** | Required for native process reading and VMware-lab integrations |
| 🟣 **.NET SDK** | Exactly **10.0.302**, pinned with roll-forward disabled in [`global.json`](global.json) |
| 🔵 **PowerShell** | PowerShell **7** (`pwsh`) for the repository validation workflow |
| 🟨 **Python** | Tooling and optional lab scripts; Lua tests use `lupa==2.8` with a Lua 5.1 module |

See the [complete development setup](docs/workflows/development.md). The core offline libraries are modular; live integration is Windows-specific.

### 2. Clone and inspect

Open **PowerShell 7**:

```powershell
git clone https://github.com/360madden/RiftReader2.git
Set-Location .\RiftReader2
dotnet --version
```

Expected SDK: `10.0.302`. If another SDK appears, install the pinned SDK before building.

### 3. Run a zero-game-required demo

```powershell
# Inspect available commands.
dotnet run --project src/RiftReader2.Cli -- --help

# Validate the included synthetic capture.
dotnet run --project src/RiftReader2.Cli -- validate-capture --manifest samples/demo/capture.json

# Produce deterministic, derived-motion analysis.
dotnet run --project src/RiftReader2.Cli -- analyze --manifest samples/demo/capture.json --config config/default.json
```

**No RIFT game session or VMware machine is required** for these commands. The included demo is **synthetic**, so it demonstrates the pipeline rather than a real player's live telemetry.

### 4. Validate the repository

The full gate requires the Lua/Python test runtime described in the setup guide:

```powershell
python -m venv artifacts/tools/lua-python
.\artifacts\tools\lua-python\Scripts\python.exe -m pip install -r requirements-lua-tests.txt
pwsh -NoProfile -File .\scripts\validate.ps1
```

The validation script includes C# checks, Lua contract coverage, architecture and documentation checks, and CLI smoke tests. **Do not infer a green current run from this README**; see actual results in [status](docs/status.md) and [validation records](docs/README.md).

## 🧪 Explore the toolkit

<details open>
<summary><strong>🟦 Offline analysis, discovery, and evidence inspection</strong></summary>

The CLI can validate captures, calculate derived motion, decode strict addon frames, search saved memory, compare snapshots, evaluate recorded field assessments, and export discovery catalogs.

```powershell
# Saved frame decoding (requires an exact existing wire-frame file).
dotnet run --project src/RiftReader2.Cli -- decode-addon --frame artifacts/example.wire

# Offline discovery export (synthetic example identity).
dotnet run --project src/RiftReader2.Cli -- export-discoveries --manifest samples/discovery-sources.json --build-sha256 ('A' * 64) --session-id synthetic-session-a --as-of 2026-10-21T00:00:00Z --format json --output artifacts/discoveries-example.json
```

The frame example assumes you already have `artifacts/example.wire`; it is **not** included as a live data source. Exact frame bytes are required, without a trailing newline. Reports keep the source-binding and freshness limitations explicit.

Open [`scripts/discovery_explorer.html`](scripts/discovery_explorer.html) locally, then select an exported discovery JSON file to **filter, sort, inspect, and download** records without contacting the game.

📖 [Memory discovery](docs/reference/memory-discovery.md) · [Discovery compilation](docs/reference/discovery-compilation.md) · [Field catalog](docs/reference/field-catalog.md)

</details>

<details>
<summary><strong>🟪 Native position research (identified RIFT builds only)</strong></summary>

On a Windows machine with a matching RIFT executable, the Live reader supports build-bound native position-candidate sampling. For the current-build two-lab workflow, see the [native sampling guide](docs/reference/current-native-position-sampling.md).

```powershell
# Example: use the existing host/lab wrapper in a configured RR2 lab.
python scripts/sample_current_native_xyz.py --lab lab1 --samples 3 --interval-ms 400
```

This is **not** a universal coordinate offset, gameplay movement command, or proof of player-position semantics on an updated game client. The reader checks process/build identity and publishes *candidate* observations.

📖 [Current-build validation](docs/validation/native-current-sampler-2026-11-05.md) · [Historical known-build sampler](docs/reference/known-position-sampling.md)

</details>

<details>
<summary><strong>📡 On-demand player, ability and buff candidate retrieval</strong></summary>

Existing lab samplers turn discovery into repeatable acquisition commands. In a configured lab, for example:

```powershell
# Read current player-context candidates through the existing guarded workflow.
python scripts/sample_current_native_player_context.py --lab lab1
```

Other readers cover [ability catalogs](scripts/sample_current_native_ability_catalog.py), [selected targets](scripts/sample_current_native_selected_target.py), [experience values](scripts/sample_current_native_experience_values.py), and [raw buff details](scripts/sample_current_native_buff_details.py). Each has its own arguments and prerequisites; use its `--help` and linked research notes. Fresh build/process identity and applicable ownership/freshness checks remain part of acquisition. A successful candidate read does not establish changed-state semantics or restart recovery.

📖 [Player and target findings](docs/reference/native-player-context-candidates.md) · [Buff findings](docs/reference/native-buff-candidates-2026-11-07.md) · [Current discovery handoff](docs/handoff-2026-11-07-1700-native-discovery.md)

</details>

<details>
<summary><strong>🟩 Addon synchronization and live-session binding</strong></summary>

The source addon is distinct from the package installed in RIFT. RR2 contains tools for comparing, synchronizing, and verifying addon installations on the host and configured labs.

```powershell
# Run from the repository root with the configured environment.
python scripts/addon_sync.py check --target all
python scripts/addon_sync.py sync --target all
python scripts/addon_sync.py verify --target all
```

The `sync` command **changes installed addon files**. Use it only after reviewing the target-specific workflow. File hashes matching on disk do **not** establish that the game has reloaded the addon or that fresh live telemetry is available.

A live addon load can be bound using `/rr2bind <nonce>` (with a reader-generated 32-character hexadecimal nonce). An addon UI reload clears that binding and requires a fresh one.

📖 [Addon package](addon/README.md) · [Sync workflow](docs/workflows/addon-sync.md) · [RR2R1 reference contract](contracts/addon/reference-v1.md) · [Live transport](contracts/addon/live-transport-v1.md)

</details>

<details>
<summary><strong>🟧 Lab operations and guarded experiments</strong></summary>

Development workflows can use **RIFT-Lab-1**, **RIFT-Lab-2**, and a physical Windows client, with separate identities and run receipts. On-demand controllers and guest agents recover eligible prerequisites while keeping actual game-input authority separate.

The bounded experiment layer supports explicitly supervised movement/turning validation. It does **not** provide general-purpose navigation or autonomous combat.

📖 [Operational dependencies](docs/workflows/operation-dependencies.md) · [Supervised experiments](docs/reference/guarded-experiments.md) · [Three-target development workflow](docs/workflows/development.md)

</details>

## 🗂️ Project map

| Area | Responsibility |
|:--|:--|
| [`addon/`](addon/) | RIFT Lua producers, API references, versioned frames, and operator-delivered guidance |
| [`src/RiftReader2.Domain/`](src/RiftReader2.Domain/) | Typed observations, units, identities, and result semantics |
| [`src/RiftReader2.Application/`](src/RiftReader2.Application/) | Analysis and evidence-aware application behavior |
| [`src/RiftReader2.Infrastructure/`](src/RiftReader2.Infrastructure/) | Strict parsing, capture verification, config, and persisted reports |
| [`src/RiftReader2.Cli/`](src/RiftReader2.Cli/) | Offline command-line entry point |
| [`src/RiftReader2.Live/`](src/RiftReader2.Live/) | Isolated Windows process observation and live-reader composition |
| [`contracts/`](contracts/) | Explicitly versioned addon and transport schemas |
| [`scripts/`](scripts/) | Repeatable research, synchronization, lab orchestration, and local explorer |
| [`tests/`](tests/) | C#, Python, Lua, and cross-language validation |
| [`docs/`](docs/) | Architecture, evidence, decisions, validations, guides, and handoffs |

## 🧭 Where the research is going

```text
FOUNDATION       ██████████  Versioned offline analysis and strict contracts
LIVE REFERENCE   ███████░░░  Identified-session transport; RR2R1 acceptance pending
NATIVE RESEARCH  ██████░░░░  Candidate sampling; per-field qualification ongoing
AUTOMATION       ███░░░░░░░  Supervised experiments only; player bot out of scope
```

*These bars are an **illustrative stage map**, not measured completion percentages.*

Current priorities emphasize **useful discovery and reliable on-demand retrieval**, **reuse of complementary RRE work**, **changed-state evidence**, **session/restart identity**, and **self-contained RR2-owned telemetry**. Build useful retrieval paths with the existing tools; refinement can follow actual use when needed. Older RiftReader and probe work can inform research but are **not runtime requirements**.

📍 [Current ranked RR2 roadmap](docs/planning/implementation-roadmap.md) · [Waypoints roadmap](docs/planning/five-hour-recorded-routes-2026-11-12.md) · [Current status and validation notes](docs/status.md)

## 📚 Documentation hub

| Start here | You'll find |
|:--|:--|
| 📌 **[Current status](docs/status.md)** | Most recent verified results, handoffs, and known blockers |
| 🧠 **[Architecture](docs/architecture.md)** | Hybrid design, responsibilities, and data boundaries |
| 🛠️ **[Development guide](docs/workflows/development.md)** | SDK, dependencies, tests, and safe iteration |
| 📡 **[Addon guide](addon/README.md)** | Package, binding, typed reference and live framing |
| 📐 **[Contracts](contracts/addon/README.md)** | Wire formats, decoders, and cross-language fixture expectations |
| 🔬 **[Native capture](docs/reference/native-capture.md)** | Read-only acquisition and exact process/build evidence |
| 🧾 **[Documentation index](docs/README.md)** | Research references, validation records, decisions, and experiments |

## 💡 Design principles

**Practical on-demand retrieval** · **Reuse complementary research** · **Evidence over inference** · **Exact build identity** · **Freshness over plausible numbers** · **Read-only native acquisition** · **Clear separation of API/native/derived data** · **Small useful increments**

---

<div align="center">

**Built for curious RIFT developers, toolmakers, and reverse-engineering researchers.**

<sub>Independent community research project. Not affiliated with, endorsed by, or operated by the RIFT game's publisher.</sub>

<br /><br />

[![Explore the code](https://img.shields.io/badge/EXPLORE-THE_CODE-805AD5?style=for-the-badge&logo=github&logoColor=white)](src/)
[![Read the docs](https://img.shields.io/badge/READ-THE_DOCS-1689c2?style=for-the-badge&logo=readthedocs&logoColor=white)](docs/README.md)
[![See the status](https://img.shields.io/badge/VIEW-CURRENT_STATUS-1ca78e?style=for-the-badge)](docs/status.md)

</div>
