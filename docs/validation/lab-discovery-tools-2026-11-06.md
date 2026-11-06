# Both-lab discovery tool inventory — November 6, 2026

Fresh authenticated inventory completed at 04:51 EST on both labs. No diagnostic tools were launched, software installed, game input sent, or VM/game restarted. Existing developer CLI version probes were executed.

## Verified portable files

All 20 checked files (x86/x64 variants of ten families) under `C:\Tools\Sysinternals` have matching SHA-256 across both labs, with zero metadata-read errors. File presence/version/hash is not runtime acceptance.

| Tool | Lab 1 version | Lab 2 version |
| --- | --- | --- |
| procmon64.exe | 4.13 | 4.13 |
| procexp64.exe | 17.21 | 17.21 |
| procdump64.exe | 12.02 | 12.02 |
| handle64.exe | 5.0 | 5.0 |
| listdlls64.exe | 3.3 | 3.3 |
| vmmap64.exe | 3.4 | 3.4 |
| rammap64.exe | 1.63 | 1.63 |
| sigcheck64.exe | 2.93 | 2.93 |
| tcpview64.exe | 4.19 | 4.19 |
| autoruns64.exe | 14.3 | 14.3 |

## Baseline and differences

Both labs successfully probed Git 2.56.0.windows.4, Python 3.14.10/pip 26.2.2, .NET SDK 10.0.403, Node 26.13.0/npm 11.20.0, PowerShell 7.6.9 and WinApp CLI 0.7.1. VMware Tools is running. Guest SDK 10.0.403 does not satisfy this repository's pinned SDK 10.0.302 by itself. SSH executable presence still has a failed version probe; SSH readiness is unverified.

Lab 1 returned 65 installed-app records and 36.10 GiB free; Lab 2 returned 62 records and 47.93 GiB free. Neither application nor registry enumeration cap was reached. Lab 1 records include Notepad++ 8.9.8.1, RipGrep MSVC 15.2.0 and Codex CLI 0.161.0; these records were not found in the checked Lab 2 registry locations. These are metadata observations, not executable checks or exhaustive absence claims.

## Proposed discovery uses

Prioritize VMMap for process-memory layout and allocation context, Process Explorer/ListDLLs for module context, and Handle for resource ownership. Process Monitor can diagnose file/registry/process activity when a specific failure warrants a bounded capture. RAMMap is useful for guest-wide memory pressure, not identifying player-field semantics. These are proposed uses, not operations executed here. Microsoft describes these capabilities in its [process utilities reference](https://learn.microsoft.com/en-us/sysinternals/downloads/process-utilities) and [utilities catalog](https://learn.microsoft.com/en-us/sysinternals/downloads/).

Continue using the existing exact-build RR2 reader for native field acquisition and the host REA installation for static analysis. Tool availability does not grant debugger, dump, kernel-driver or game-input authority; choose applicable read-only modes after checking their behavior. The immediate semantic question still needs independent advancing same-unit API evidence; installed utilities alone cannot establish it.

## Coverage, reproduction and evidence

Run `C:\Python314\python.exe -B scripts\lab_software_inventory.py --lab all` from the repository. The reusable inventory now reads explicit Sysinternals filenames and up to 128 application names/versions/publishers across three uninstall roots (up to 1,024 keys per root). It does not enumerate every portable folder, Store package, Python package or npm package. Retained scope flags expose truncation. Reports are bounded to 256 KiB.

Original reports: `artifacts/lab-software-inventory/20261106T095124Z-a2449395/`.
- `lab1.json` SHA-256 `8508b9e4e434f18cc701b635817d2f3b7700b3a27482cd466381ba8be3a67f75`.
- `lab2.json` SHA-256 `a9e221f6d144dff94bae0723c1ae1e20480d8e95967041f74833aedcc2379677`.

Validation: 16 focused software inventory/setup tests passed, PowerShell syntax parsing passed, elevated code review approved. Native sampler correction separately passed 10 Python tests and 8 focused native tests; no full-repository suite claim.
