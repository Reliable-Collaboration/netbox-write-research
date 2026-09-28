Direct REST MCP spike journal
=============================

2026-09-28 — Objectives and design

- User requested a separate, runnable spike with its own README: agent writes, guaranteed observability, and a clean undo path.
- Architecture: agent → this MCP server → NetBox REST API. No upstream MCP server, SDK repair, or proprietary service in the write path.
- Guarantee boundary: durable intent, previous values, and inverse before dispatch; conditional writes; explicit uncertain outcomes; conflict-safe inverse. Unconditional reversal despite external edits/deletion or destroyed storage is impossible via REST. The README will state the assumptions, tested scope, and refusal behavior explicitly.
- Scope chosen to make reversibility enforceable: device description, serial, and status updates. Arbitrary creates, deletes, relationships, unique asset tags, and arbitrary REST calls are excluded before dispatch.
- Improvements over the first prototype: one integrated agent-facing interface, idempotency keys, pre-write recovery evidence, explicit no-op handling, global process locking per journal, immutable event history, independent export/backup, and resumable task compensation.

2026-09-28 — Working integrated path and optimistic concurrency

- User explicitly agreed to optimistic concurrency and person-visible warnings for changes edited again before undo.
- Built a standalone Python/stdin-stdout MCP server exposing edits, task/object history, reconciliation, undo, and observability. It has no runtime dependency on the first spike's MCP adapters.
- Created a non-superuser NetBox identity with view/change permissions constrained to two new synthetic devices, plus read access to native change history. The server independently allowlists the same device IDs and writable fields.
- Initial direct-REST smoke test succeeded: description A→B, durable native evidence correlation, then inverse B→A. Both original and corrective operations remain in the journal.
- Added write-ahead inverse capture, explicit no-op records without PATCH, stable operation-key replay, append-only evidence with integrity checks, and conflict warnings including ABA detection.
- Live acceptance suite is running against the existing isolated lab. It tests actual stdio MCP traffic, process death, concurrent processes, storage/archive failures, task compensation, and backup-based recovery.

2026-09-28 — Acceptance tests and demonstration

- First suite: 22/22 passed. Expanded suite: 28/28 passed, including native permission boundaries, post-commit archive loss, missing historical evidence, actor correlation, scalar restoration, and instance-lineage rejection.
- Standalone `demo.py` passed through actual MCP stdio: read → task → direct REST write → recovery bundle → preview → inverse. The fixture returned to its initial values. Transcript saved in evidence.
- Added a final retry hardening: the same undo key now returns its original failed/successful receipt without creating a new corrective task or mutation. A task compensation that died before dispatch can resume under a new attempt key after reconciliation proves that attempt was never sent.
- The final 30-case suite is running. Outcomes and artifacts will be linked from RESULTS.md.

2026-09-28 — Final acceptance complete

- Final suite passed 30/30 on NetBox 4.6.10: `evidence/run-20260928T091918/results.json`.
- Stable undo keys now preserve original outcomes, including definitive failures. Resuming a task after a pre-dispatch crash creates a new attempt only after reconciliation establishes the old attempt was not sent.
- RESULTS.md links actual MCP transcripts, the conflict warning for a person, task compensation, runtime details, and the full test matrix. README documents the objectives, optimistic-concurrency contract, tool interface, run commands, and operating assumptions.
- Scope remains deliberately bounded: three device fields, one stdio identity, durable local journal plus retained native evidence. No create/delete/relationship APIs or force-undo are exposed.
