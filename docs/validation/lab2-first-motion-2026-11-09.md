# Lab2 first measured movement — 2026-11-09

**Result:** One authorized, guarded S/backward calibration moved the RIFT player and changed independently observed XYZ, but **failed the key-hold timing requirement**. This is not a successful calibration or waypoint arrival. No further game input pending a release-timing fix.

- Planned hold: **150 ms**. Observed guest key-down to key-up: **1,850.3 ms** (2026-11-09T05:33:25.7629717Z to 05:33:27.6125501Z). The guarded runner rejected the action as timing drift.
- Independent feedback: pre (7182.45996, 820.51996, 3159.66992) at 05:33:23.504Z; post (7187.02002, 822.44000, 3163.21997) at 05:34:15.836Z. Delta X +4.56; Delta Z +3.55; horizontal displacement **5.78 units**. This does not establish safe control accuracy.
- Reader was fresh-scoped to Lab2 RIFT PID 10876 with reader PID 7560, nonce 6fc3df443f664a9cbf82ac8693df5d26, journal sequence 647. It expired at 05:37:30Z; old source pins must not be reused.
- Postflight guest: armed=false, busy=false, desktopInputsDown=[], recoveryRequired=false, expiresInSeconds=0. Lab2 host queue unblocked with no holder. Keys released. Lab1 VM/game and 4 GiB RAM unchanged.
- Evidence: artifacts/sunday-night-20261108-2250/lab2-calibration-run-05/{action-1.json,final-status.json,feedback/}.

**Next milestone:** Independent bounded-release watchdog, cheap in-hold target validation, adversarial offline tests, then a fresh live trial with new reader and queue evidence.
