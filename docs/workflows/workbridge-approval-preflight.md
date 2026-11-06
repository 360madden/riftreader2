# Workbridge write-approval preflight

At the start of a new ChatGPT RiftReader2 coding session, inspect Workbridge app permissions and Git status before starting long-running work. As verified 2026-11-01, Workbridge's app-specific permission was **Allow all actions**; do not assume a later tool stall was an approval prompt without seeing one.

If an approval is required for a real planned edit, make that **small, reviewable, recoverable edit the first mutation**. Select the offered remembered approval only if desired; approval may be per tool and per conversation. Never make dummy writes solely to elicit approval or bypass a permission gate.

After every mutation, confirm the operation receipt, saved file hash, and relevant tests before spawning heavy concurrent operations. If a write stalls or returns uncertain/aborted, inspect the exact operation journal and target file **before retrying**; preserve the operation ID and do not switch to another write route to dodge the approval. Do not call an unreceipted preview an applied change.

Reference: docs/workflows/workbridge.md and OpenAI's custom MCP-server approval documentation.
