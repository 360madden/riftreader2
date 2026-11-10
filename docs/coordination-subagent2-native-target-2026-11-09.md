# subagent2 — offline native target comparison (Nov 9, 2026)

**Lane acknowledged:** offline native retrieval/discovery; no live RIFT input, controller, VMware or guest sessions.

**Claimed files:** `scripts/compare_native_target_reports.py`, `tests/test_compare_native_target_reports.py`, and this note. Existing native samplers and other developers' source/test files are not claimed.

**Verified outcome:** `scripts/compare_native_target_reports.py --before FILE --after FILE --pid PID --start-ticks TICKS` compares two bounded source-hashed saved native selected-target reports. Same player/epoch, nonoverlapping timestamps, same target and calculated resource candidates are required for HP/energy/mana deltas. Target switches, absent targets and unavailable fields produce null deltas; no zero inference. Direct CLI launch and sanitized errors are checked.

**Focused tests:** `C:\\work\\riftreader2\\.venv\\Scripts\\python.exe -m unittest tests.test_compare_native_target_reports tests.test_sample_current_native_selected_target -v` — **25/25 passed**. Tests are synthetic/offline; no changed-state live target pair was available or acquired. Field semantics/freshness/restart recovery remain unqualified.

**Coordinator handoff:** commit only the three claimed files, no independent push. Other-lane edits in `scripts/quick_review_capture.py` and `tests/test_quick_review_capture.py` were observed and preserved; `scripts/project_current_native_energy_variants.py` was not touched.
