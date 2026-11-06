# Native Mana UI screenshot attempt — November 6, 2026

Status: **refused at the foreground gate; no screenshot or input occurred.**

One capture-only attempt used the registered controller runtime
`C:\Python314\python.exe` and the fresh descriptor
`artifacts/native-mana-descriptor/lab1/d8607c07aa5247438030a49996bf03f5/review.json`
(SHA-256
`3BF66F00EBAE55BDADD93AFEC3165F45E18D50AF7AA8ECFA0AC6E016CAE590E4`).
Its bound final owner review was
`artifacts/native-unit-manager/lab1/0860355702dc47e7bfc6f75c48e7eb51/review.json`
(SHA-256
`37812F75AEE3F8139FA59549ED09BB41D9D3462227AE823F8D10156016408FD9`),
with observation completion `2026-11-06T13:36:53.5053785Z`.

The helper refused with:

```text
CaptureBlocked: guest is not idle/foreground or exact Mana process changed
```

A read-only post-attempt audit isolated the failed condition to
`target.isForeground == false`. The exact Lab-1 VM epoch, RIFT PID `7164`,
process start ticks `639294897866244204`, current executable SHA-256 and player
identity remained bound. The controller was connected and ready; its supervisor
was running with initial cleanup verified; the console reservation was held and
not faulted. The guest was disarmed and idle, did not require recovery and
reported no desktop inputs down.

The refusal occurred during the first readiness check, before access-queue
submission. No queue request, lease or token was created; the queue was
unblocked with no holder or unfinished request and retained its cleanup receipt
at generation 5195. No screenshot output directory was created. No arm, action,
keyboard, mouse or gameplay input occurred, and no retry or bypass was attempted.
The owned controller remained available as its designed persistent endpoint;
the independently observed disarmed/no-input guest state required no additional
release action.

This attempt supplies no visual or numeric UI corroboration. Any later attempt
requires a newly fresh descriptor, a separate serialized handoff and a reviewed
foreground-state plan; this receipt must not be replayed.

## Successful foreground capture

After the user manually foregrounded the existing Lab-1 RIFT window, one new
fresh descriptor was acquired under the serialized slot and one capture-only
attempt succeeded. No game UI was changed by the helper. The retained evidence
is under
`artifacts/native-mana-screenshots/lab1/mana-ui-20261106-8e3f0e98/`:

- capture ID `1d0bf09c57c84543aa3587ed69d47432`;
- `image.bmp`, 1211 by 702 pixels, 3,400,542 bytes, SHA-256
  `5179B0D2B85CB6D8641A9A0DD7A8234B46D78DC2BB9EA0673A90DCFF7FA2E0B0`;
- `capture.json`, SHA-256
  `D5194C1ADE28755F1E9AD6C0BACAA254F639C11D6233A1A1A30D18CDE6EFC5A9`;
- exact foreground target PID `7164`, start ticks `639294897866244204` and
  current executable SHA-256;
- descriptor review SHA-256
  `E28D25500B1F4C1138DABBF04C1304BE9C3AE272A74154ED95F827E614862EA7`;
- final owner review SHA-256
  `D7B06D4DA277E21367254DD8CA0A11B148DC9A910C3BF8468459AA117C69555B`.

The native owner observation completed at
`2026-11-06T13:49:06.3279054Z` with raw candidate `3980/3980`, coherent
primary revisions `33/33`, secondary revision `35` and unchanged mutable
inputs. The screenshot was captured at `2026-11-06T13:49:35.6636385Z`, exactly
**29.3357331 seconds** after that native completion.

The coordinator manually inspected the retained original and observed the
top-left **Trio** blue resource display as **3980/3980 (100%)**. This is a
manual visual reading, not OCR or an automatically decoded field. The UI's
implementation lineage is unknown: the image does not establish whether that
display uses the same resource object, native cache, RIFT API getter or another
presentation path. Agreement therefore supplies visual corroboration of one
stable baseline value, not independent arithmetic or implementation provenance.

Cleanup completed normally. Queue request
`mana-screenshot-513040d80f994076829a11ad10c8bd03` at sequence 312 finished
`succeeded`; resource generation 5197 was unblocked with no holder and cleanup
receipt
`nav-cleanup:1e88263a515d1de8fffbd4532c087553d156354d35e95ef18bb61776b89a1db3`.
The helper verified STOP and watchdog release. No arm, action, keyboard, mouse
or gameplay input occurred.

All three observations remained `3980/3980`; no Mana-consuming stimulus or
other changed state occurred. This evidence does **not** establish change
response, passive freshness, recovery behavior, continuity or restart
durability.
