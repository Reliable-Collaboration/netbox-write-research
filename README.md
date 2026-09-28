NetBox agentic write and recovery spikes
=======================================

An open-source research and executable lab project investigating trusted AI writes to NetBox, perpetual change history, observability, and evidence-based recovery. No human approval workflow is required for the tested scenario.

The newer [direct-write MCP spike](spikes/direct-write-mcp/README.md) implements one agent-facing server that writes directly to NetBox REST, with durable evidence and optimistic, conflict-aware undo. It lives in its own folder and does not depend on a writable upstream MCP server.

Start with the [runtime findings](research/spike-findings.md) and [downstream implementation guidance](guidance/agentic-netbox-edits.md). The [build journal](JOURNAL.md) records the investigation, failures, corrections, and evidence as work progressed.

- [Lab setup and test commands](lab/README.md)
- [Agent recovery instructions](guidance/agent-instructions.md)
- [Original spike plan](research/spike-plan.md)
- [Initial options research](research/options.md) and [audit/undo assessment](research/audit-and-undo.md)
- [Candidate source/build records](evidence/candidate-builds.json), [image pins](lab/images.lock.json), and [dependency licenses](evidence/dependency-licenses.json)

The lab compares three MCP candidates and implements a small durable coordinator, retained archive, recovery MCP interface, and conflict-aware inverse for selected device fields. It includes actual container deployments, dropped-response/process-death tests, a database restore/upgrade drill, and local-model recovery exercises.

The patched SDK is the leading broad integration candidate from these bounded tests. The untouched inspected SDK commit has a reproducible write-handler bug; both the failure and the isolated patch are retained. nbox supplies a narrower plan/apply option; Zenix supplies simpler general CRUD. Native history plus an archive does not provide universal undo or exactly-once execution.

This is a tested research prototype, not a production service. Graph restoration, transactional command receipts, scalable independently administered archival storage, and reliable model behavior remain explicit follow-on work. The original approval-oriented research remains available as historical context; the implemented spikes follow the later trusted-write requirement.

The primary lab UI is at `http://127.0.0.1:18780/` while running. Username: `spike-admin`; its generated password is in ignored `.lab/secrets.json` under `admin_password`. Run `python3 lab/lab.py stop` to stop lab services while preserving data. Existing unrelated Podman workloads are untouched.
