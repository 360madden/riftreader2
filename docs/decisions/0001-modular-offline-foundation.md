# 0001: Modular offline foundation

Status: accepted.

Date: 2026-10-18.

Authorized by: Joey authorized building as much of a modular, organized,
configurable foundation as practical, with efficient future upgrading and AI
work. The implementer selected the concrete stack and boundaries below under
that delegated authority.

## Context

RiftReader2 must turn RIFT observations into reliable, reusable knowledge while
reducing rediscovery after restarts and updates. V1 provides valuable evidence,
tools, and failure lessons, but its application and architecture are not the V2
starting point. The first useful foundation also needs to work entirely from
saved evidence so it can be tested without a running game.

A single undivided project would make file formats, analysis, CLI behavior, and
future native process access easy to couple. A service-based or plugin platform
would introduce configuration, deployment, discovery, and failure modes before
RiftReader2 has multiple independently operated workloads.

## Decision

Use .NET 10 with SDK `10.0.302` and a modular, single-process command-line
application. Create these production boundaries:

- Domain owns evidence and analysis meaning and uses only .NET base libraries.
- Application owns use cases and streaming derived-motion analysis.
- Infrastructure owns strict versioned JSON configuration and capture formats,
  SHA-256 verification, bounded UTF-8 JSON Lines reading, and atomic result
  persistence without overwriting existing evidence.
- CLI owns explicit composition, commands, help, and exit behavior.

Application depends on Domain. Infrastructure depends on Domain. CLI composes
all three. A single xUnit test project verifies important behavior and module
boundaries. Product projects have no external package dependencies; test
packages are centrally pinned and restore uses lock files.

The first vertical slice analyzes a verified manifest plus JSON Lines capture
and supports capture validation as a separate command. Hashing and replay use
the same open file handle, input size and line length are bounded, and strict
readers reject missing, duplicate, or unknown members. Its tracked sample is
synthetic and illustrative. It does not claim to reproduce V1 motion findings.

Use direct construction for the current composition path. Add interfaces,
dependency-injection infrastructure, runtime plugin discovery, services,
scheduling, or a database only when a demonstrated next capability needs them.

## Consequences

The module graph can be checked mechanically and each external format can
evolve through an explicit schema version. Offline analysis stays deterministic
and testable, and a later native reader cannot push process-access details into
analysis semantics.

There are more projects than a minimal CLI, and cross-project changes require
careful dependency discipline. Direct composition may need revision when a
second real adapter appears. JSON artifacts will eventually be inefficient for
some catalog queries; that is a reason to measure the need before adopting a
database.

## Alternatives considered

- Copy or refactor V1: rejected as a default because V2 has different durability
  and recovery goals; selective reuse remains subject to independent review.
- One project organized by folders: simpler initially, but offers weaker
  enforcement at the adapter and domain boundaries most likely to drift.
- Multiple services or processes: deferred until independent deployment,
  isolation, or scheduling is demonstrated.
- Runtime plugin framework: deferred until independently versioned third-party
  extensions exist.
- SQLite from the start: deferred until measured query, scale, or transactional
  needs justify it.

## Validation

Repository validation is defined in
[the development workflow](../workflows/development.md). Passing results and
their date belong in the current status or a validation record; this decision
does not itself claim those checks passed.
