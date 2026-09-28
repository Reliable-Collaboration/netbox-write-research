Hands-on findings: autonomous NetBox edits and recovery
=======================================================

Executed 2026-09-28. Read the [build journal](../JOURNAL.md) for the investigation, including failed tests and corrections; use the [lab instructions](../lab/README.md) to reproduce it. The [downstream guidance](../guidance/agentic-netbox-edits.md) is the implementation handoff.

**Recommendation.** Start with a durable write coordinator plus native/archived history and a bounded deterministic recovery service. The patched SDK is the most useful broad MCP integration candidate tested; nbox is attractive when its narrow operation set fits. Zenix offers simple CRUD but needs an extension for the concurrency/receipt contract used here. A transactional NetBox plugin is justified if every command—including no-ops and retries—must have an atomic durable receipt. Do not switch databases for this requirement.

**What ran.** Rootless Podman 5.7.0; isolated NetBox 4.6.10 with PostgreSQL 18 and Valkey 9.1; a separate restored database upgraded to NetBox 4.7.1; Python/Node MCP candidate containers; the nbox v0.14.1 release binary; a local CPU model. Existing containers belonging to the other project were untouched. Versions, source hashes, image digests, tools, and dependencies are recorded under [evidence](../evidence/candidate-builds.json).

| Candidate | Observed behavior | Integration consequence |
|---|---|---|
| SDK, original research commit | MCP initializes, but create/patch handlers raise `unexpected keyword argument active` | Cannot recommend that unmodified commit for writes |
| SDK, isolated local patch | Create/update/delete and invalid-choice handling work; stale If-Match rejected; HTTP status, ETag, and request ID exposed | Best tested fit for coordinator integration, conditional on the small patch |
| Zenix, research commit | Create/update/delete and invalid-choice handling work through its five-tool interface | Simple usable writer; write schema has no arbitrary precondition/header argument |
| nbox v0.14.1 release | Local MCP plan/apply status update works; consumed-plan replay rejected; stale plan preserves external edit | Strong bounded-write option; broad CRUD/graph recovery remains outside its tested surface |

The [original SDK failure](../evidence/runs/candidates-20260928T081738/results.json), [final comparison](../evidence/runs/candidates-20260928T083633/results.json), [nbox stale/replay results](../evidence/runs/nbox-20260928T084003/results.json), and [SDK recovery integration](../evidence/runs/sdk-recovery-20260928T083640/results.json) support these conclusions. The SDK patch filters a captured closure variable out of forwarded arguments; its upstream source is Apache-2.0. A separate failed patched run came from our read-only config-directory mount preventing SDK cache creation; corrected to a read-only config-file mount. These failures are not conflated.

**Deterministic results.** Eight [NetBox baseline tests](../evidence/runs/baseline-20260928T082817/results.json) and thirteen [recovery integration tests](../evidence/runs/recovery-20260928T083739/results.json) passed. The SDK bridge additionally demonstrated correction through MCP and protection against an apply-time race. Replay/export tests recovered a late-visible record, tolerated reordered input and interruption, detected missing native rows, and read an exported archive offline. These tests have different scopes; they are not 21 independent proofs of universal recovery.

| Requirement | Demonstrated | Boundary |
|---|---|---|
| Actual previous values | Native before/after values for tested changes; request and actor attribution | Not every model/plugin tested; successful no-ops can have no change record |
| Indefinite retention | Effective `CHANGELOG_RETENTION=0` | No long-duration housekeeping/capacity soak |
| Safe field correction | Description/serial/asset-tag/status inverse; null and empty preserved; unrelated later serial retained | Structured fields and relations are explicitly unsupported inverses |
| Concurrency | Stale ETag, simultaneous writers, apply-time race, same-field and ABA conflict handling | Exact tested detail endpoints; not generic bulk/plugin guarantees |
| Outcome uncertainty | Dropped response after actual IP creation reconciled by marker; hard process exit before/after dispatch handled durably | Marker cannot establish an unrecorded no-op or supply exactly-once execution |
| Partial task | Successful and failed operations recorded separately | No generic dependency-ordered task rollback/resume |
| Retained archive | Deduplication, late/reordered replay, corruption detection, outage reporting, fail-closed option, offline export and SQLite backup | Single-process full scans; no independently privileged off-host store deployed |
| Delete recovery | Interface deletion also deletes its assigned IP; recreation produces a different ID | No automatic graph reconstruction; creates/deletes classified manual |
| External effects | Worker delivered both mistaken and corrective webhook events | No automatic downstream compensation |
| Permissions | Read-only token and view-only object permissions reject writes | Broad candidate tests use lab administrator; per-tenant production policy not built |

**Surprising findings that change the design.** A 200 response does not guarantee a native ObjectChange row: a no-op can be omitted even when a changelog message was supplied. The journal must retain successful receipts and distinguish evidence-pending from proven no-op. The prototype conservatively reports missing evidence; a production system should make this a first-class outcome rather than silently treating it as failure or success-with-history.

Native snapshots are not API payloads. The tested tag snapshot contains slugs, while the write used IDs. Boolean false and null were preserved. Reversing arbitrary snapshots blindly is therefore unsafe even when the previous values exist.

The [restore/upgrade drill](../evidence/runs/upgrade-20260928T082913/results.json) retained all original values in 149 history records, but one device-role snapshot gained tree fields. Exact immutable-payload comparison initially failed; the [recorded difference](../evidence/runs/upgrade-20260928T082913/snapshot-differences.json) explains why. Preserve original archived bytes and version metadata; compare semantic compatibility explicitly after an upgrade. The same drill ran scalar recovery on 4.7.1, then removed native history only from the disposable restored database and verified the independent archive/backup remained readable.

The external journal has a genuine transaction boundary. A durable operation marker survived the tested response-loss case, but it is not server-side deduplication. The prototype does not blindly retry missing outcomes. If the downstream requirement is zero ambiguity for every command, add an in-transaction plugin receipt with a unique operation key and request fingerprint; that extension was not built here.

**Actual agent behavior.** The [final validated trials](../evidence/runs/agents-20260928T083816/results.json) used Apache-2.0 Qwen2.5-1.5B-Instruct locally through llama.cpp, five scenarios × three repetitions. All 15 ended with the expected data state, but **0/15 passed the complete workflow-and-reporting criteria**. The model skipped evidence inspection, repeatedly requested refused corrections, and omitted operation IDs. One uncertain-operation explanation falsely claimed commitment. One injected-description trial falsely claimed a device had been deleted, although the supported corrective update preserved it.

This demonstrates the value of bounded deterministic tools; it does not establish that the model is a reliable operator. The tool rejected unsupported/conflicted/uncertain corrections, while the model's prose could still be wrong. The downstream application should render authoritative outcome and evidence references directly from receipts, limit repeated calls, and independently evaluate its chosen model. The [model manifest](../evidence/model-manifest.json) records exact runtime/weight artifacts; prompts and tool transcripts are retained with each trial. Earlier exploratory runs and fixture errors are retained but excluded from this final count.

**Evidence quality and remaining work.** Earlier failed runs remain available, including a reused-IP fixture error and a weak no-op assertion corrected before the final recovery suite. Initial agent runs also reused a fixed create address; five unsupported-create scenarios were invalid and are excluded from acceptance conclusions. The final agent setup uses unique documentation-prefix addresses and asserts that intended creates actually committed.

The plan's broad investigation is implemented as working spikes, not as a finished production service. Remaining work includes a transactional receipt plugin if required, automatic simple-create/deleted-graph recovery, generalized task compensation, multi-user service authentication, independent archive permissions/off-host backup operations, incremental-export scaling and long-duration retention tests, and broader endpoint/model/role/version coverage. No independent human operator study was performed. Application recovery is tested; full production disaster recovery and point-in-time recovery are not established by a local copied database.

Primary components and captured Python/Node dependency license metadata use open-source licenses. This deployment requires no paid model/API product. Full base-image/transitive license review and redistribution compliance remain deployment tasks. The harness is MIT; third-party code and the SDK-derived patch keep their upstream licenses.
