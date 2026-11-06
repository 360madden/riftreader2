# Current-build native XYZ sampler: Lab 2 checkpoint

On 2026-11-06, two no-input Lab 2 acquisitions completed against game PID **9752**, start ticks **639294897826627677**, executable SHA-256 **1935A05C9DB6D468E34E0055014A4A99C1B5AFCEB1695884E24600F5C20A4BE8**. Both reused the SHA-checked guest reader **B8A725E6A9CE663C36CB836681ED660261B07FDA4118A0167262E92131B2373E**. This is a new process epoch; do not reuse its PID or addresses as current identity.

- Smoke run `fdad76d87c894a4ca080c6c270bc8365`: 3/3 samples, 09:45:27.850–09:45:28.983 UTC. Source report SHA-256 `F3AD02DCF3A1974A16FD43F841133A7433026B19C213A4DC6DA5E99238999163`.
- Run `5e652415e9914e0984cde21ad11fce2b`: 30/30 samples with 2,000 ms requested delay, 09:47:07.264–09:48:08.346 UTC. Measured first-start-to-last-end acquisition span **61.0816268 s**, maximum start gap **2.1387307 s**, maximum read **113.7881 ms**. Source report SHA-256 `FB43DEEF283529E71DACB14812969DF54680ABE331A448A00FDC0D2079173683`.

Original `summary.json` and `samples.json` for each run are under `artifacts/native-current-sampler-20261105/runs/lab2/<run-id>/`. Both reports show unchanged candidate XYZ `(7182.075, 821.2716, 3135.4204)`; no movement was performed. The measured cadence is an acquisition property over this interval, **not** proof that the candidate is passively refreshed player position, a changed-state correlation, or an eight-minute continuity qualification.

The host report validator now requires at least two samples for a cadence claim, rejects overlapping monotonic read intervals, and records the acquisition span. The correction received elevated review; focused host tests passed **10/10**, and focused native reader tests passed **8/8**. The native sampler's existing duration limits were not expanded.

Next, assess the independent [typed inline capture](../reference/typed-inline-capture.md) and [typed-wire inspection](../reference/typed-wire-snapshot.md) route using freshly established producer, process and source prerequisites. Complete advancing frames and same-unit correlation are needed; a marker alone is not a qualified reference. Do not bypass the bind or input restrictions. The subsequent [both-lab tools inventory](lab-discovery-tools-2026-11-06.md) completed separately; it does not change the native semantic limitations.
