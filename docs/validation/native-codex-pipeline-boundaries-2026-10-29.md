# Native Codex pipeline and boundary review — 2026-10-29

The main-PC coordinator assigned complementary read-only native Codex tasks in
parallel. Lab-1 traced the locally installed producer, wire and live modules;
Lab-2 traced installed guidance acceptance and invalidation. Lab-1's hashes for
producer, wire and live matched the main checkout; Lab-2's guidance/main hashes
matched it. Lab-1's offline/recall-marked guidance.lua was not opened.

Lab-1 identified clock/player/coordinate acquisition and sequence/epoch
handling. Lab-2 identified the separate 1.5-second current-observation and
10-second result-age limits, and the strict per-axis 0.5-unit movement limit.
The main coordinator reviewed the source and relayed Lab-1's observation
context to Lab-2. Lab-2 then provided an age-boundary setup with result clock
100, current clock 109, current sequence 21 and source sequence 10, so the
fresh-observation check does not mask the result-age check. Other identity,
field, sequence and binding requirements must remain valid.

The coordinator added two tests in `tests/test_guidance_addon.py`: exact result
age 10 versus 10.001 seconds with a fresh observation, including subsequent
invalidation; and coordinate displacement exactly 0.5 versus 0.5001 on receipt
and after acceptance. The real Lua 5.1 focused suite passed 20 tests. These are
offline synthetic inputs and do not establish live movement, actual UI delivery,
game restart durability, or field semantics.

The full repository gate also passed: 539 .NET tests, 1,001 Python tests
(2 skipped), Lua/shared-contract checks, published native smoke, format,
deterministic demo and 767 relative links. Evidence is under
`artifacts/validation/20261029T182217Z-d304322c/`.

Initial native turns: Lab-1 `01a188e3-b657-7d40-b98c-6c1d2fec5304` and Lab-2
`01a188e3-c219-7371-bbc3-8d8c8b2ca7c8`. Lab-2 cross-review and test-review
turns were `01a188e4-af28-7973-9f09-114dc8e4a98d` and
`01a188e5-8a78-7033-aacb-0b359c43bccd`. A passive wait on Lab-1 reported a
host-change error; a subsequent exact-host read recovered its completed turn.
No game input, game launch or guest source edits were requested.
