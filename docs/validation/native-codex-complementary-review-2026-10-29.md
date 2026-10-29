# Native Codex complementary review — 2026-10-29

At Joey's request the main-PC coordinator gave both existing remote Codex
chats complementary read-only tasks. Lab-1 inspected guidance file metadata
and the locally available main.lua; Lab-2 reviewed installed guidance and main
source for freshness checks. The coordinator checked the reported checks
against the main checkout and then relayed Lab-1's finding to Lab-2 for a
startup-dependency review. The initial turns overlapped.

Lab-1 reported `guidance.lua` attributes `0x00401620` (including Offline,
SparseFile and ReparsePoint) while OneDrive was running. It did not open,
hash or hydrate the file. The observation does not prove whether RIFT can read
the file. Lab-1's readable main.lua calls `privateVars.Guidance.New()` at line
6; its constructor must be available at that point.

Lab-2's installed guidance.lua and main.lua hashes matched the main checkout.
Its source review correctly identified observation freshness (1.5 seconds),
result expiry (10 seconds), lab/session and sequence checks, and invalidation
when a coordinate moves by over 0.5. It noted that successful UI presentation
and live inputs are not proven by source. In a subsequent coordinator-relayed
review, Lab-2 found that its manifest lists guidance.lua before main.lua and
that main.lua calls the constructor without a nil check. If the guidance module
did not load and nothing else defined the constructor, startup would fail at
that call. This is an inference, not proof of what RIFT would do on Lab-1.
Lab-1's manifest matched the checkout in the earlier inventory.

Remote turn IDs: Lab-1 `01a188e1-7fac-7d22-9070-fe34a3cbe2df`, Lab-2
`01a188e1-8dab-7221-9712-ffc9608ec20e`, and Lab-2 follow-up
`01a188e2-6495-7f11-802f-625ac0ffcd7e`. A passive wait for Lab-2 returned
`Task host changed during passive read`; an immediate exact-host read found
the completed turn. This is an observed monitoring error, not proof that the
lab actually changed hosts or lost connectivity.

No files, settings, game processes or input were changed by the assigned tasks.
This shows useful complementary source and environment work through the native
chats, with manual coordinator relay; it does not test file transfer or repair.
