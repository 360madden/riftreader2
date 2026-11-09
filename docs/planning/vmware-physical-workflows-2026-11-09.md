# VMware and physical RIFT workflows

Date: 2026-11-09
Status: accepted implementation direction; this commit records the plan only.

## Outcome

One RR2 discovery-and-retrieval engine with two explicit execution workflows:
VMware guests and physical Windows. Start with screenshots and one existing
retrieval operation. Deliver a working result after each small change.

Keep the current repository, .NET module boundaries, controllers, readers,
credential handling, and evidence contracts. Do not create another engine,
service, scheduler, general framework, or competing console controller.
Movement remains a controlled experimental capability; this change does not
expand gameplay-automation scope or relax existing action authority.

## Reuse what already exists

- `scripts/control_host.py`: `/api/capture` forwards capture to the guest agent
  and retains the result; this is not VMware-native console capture.
- `scripts/control_client.py`: validated capture delivery.
- `scripts/inspect_lab2_workflow.py`: existing coordinated Lab 2 inspection,
  temporary access, identity checks, and verified release.
- `scripts/inspect_lab2_tool.py`: combined execution and image-delivery entry
  point; see `docs/workflows/lab2-tool-handoff.md`.
- `scripts/quick_review_capture.py`: small SHA-bound visual preview; original
  capture metadata and review-age rules remain authoritative.
- `scripts/vmware_guest_session.py`: established VM-specific cached login path.
- `scripts/vm_console_native.py`: separate VMware VNC-console helper, not the
  default entry point while a managed host owns the console reservation.

The 2026-11-08 17:22 entry in `docs/status.md` records healthy managed hosts
intentionally holding both console mutexes. That is historical evidence, not
fresh ownership proof. A standalone helper returning `controller-busy` does not
justify stopping a host, forcing a mutex, or assuming a foreign owner.
The current mutex error mapping also needs to distinguish a wait timeout from
an API failure before diagnosing contention.

## Thin workflow boundary

Extend existing target configuration and entry points rather than duplicating
them. Pin each operation to an explicit target and expected owning host.

| Concern | VMware | Physical Windows |
| --- | --- | --- |
| Identity | Expected host, exact VM identity, current guest RIFT process/build | Expected host, current RIFT process/start/build and window when needed |
| Data access | Existing reader inside the selected guest | Applicable shared reader functionality executed locally |
| Capture | Coordinated guest-agent capture first; native VMware console separately qualified | Existing Windows capture for the exact physical RIFT window |
| Authentication | Existing VM-specific credential source only when needed | No VMware credential lookup |
| Experiments | Existing per-lab controller and scoped access | Existing physical desktop ownership and target-specific authority |
| Output | Common RR2 result tagged with target, source, capture method, time, and qualification | Same contract, without pretending capabilities have equal readiness |

Share locating recipes, field definitions, analysis, and validation. Never share
live addresses, process IDs, approvals, or readiness across targets.
No silent fallback from a lab to physical RIFT, from Lab 1 to Lab 2, or between
AMD-DESKTOP and LEGION. Verify the endpoint host; its friendly name is not proof.

## Implementation order

### 1. VMware observation: first useful result

Use the existing coordinated controller capture path for explicit Lab 2.
Return an actual inspected image, capture origin, identity, timings, and a
specific failure if unavailable. Reuse healthy services and saved credentials;
do not launch a competing standalone console helper. Extend the proven route
to Lab 1 without duplicating its implementation.

Acceptance: a fresh image from the requested lab, no game input, verified
release of temporary access, and useful failure details. The persistent host's
normal console reservation may remain held. Do not claim native VMware capture
from guest-agent or host-window output.

### 2. Physical observation

Provide the equivalent operation for an explicitly selected physical host.
Use its existing Windows capture path with fresh process/window identity.
Keep VMware endpoints, VM credentials, and VM readiness out of this path.

Acceptance: correctly attributed physical RIFT pixels; unavailable RIFT reports
not-running rather than another target's image; stale identities are rejected.
Do not steal foreground while Joey uses the PC without the applicable desktop
ownership. A failed VM must not block independent physical observation.

### 3. One existing retrieval operation

Route one already-implemented RR2 retrieval through the two workflows.
Preserve its source, candidate/qualified labels, exact-build and freshness
requirements. Reuse the current reader implementations and locating recipes.

Acceptance: current data for the selected target or an exact unavailable reason;
no stale cached value promoted to live data and no cross-target addresses.
Then use the workflow for discovery. Migrate other operations only when useful.

## Fast path and ownership

- Check prerequisites for the requested operation, not every installed tool or
  service. A screenshot must not trigger an unrelated memory scan, addon sync,
  or full lab inventory.
- Reuse healthy controllers. Start/recover only necessary dependencies within
  existing authority; never hide restarts, queue resets, or input in a read.
- Keep cached-source lookup in the existing authentication code. Saved entry
  presence and successful authentication are different results. No credential
  copies, recreation, or secrets in command arguments, reports, or Git.
- Request supported work through the current controller. Report its identity
  and operation when known; otherwise report ownership as unknown.
- Keep per-VM console access distinct from shared host-desktop access. VMware
  host-window fallbacks and physical RIFT can compete for AMD-DESKTOP's focus
  and input; both must use the existing shared desktop coordination.
- Combine deterministic run/completion/image delivery where possible. Keep
  decisions requiring visual interpretation as separate decisions.
- Use a compact preview by default and the original for fine text. Preserve
  capture provenance and original review expiry; a file hash alone is not
  evidence of fresh pixels or game-state semantics.
- Measure acquisition, transfer, and review delay separately. Use bounded
  waits/retries; do not retry denied access or discard the original error.
- Persist stable configuration, not permanent green readiness. Revalidate
  relevant identity and freshness at the operation boundary.

## Native VMware capture and optional diagnostics

Native VMware capture remains a separate bounded acceptance test through the
established console ownership/handoff route; do not disrupt a healthy controller
just to try another screenshot backend. Do not equate `vmrun captureScreen`,
VMware VNC-console capture, guest-agent capture, and host-window capture.

The earlier unauthenticated `vmrun` rejection did not test saved credentials.
The standalone console attempt stopped at mutex acquisition, before testing
console authentication or pixels. Two WinApp host-window captures succeeded,
but that does not establish unattended/background reliability.

Adopt a native backend only after real target-correct image tests in the
foreground, covered/inactive, and minimized conditions relevant to use.
Until then retain the working, accurately labelled route.

Sysinternals is optional targeted diagnostics, not a workflow dependency.
Guest RIFT process diagnostics run inside that guest; host VMware process
inspection is not a substitute. Verify installations per machine before use.

## Small delivery rules

Make focused changes, run the relevant tests, try the authorized real operation,
and commit the useful result. Preserve concurrent work. No broad refactor,
mandatory full-suite run, new handoff package, or documentation expansion as a
default gate. Wrong-target, stale-identity, ownership, and cleanup protections
remain in force.

First implementation target: one reliable Lab 2 screenshot request through the
existing managed controller, with fast image delivery and truthful diagnostics.
