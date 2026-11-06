# Native Codex addon inventory — 2026-10-29

Joey requested native Codex workflow exploration while an unidentified issue
is being investigated. The main-PC coordinator sent read-only inventory tasks
to the existing native Codex chat in each lab. They ran concurrently and
returned local machine names and command outputs, which were inspected against
the main checkout at `d9760e7`.

At 17:37 UTC neither guest reported a `rift` or `rift_x64` process. Both found
the addon under their own `C:\Users\mrkoo\OneDrive\Documents\RIFT\Interface\Addons\RiftReader2`.
The three files in Lab-2 matched the checkout's SHA-256. Lab-1's `RiftAddon.toc`
and `main.lua` matched; `guidance.lua` was 7,566 bytes and had attributes
4199968 including the recall-on-data-access bit. The lab worker deliberately
skipped opening or hashing it to avoid initiating a cloud recall. This does not
prove it is unreadable or that its bytes mismatch. No file was repaired or
hydrated in this check.

The checkout hashes for comparison were `FCAE6B22834474831BED3C9E3341FE9635033EF43F8F6FE96A93780D2376001F`
(TOC), `35F50FE3AD697B167D3068636840BEE1EB99C62B4AD9965B2E05429B9AF81AE1`
(guidance), and `BA0777EF8732CC5A2108F47DDEEA14555A8070804FCF930E572082197341AC52`
(main). These disk observations do not prove which bytes a running game loaded.

Remote turns: Lab-1 `01a188bc-c2f7-7e41-94eb-ce3f8721bec6`, Lab-2
`01a188bc-cd9d-7091-b479-c8778caea198`. No game or settings changes were
requested. When the unidentified issue is understood and further game work is
appropriate, inspect Lab-1's recall state and verify local file availability
before relying on guidance; do not assume the earlier repair still holds.
