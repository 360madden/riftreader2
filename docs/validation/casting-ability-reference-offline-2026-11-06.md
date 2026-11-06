# Casting ability reference 0.4.1 offline validation

Status: implemented and tested offline; not deployed, reloaded, or observed in RIFT.

`RiftReader2Casting` 0.4.1 adds `ability_reference.lua` to the unconditional
startup list between `model.lua` and `main.lua`. The version differs from 0.4.0
so an installed copy cannot be mistaken for the earlier dashboard-only package.
The module is optional with respect to API availability: failures produce a
typed blocked observation and do not prevent the existing dashboard from
loading.

The reference is fixed to Lifebound Veil (`A0865F2DE73516486`) and owns a
separate Casting model instance. It creates no UI, slash command, macro, secure
action, cast, or trial. The `RR2CASTREF1` schema remains version 1. Readiness is
the model observation, but the second ability detail used for strict typed wire
fields must match the first observation across every readiness-relevant field.
A mismatch is blocked as `ability-detail-inconsistent`; it is never emitted as
ready. Player and target identity are also checked after the second detail.

An invalid frame clock publishes one `frame-clock-invalid` observation without
performing model or ability work. Further update events remain suppressed while
the clock is invalid. A finite clock resumes sampling; consumers must treat that
recovery as a new evidence segment because the wire remains explicitly
sequential and non-atomic.

Offline validation command:

```text
artifacts/tools/lua-python/Scripts/python.exe -m unittest \
  tests.test_casting_addon tests.test_casting_ability_reference
```

Live use still requires an explicit, hash-recorded deployment and `/reloadui`.
Until then, the installed-source lineage remains
`external-deployment-receipt-required` and no runtime claim is supported.
