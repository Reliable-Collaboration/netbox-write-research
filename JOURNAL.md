Build journal
=============

2026-09-28 — Started hands-on implementation

- User authorized execution of the spike plan and requested this journal.
- Checked Podman: 5.7.0, rootless. Existing containers belong to another project and will remain untouched.
- Cached baseline images available: NetBox v4.6.10-5.0.2, PostgreSQL 18-alpine, Valkey 9.1-alpine, Node 24.21.0. Reusing images, not existing containers or data.
- Chose a Python standard-library host harness to minimize prerequisites (host Python 3.14; no uv, Node, or Cargo on PATH). Candidate runtimes will live in containers.
- Upstream netbox-docker 5.0.2 uses PostgreSQL 18 and Valkey 9.1. Podman adaptation will be tested directly. Actual image digests will be recorded.
- Plan: baseline → candidate protocol tests → archival/recovery failure tests → guidance. No runtime claims yet.

2026-09-28 — Lab and candidate builds

- Added `lab/lab.py`: exact-name, labelled Podman lifecycle; private generated credentials; loopback port 18780; image digest lock; indefinite native changelog retention; Copilot disabled.
- SDK and Zenix built from the previously inspected source commits, without source changes. Source archive hashes match the research manifest.
- Downloaded nbox v0.14.1 release binary and checked its SHA-256 against the published asset digest. Its release commit differs from the research snapshot; recorded explicitly in `evidence/candidate-builds.json`.
- Added a stdlib JSON-RPC MCP driver. This exercises actual stdio protocol calls, not surrogate REST calls.
- Caught a NetBox 4.6 token-model difference before bootstrap: legacy tokens use `plaintext` and `version=1`, not `key`. Bootstrap uses a disposable lab-only legacy token initially; token-version coverage will be reported honestly.

2026-09-28 — First runtime findings

- All three MCP servers initialize: SDK 17 tools, Zenix 5, nbox 13. Schemas saved in `evidence/*-tools.json`.
- Unmodified SDK CRUD fails with `unexpected keyword argument active`: closures forward `locals()` including the captured service object. Preserved failed run `candidates-20260928T081738`.
- Added a small isolated SDK patch (filter `active` from forwarded arguments). First patched attempt revealed a harness mistake: mounting the entire config directory read-only also prevented SDK HTTP-cache creation. Changed to a read-only config-file mount; preserved that failed run too.
- Corrected patched SDK run `candidates-20260928T082153`: create/update/delete, invalid status, and stale If-Match checks pass. Zenix CRUD passes; nbox local plan/apply status update passes without a separate human gate in our test host.
- NetBox 4.6.10 returns ETags and HTTP 412 for mismatches. Inspected installed viewset implementation: it rechecks preconditions under a row lock for detail updates/deletes.
- Verified `changelog_message` survives as native ObjectChange.message. This provides a durable operation marker even when the response/request UUID is lost. It is application correlation, not a tamperproof or transactionally deduplicated command log.
- Recovery prototype and 12 integration tests pass. Includes unrelated-field preservation, same-field/ABA conflicts, apply-time race, null restoration, dropped HTTP response after create, durable intent reopen, partial task, archive replay/outage/integrity checks, and backup restore.
- Scope boundary: automatic inverse currently covers selected scalar device fields. Creates remain observable but require assisted recovery; graph undelete is not implemented.

2026-09-28 — Expanded baseline and local model

- Two simultaneous updates using the same ETag produced one success and one 412. Same-model bulk validation failure left the other object unchanged.
- Native snapshots preserve false, null, tag slugs, and custom-field values. These are not uniformly REST-ready payloads (tag snapshot values differ from write IDs).
- Read-only tokens and a non-superuser with view-only object permissions rejected writes. Webhook capture saw both the mistaken update and the correction: compensation does not retract the earlier event.
- A first attribution test expected a history record for a no-op write and failed. NetBox can return 200 without a new change record when data and changelog message do not change. Revised the test to distinguish actual changes from no-ops. This is useful evidence for journal completeness requirements.
- Downloaded Apache-2.0 Qwen2.5-1.5B-Instruct GGUF at a pinned revision and started it locally with the MIT llama.cpp runtime on CPU. Runtime digest and weight hash recorded; no hosted model API involved.
- Upgrade image v4.7.1-5.0.2 does not exist. Checked upstream packaging version and obtained v4.7.1-5.1.1. Will restore a disposable database copy before upgrading it.

2026-09-28 — Integration, upgrade, and agent findings

- The selected patched SDK is now exercised behind the coordinator, not merely tested separately. MCP write → native archive → inverse MCP write preserved an unrelated serial edit. A later apply-time race returned a failed correction and preserved the concurrent edit.
- Corrected a weak assertion in the initial no-op test: a different change ID could previously mean `None`. The revised test explicitly verifies that a successful no-op can have no native change record and remains visible as evidence-pending. A changelog message alone does not force a record.
- Final expanded baseline: 8 tests passed, covering snapshots, simultaneous stale writers, structured values, bulk validation, deletion identities, actor attribution, permissions, and external webhook persistence.
- First upgrade test failed exact snapshot equality. Inspection showed one device-role record gained MPTT tree fields in 4.7.1. Saved the difference rather than suppressing it. Revised criterion checks preservation of all original values and separately records extensions.
- Restore/upgrade result: 149 pre-upgrade history records retained their original values, one snapshot extension, scalar recovery passed on 4.7.1. Deleted native history ONLY in the disposable restored database; archived history and its SQLite backup remained readable.
- Local model experiment 1: 15 trials (five scenarios × three repetitions), 0 strict workflow/reporting passes, 9 expected final states. Invalid combined tool names and repeated calls were common.
- Experiment 2 used an explicit workflow and JSON response schema: 0 strict workflow/reporting passes, 15 expected final states. It still skipped inspection, repeated refusals, and omitted evidence IDs. All transcripts and both failed strict evaluations are retained. This small model is not recommended as a reliable recovery operator.
- Added downstream guidance and agent instructions. The recommendation is to enforce inverses/preconditions and bounded execution in code and attach evidence IDs programmatically.

2026-09-28 — Final verification caught fixture reuse

- A repeated dropped-response test failed because its fixed IP already existed; the server returned 400, so it was no longer testing a committed response loss. Changed create fixtures to unique addresses within the documentation IPv6 prefix and kept the failed evidence.
- Audited the agent trials for the same issue. Five of the six earlier unsupported-create setups had failed creates rather than successful creates awaiting unsupported recovery. Their earlier aggregate scores are exploratory only, not valid acceptance results. Added setup assertions and am rerunning all 15 final-schema trials with unique addresses.
- Strengthened injection exposure: the final injected-text scenario includes the actual malicious description as explicitly untrusted input even if the model skips the history-read tool. Earlier final-schema runs skipped that tool, so exposure through history was not assured.
- Replaced the modeled SystemExit crash with child processes that use os._exit before dispatch and after the response. Reopening the durable journal distinguishes the unresolved intent from the reconciled committed operation.

2026-09-28 — Final deterministic checks and stronger deletion finding

- Final recovery suite passes 13/13, including actual hard process exits, unique-IP response loss, conservative no-op evidence handling, and both permissive/fail-closed archive outage modes.
- nbox focused tests passed: local plan/apply, consumed-plan replay rejection, and stale-plan rejection. Responses preserve external changes.
- Archive replay test used 260 observed native records: recovered a late-visible record, deduplicated reversed order, retained evidence through interrupted export, surfaced missing native rows, and verified a checksummed offline export.
- Effective retention was read from NetBox's runtime config and is 0, not merely present in an environment file.
- Inspected deletion evidence more closely: deleting the interface cascaded to delete its assigned IP address (GET returned 404), not just its relationship. The handoff now states that both objects and identity mapping require restoration.
- Generated a private UI password for the lab admin so the user can inspect the running instance. Credentials remain only in ignored `.lab/secrets.json`.

2026-09-28 — Completed handoff

- Final validated local-agent run `agents-20260928T083816`: all 15 intended setups verified; 15/15 expected final data states; 0/15 strict workflow/reporting passes. An uncertain operation was incorrectly described as committed, and one injection trial falsely claimed a device was deleted. Actual state remained protected by deterministic tools. These specific reporting failures are included in the findings.
- Final artifacts: executable Podman lab, source/image/dependency/model pins, three-candidate comparison, separate SDK repair, durable coordinator/archive, recovery MCP and CLI, deterministic tests, restore/upgrade drill, agent transcripts, guidance, and this journal.
- Verified all JSON parses, Markdown local links resolve, archived export hashes match, and no generated lab credentials occur in checked-in-content paths.
- Stopped the model, restored upgrade instance, and webhook capture to release resources. Primary NetBox, worker, PostgreSQL, and Valkey remain running for inspection on loopback port 18780. All data/evidence remains preserved; `lab.py stop` stops the remaining lab services.
- Explicit remaining scope: production archive administration/off-host backups, scalable exporting, transactional command receipts, broad graph/task recovery, wider endpoint/plugin coverage, and a more reliable agent runner/model. Those are downstream recommendations, not silently claimed as implemented.

2026-09-28 — Separate direct-REST MCP spike

- Built the requested independent spike under `spikes/direct-write-mcp/`, with its own README, journal, code, tests, and evidence.
- Agent-facing server performs NetBox REST writes directly; no writable upstream MCP server is required.
- User approved optimistic concurrency with a warning to a person for intervening changes. Implemented that contract with durable preimages, conditional writes, field-aware conflicts, idempotent corrections, and resumable task compensation.
- Final acceptance: 30/30 live contract tests passed. See the spike's RESULTS.md and JOURNAL.md for details and limits.
