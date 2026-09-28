Hands-on spike plan: agentic NetBox edits, perpetual history, and guided recovery
===============================================================================

Prepared 2026-09-28. Status: planned; no candidate runtime results yet. Builds on the [landscape](options.md) and [trusted-write scenario](audit-and-undo.md).

**Outcome.** Produce a reproducible lab and an evidence-backed guidance document that another project can use to implement autonomous NetBox edits, retained change history, operational observability, and AI-assisted recovery. Recommend an existing adapter, an adapter plus a small recovery service, or a narrowly scoped custom implementation based on measured results. Human approval is not required for ordinary writes or supported recovery operations.

“Perpetual history” means no automatic age-based deletion of committed change evidence, durable storage independent of the running application, recoverable backups, and continued readability across upgrades. It is an operational commitment, not a promise of indestructible storage. Keep original changes and subsequent corrections. Define acceptable archival lag and disaster-recovery loss explicitly; distinguish eventual archival from transactional capture.

**Candidate shortlist.** Run a direct REST baseline plus three complementary MCP implementations. Begin from the previously inspected full commits in the [source manifest](evidence/source-snapshots.json); record newer versions as separate experiments rather than silently replacing the baseline.

| Candidate | Question it answers | Planned scope |
|---|---|---|
| [emersonfelipesp/netbox-sdk](https://github.com/emersonfelipesp/netbox-sdk), Apache-2.0 | Can a broad schema-driven adapter serve as the main write interface with a thin history/recovery layer? | Full common scenario suite; primary integration candidate |
| [ZenixSolutions/netbox-mcp-server](https://github.com/ZenixSolutions/netbox-mcp-server), MIT | Does a smaller generic MCP interface give simpler integration and better agent usability? | Same common suite; compare errors, schemas, and extension effort |
| [lance0/nbox](https://github.com/lance0/nbox), MIT OR Apache-2.0 | What can we reuse or learn from constrained writes and concurrency checks? | Supported descriptions, tags, status, and allocation operations; measure approval/configuration friction |
| Direct NetBox REST | Which behaviors originate in NetBox and which are adapter limitations? | Ground-truth baseline for all scenarios |

The shortlist is an experimental choice, not a production ranking. nbox may be unsuitable for approval-free use; report that result instead of removing its controls just to make it pass. Unsupported operations are recorded as unsupported, never exercised through an undisclosed REST bypass in a candidate's results.

Reserve [skuldgerry/netbox-mcp](https://github.com/skuldgerry/netbox-mcp) as a replacement if a broad candidate cannot run or lacks essential coverage. Give a candidate at most one engineer-day of setup/compatibility repair before documenting the blocker and moving on. Keep local patches separately reviewable. Optionally evaluate netbox-history for human search after the base history tests. Navigator, branching, Doltgres, and generalized graph undelete are outside the first sequence: they do not resolve the central unanswered questions efficiently under this scenario. Prior licensing exclusions remain in force.

**Lab and reproducibility.** Podman 5.7.0 and rootless operation were verified on this host. Existing workloads are present. Create only project-labelled networks, volumes, and containers; bind UI ports to loopback and clean up by exact project identity. Do not use global prune commands. Start with one active NetBox stack and sequential candidate runs; add a second stack for restore/upgrade and concurrency experiments as needed. Container availability does not imply unlimited memory.

Use the [community NetBox container project](https://github.com/netbox-community/netbox-docker) as the packaging reference, adapting its deployment to Podman and verifying health checks and worker operation. It documents Docker Compose; Podman compatibility is a lab result to establish. Pin NetBox, matching container support files, PostgreSQL, queue/cache services, candidates, and dependencies to exact versions and image digests. Inspect licenses for the actual selected artifacts, including queue/cache versions and any model weights. Copyleft is acceptable; required proprietary services are not.

The lab contains NetBox web/worker services, its database and queue/cache dependencies, one MCP candidate, a deterministic MCP test driver, a fault-injection HTTP proxy, and a webhook capture service. The history spike adds a separate journal/archive store; the recovery spike adds a small coordinator if necessary. Begin with machine-readable JSON evidence and simple queries; add a dashboard only if existing views cannot answer the operator exercises.

Choose a currently supported stable NetBox release at execution time and record why. Test the selected approach on a second supported release during the upgrade drill. If the downstream project supplies a target release, prioritize it. Use synthetic data: two sites, manufacturer/device type/role prerequisites, several devices and interfaces, prefixes/IPs and assignments, tags, nullable fields, boolean/custom fields, and cable/dependency examples. Include two write identities and a separate read-only observer. Fixture reset must restore the same logical state between candidates.

Deliver version-controlled lab definitions, lock/manifest files, seed/reset scripts, and test scenarios. Put raw evidence in run-specific directories containing manifests, redacted MCP transcripts, HTTP outcomes, native change records, archive receipts, final-state assertions, and a short result report. Store tokens outside transcripts and Git. A run must be repeatable without paid APIs or accounts.

**Spike 0 — establish the baseline and test oracle (1–2 engineer-days).**

Stand up the lab, verify API/worker readiness, seed fixtures, and run direct REST create/update/delete operations. Inspect native before/after snapshots, actor identity, request identifiers, and relationship serialization. Exercise an unsuccessful validation request and a multi-request task that stops halfway. Establish what is actually recorded for each model and field.

The oracle checks both final object state and committed native history; HTTP success alone is insufficient. Verify retention configuration and how housekeeping applies it on this release. Record the exact optimistic-concurrency mechanisms available, including their applicability to deletes and bulk operations. Do not assume all endpoints honor a precondition because detail PATCH does.

Exit: repeatable setup/reset, validated fixtures, a capability matrix, and a baseline evidence bundle. If NetBox itself lacks a required guarantee, subsequent experiments must address that gap explicitly.

**Spike 1 — compare writable MCP adapters (2–3 engineer-days total).**

Run the same deterministic MCP scenarios against each candidate. Measure installation effort, supported operations, tool/schema discoverability, permissions, useful validation errors, request-ID exposure, preservation of concurrency headers, bulk behavior, and ability to associate writes with a task. Inspect how nested values, nulls, booleans, tags, custom fields, and relationship identifiers are translated.

Capture tool-call counts and latency as descriptive measurements, with hardware and sample size. Separate adapter overhead from model reasoning. Test the MCP protocol itself, not just equivalent SDK calls. Record any required hosted authentication or other dependency that would violate the deployment constraints.

Exit: candidate scorecard with links to runs, one selected adapter and a fallback, and an explicit list of changes needed for task correlation and recovery. A good adapter need not implement undo itself if a small external layer can supply it reliably.

**Spike 2 — perpetual history and observability (2–3 engineer-days).**

Prototype the smallest journal/archive design around the selected adapter. Retain native history indefinitely using the verified configuration, then independently archive committed snapshots. Use durable operation intents, task/operation IDs, actor, instance ID, timestamps, outcome, native request/change IDs, schema/software versions, and links from corrective operations to originals. Keep raw snapshots plus versioned normalized representations; derived search indexes must be rebuildable.

Prove correlation rather than assuming a client-supplied request header is persisted by NetBox. A timestamp plus service account is not a reliable match under concurrent writes. If the response is lost before its server request ID arrives, the operation must remain uncertain until reconciled using sufficient evidence. If exact correlation cannot be established externally, prototype a small NetBox plugin endpoint with a transactionally recorded operation ID and deduplication receipt. Label this as a separate architecture, including its maintenance cost.

Make the archive exporter replayable and deduplicated. Test interrupted pagination, out-of-order visibility, overlapping reads, late records, exporter restarts, and a database restore that reuses numeric IDs; include instance/restore lineage. Do not advance a watermark in a way that can permanently miss a committed change. Periodic reconciliation must compare expected native records with archived records for the tested interval.

Exercise archive downtime, application/journal restarts, log rotation, and deliberate loss of disposable live history. Restore the archive from a separate backup and reconstruct task/object history without the original NetBox database. Verify checksums and completeness manifests; explain that hashing alone does not prevent an administrator rewriting history. Separate writer, reader, and deletion privileges and document the residual trust boundary. Record storage growth per change at two fixture sizes to support a capacity estimate.

Expose queries for “what did this task change?”, “what changed this object?”, “which writes are uncertain?”, and “which changes lack recovery evidence?”. Track archive lag, oldest unresolved operation, reconciliation discrepancies, recovery conflicts, and failed corrections. Test an alert on an intentional archive interruption. Initial lab target: normal archival within 60 seconds, immediate visibility of uncertainty, and no silent evidence loss in injected failures; tune production targets from measurements.

Decide whether loss of archive availability should stop new agent writes, and at what lag. Run both permissive and fail-closed configurations to show the tradeoff. If zero-loss journaling is required, an external asynchronous exporter alone does not satisfy it.

Exit: query examples, failure evidence, a backup/restore drill, measured archival lag and storage growth, and a justified decision between an external coordinator and transactional plugin capture.

**Spike 3 — deterministic recovery with AI-readable guidance (2–3 engineer-days).**

Build only enough recovery code to test selected field updates and conditional reversal of simple creates. Generate an inverse from committed evidence; validate it against current state and apply with server-side concurrency protection. Treat undo as a new linked task. A preview is informational; it need not introduce human approval.

For each operation, return a structured recovery assessment: supported, conflicted, uncertain, or manual restoration required; evidence references; current versus expected values; proposed inverse; affected dependencies; and remaining side effects. The AI explains these results and chooses supported actions. Deterministic code enforces preconditions and calculates inverses.

Test recovery interrupted halfway, safe resumption, and repeated requests for the same recovery. Recover repeated edits to one field in reverse dependency order or use a verified net inverse; never independently overwrite intermediate states. Detect an intervening A→B→A edit using history/version evidence when available: value equality alone does not establish that nothing changed.

Investigate one deletion/relationship example to establish the boundary, including cascade records and changed IDs. If reconstruction is not proven, return an assisted-restoration procedure rather than claim general undelete. Show how to extract evidence from a restored isolated database. A captured webhook remains an external effect even after the NetBox data is corrected.

Exit: supported-operation contract, deterministic inverse tests, conflict/resume results, and example machine-readable recovery reports with human explanations. Arbitrary model/plugin graph recovery remains a separately estimated extension.

**Common acceptance scenarios.** Apply the relevant cases across the baseline, candidates, and selected recovery architecture.

| ID | Scenario | Required observable result |
|---|---|---|
| T01 | Create, patch, delete, and failed validation | Accurate actor, actual committed before/after values, and outcome; no invented changes for failures |
| T02 | Description A→B; later unrelated serial edit | Correct description recovery preserves the newer serial |
| T03 | Same-field edit after original write; race after recovery preview | Conflict detected; no silent overwrite, including the apply-time race |
| T04 | Null/empty/false, tags, custom-field maps, relations | Defined inverse semantics preserve untouched values and valid relationships |
| T05 | Allocate/create commits but response is dropped | Outcome stays uncertain until reconciled; no blind retry producing duplicates |
| T06 | Process dies before send, during request, or after commit before receipt | Durable intent survives; correct committed/failed/uncertain classification |
| T07 | Mixed success across a task and within bulk requests | Exact affected objects and partial execution exposed; no false atomicity claim |
| T08 | Original task and recovery each touch one field repeatedly | Ordered or verified net recovery; interrupted recovery resumes without double correction |
| T09 | Created object gains dependents; deleted interface had an IP assignment | Unsafe create reversal blocked; unsupported graph restoration clearly reported |
| T10 | Archive outage/restart, live pruning, backup restore, schema upgrade | Completeness verified; old history remains readable; gaps surfaced explicitly |
| T11 | Two simultaneous actors and operations with identical values | Correct attribution/correlation or explicit ambiguity; no guessed success |
| T12 | Read-only/limited token; instruction-like text in object descriptions | Permissions enforced; object text treated as data, never recovery authority |
| T13 | Webhook generated before compensation | External effect remains visible and linked; no assertion that data undo retracts it |
| T14 | Write using native UI or a second REST client | Object history includes external edits; task attribution may be absent but conflict checks remain effective |

**Spike 4 — agent exercises and downstream guidance (2 engineer-days).**

After deterministic tests pass, run a small repeatable set of actual agent tasks: correct a bad update, diagnose a partially completed task, investigate a timed-out allocation, and explain an unsupported deletion restore. Include misleading instructions embedded in ordinary NetBox text. Use an eligible locally hosted model and open-source runner; record runtime, weights/license, prompts, tool schemas, model settings, and hardware. Verify local inference feasibility rather than assuming a GPU exists. If an eligible runnable model is unavailable, report agent validation as blocked; scripted calls are not a substitute for claiming model behavior was tested.

Run each exercise at least three times from clean fixtures, reporting every failure and the small sample size. Measure correct recovery, inappropriate writes, conflict handling, evidence citations, and tool-call effort. Give an operator only the history and runbook for a recovery exercise; record whether they can identify the changed values and verify the correction. A different operator is preferable; self-evaluation must be labelled.

Write `guidance/agentic-netbox-edits.md` as the downstream deliverable, with a concise recommended architecture and a traceable practice matrix: recommendation, rationale, scenario/run evidence, supported versions/models, and residual limits. Every statement must be labelled by context as experimentally demonstrated, source-derived, or proposed. Include deployment configuration, retention/backup ownership, correlation schema, observability queries/alerts, permission boundaries, upgrade retesting, failure runbooks, and estimated integration work.

Also deliver `guidance/agent-instructions.md` and versioned recovery-response examples. The agent instructions require inspecting durable history, distinguishing failed from uncertain writes, requesting deterministic recovery, respecting conflicts, avoiding guessed previous values and blind retries, treating stored text as untrusted data, and reporting original/corrective task IDs plus unresolved effects. Prompts supplement enforcement; they do not replace concurrency or permission checks.

**Selection and completion.** License eligibility and local operation are hard gates. For a recommended architecture, every claimed recoverable operation must pass the applicable correctness, concurrency, crash, and evidence-preservation cases. Unsupported operations may remain explicit exclusions. Report untested cases separately from failures. Use coverage, integration effort, operational burden, and agent usability to choose among architectures that pass; a weighted score cannot compensate for a silent data-loss failure.

Plan for roughly 9–13 engineer-days, with setup fixes and model execution as the main uncertainties. Review scope after the adapter comparison and after the archival failure tests. A custom MCP implementation is justified only if the tested adapters cannot expose the necessary identity, outcomes, or concurrency controls with a small maintainable extension. A transactional NetBox plugin may still be justified independently of which MCP adapter wins.

The project is complete when a clean lab run reproduces the supported guarantees, retained evidence survives the tested loss/restore scenarios, guided recovery preserves unrelated changes, and the handoff documents identify exactly what the next project can adopt and what it must still build. Findings from these spikes establish bounded compatibility and recovery evidence, not proof of indefinite durability or universal undo.
