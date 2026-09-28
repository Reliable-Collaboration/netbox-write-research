Direct-write MCP spike results
==============================

Executed 2026-09-28 on the isolated NetBox 4.6.10 lab. **30/30 live contract tests passed.** [Final test report](evidence/run-20260928T091918/results.json). The [runtime manifest](evidence/runtime.json) records the actual environment.

The agent connects to this server, and this server makes conditional REST PATCH requests directly to NetBox. No upstream MCP server or SDK adapter participates. The [MCP transcript](evidence/run-20260928T091918/mcp-transcript.json) demonstrates the integrated interface. A separate [runnable demo transcript](evidence/demo-20260928T091726.json) records an actual edit and inverse restoring the initial values.

| Objective | Evidence | Result |
|---|---|---|
| Agentic edits | Actual stdio MCP read/task/edit/undo; restricted native identity; field/device allowlists | Implemented for device description, serial, and status |
| Observable outcomes and retained previous values | Intent/inverse persisted before PATCH; native correlation; explicit no-op, failed, uncertain, and unverified states; backup and integrity checks | Passed within the documented storage/history assumptions |
| Clean optimistic undo | Field-level inverses, unrelated-field preservation, same-field/ABA warnings, stale ETag and apply-time race rejection | Applies safely or returns a warning; no force-overwrite |
| Multi-operation recovery | Reverse-order repeated-field undo, partial/conflicted task reporting, process-loss reconciliation and resume | Passed; compensation remains non-atomic |

**The person-visible conflict behavior is demonstrated**, not just documented. In [this captured warning](evidence/run-20260928T091918/conflict-warning.json), an operation changed description A→B, another writer changed it to C, and undo returned `conflicted` with expected B, current C, inverse A, and the relevant history references. C was preserved. A newer unrelated serial edit was preserved while the description was restored in another test.

The [task-undo result](evidence/run-20260928T091918/task-undo.json) demonstrates A→B→C being compensated C→B→A as two new recorded corrections. Repeating the task undo does not duplicate corrections. A conflicting earlier operation stops a task after any already-completed corrections and reports partial progress.

**Acceptance coverage.**

| Cases | Tests |
|---|---|
| 01–03 | Actual MCP round trip; stable write-key replay across restart; different-payload key rejection; observable no-op without PATCH |
| 04–09 | Unrelated edit preservation; person-visible same-field and ABA conflict warnings; stale initial read; race during undo; server HTTP 412 at the last write boundary |
| 10–14 | Archive outage blocks dispatch; injected journal disk-full error prevents PATCH; actual commit followed by injected response loss; hard process exits before dispatch/after commit; unresolved dispatch blocks further device edits |
| 15–17 | Repeated-field task compensation; partial recovery stops at a conflict; task undo resumes after a hard process exit following commit |
| 18–22 | Unsupported fields/device scope; invalid status receipt; backup-based recovery; append-only evidence and projection-integrity checks; two processes sharing one idempotency boundary |
| 23–28 | Real NetBox permissions deny outside-scope edits and deletes; missing archived source record blocks undo; post-commit archival outage stays visible; actor matching; serial/status restoration; wrong instance lineage rejected |
| 29–30 | Retrying a failed undo key returns its original receipt; task undo resumes after a pre-dispatch crash without duplicating a correction |

Several failure tests deliberately inject errors at controlled boundaries: the disk-full test raises SQLite's error before the intent transaction commits; the response-loss test commits against real NetBox before suppressing the receipt; the missing-history test hides a real native row from the exporter. The crash tests use actual child processes terminating with `os._exit`. These are bounded fault-injection experiments, not hardware power-loss or long-duration durability certification.

The complete native-history archive and append-only local journal have no expiry mechanism. That supplies indefinite logical retention in the spike, not an off-host backup service. Native snapshots, events, and operations are preserved in each test's JSON evidence; private SQLite/config files remain under ignored `.state/`.

**Limits carried into the recommendation.** A REST client cannot atomically commit its local ledger and NetBox's transaction. If a process dies after recording dispatch and no matching native change can be found, the tool reports uncertainty and blocks further edits to that device. It never turns absent history into proof of failure. Original values remain available for guided investigation.

Field-level historical conflict detection assumes complete native history, in addition to the ETag check that protects the final write. If an environment cannot provide complete history, it cannot claim this spike's field-aware/ABA guarantee. Native pruning, object deletion, changed history serialization, unsupported versions, or unresolved operations block automatic recovery rather than weakening the checks.

The tested service is a single-user stdio tool for a small allowed field/model set. This run does not establish generalized create/delete/relationship recovery, independent archival administration, production alert delivery, multi-tenant authentication, or LLM reliability. No new model-behavior claims are made: these acceptance tests exercise the MCP contract and enforcement directly.
