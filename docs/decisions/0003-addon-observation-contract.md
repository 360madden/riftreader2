# 0003: Addon observation contract

Status: accepted and implemented. Offline contract validation and a later
actual-client source gate passed; ADR 0004 owns live binding.

Date: 2026-10-18.

Authorized by: Joey authorized the next minimal hybrid slice: a Lua producer,
C# decoder, and shared executable contracts. This decision does not authorize or
claim addon deployment, live RIFT testing, or a transport implementation.

## Context

The hybrid boundary in [ADR 0002](0002-hybrid-addon-and-reader.md) requires a
small addon API reference before .NET can acquire and compare live observations.
V1 evidence showed that Lua globals can leave old copies, reload resets local
counters, SavedVariables are not live truth, and addon/API agreement does not
prove native memory. A transport-independent wire contract is therefore needed
before live acquisition.

## Decision

Create a modular addon package with `wire.lua`, `producer.lua`, and `main.lua`,
loaded in that order by `RiftAddon.toc`. The manifest uses the V1-observed RIFT
environment value 4.4 pending a current-client test. Do not add deployment or
automatic installation.

Implementation update: the current-client gate later passed with environment
4.4. ADR 0004 added `live.lua` and the one-load binding without changing RR2A1.

Freeze addon version `0.1.0` with observation schema 1. The exact contract lives
in [the addon contract](../../contracts/addon/README.md) and shared fixtures.
The frame is ASCII, at most 4096 bytes, with no bytes outside the markers
(including a trailing newline). JSON whitespace inside the markers is accepted.
The producer publishes one current frame to
`RiftReader2_Frame`; this global is not a transport.

The observation includes only clock, player identity, coordinates, health,
maximum health, and combat state from the addon API, with explicit field status.
It has no yaw, units, UTC age, process identity, or native-memory claim. Producer
sequence and epoch are local state and do not establish reload identity.

Add a strict .NET decoder and CLI command:

```text
decode-addon --frame PATH [--output PATH]
```

Offline results identify exact input bytes by SHA-256 and always report source
binding as `unbound` and freshness as `unverified`. They cannot enter native correlation or motion analysis as bound
live observations.

Shared fixtures drive real Lua 5.1 producer tests, C# decoder tests, and a
cross-language pass that decodes actual producer output. This cross-language
gate is mandatory in `scripts/validate.ps1`; no V1 installation path is
hardcoded.

## Consequences

Lua and .NET share one executable semantic contract, including unavailable,
invalid, zero, false, identity-race, clock-loss, recovery, and regression cases.
Malformed or unsupported data fails closed rather than being upgraded silently.

The global frame remains inaccessible to .NET until a later adapter selects and
validates a real transport. Current mocked tests do not establish that the
observed V1 event/API shape or environment value works in the current RIFT
client. A later adapter must independently bind process and addon-load identity,
record receiver-monotonic receipt time, reject stale/conflicting payloads, and
demonstrate advancement before granting freshness.

Any schema or producer-version change requires explicit compatibility work,
fixtures in both languages, documentation, and a new or superseding decision.
