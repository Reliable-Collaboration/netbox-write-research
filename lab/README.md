Reproducible spike lab
======================

Requires Python 3.11+ and rootless Podman. No paid services. This is an experimental lab for synthetic data, not a deployable production recovery service. Host ports 18780 (NetBox), 18781 (local model), and 18782 (restored/upgraded NetBox) bind to loopback.

Run from the repository root, sequentially:

```sh
python3 lab/lab.py up
python3 lab/lab.py ready
python3 lab/lab.py bootstrap
python3 lab/seed.py
python3 lab/identities.py
python3 lab/build_candidates.py
python3 lab/compare.py
SDK_PATCHED=1 python3 lab/compare.py
python3 lab/test_baseline.py
python3 lab/test_recovery.py
python3 lab/test_sdk_recovery.py
python3 lab/upgrade.py
python3 lab/model.py
python3 lab/agent_eval.py
```

`ready` can take several minutes during initial migrations. Inspect `podman logs nbai-spike-netbox` if it times out. Run `bootstrap` only after readiness. The upgrade script needs the pinned 4.7.1 image (it pulls it if absent). Model startup is separate because it downloads about 1 GB of weights and uses up to 3 GB RAM; wait for `/health` on port 18781 to return 200 before evaluating. Agent trials can take several minutes on CPU. The SDK builder downloads Python dependencies and preserves an unchanged image plus a separately patched image.

Tests share fixtures: **do not run the recovery suites and agent evaluations concurrently.** Historical run directories include failures encountered while developing the harness; use the findings document for the final results and explanations. Scripts return nonzero on deterministic test failures. Agent evaluation always saves every result; inspect its result file for strict workflow failures.

Private credentials, databases, source checkouts, build logs, and weights live under ignored `.lab/` (mode 0700). Do not copy this directory into the downstream project. JSON evidence under `evidence/runs/` contains only synthetic inventory and redacted protocol/HTTP data; no Authorization headers are recorded. Keep the existing `lab/images.lock.json`, candidate source hashes, dependency lock, runtime image manifest, and model manifest for repeatability. Upstream source licenses remain applicable.

The deployment uses generated lab-only credentials. Ordinary candidate tests intentionally use a lab administrator to avoid conflating coverage with permissions. Separate permission tests verify read-only tokens and a view-only user. A production integration must use restricted service identities.

To reset known device fields while retaining the investigation history:

```sh
python3 lab/seed.py --reset
```

This is a logical fixture reset, not a database wipe: ancillary interfaces, IPs, custom fields, and historical records remain. Tests use unique names or explicitly initialize their relevant fields. For a clean database start, create a separately named project or remove only this project's containers and DB volume after stopping it; then create new journals/instance lineage. Do not reuse an existing journal against a rewound database.

To stop all lab services and preserve data:

```sh
python3 lab/lab.py stop
```

No global cleanup/prune command is used. All lab containers/networks/volumes use `nbai-spike` names and the project label `io.netbox-ai-spike.project=nbai-spike`. Upgraded databases are separate named databases within the lab PostgreSQL container, never the original or another project's database.

The recovery MCP server can be launched by any stdio MCP host:

```sh
python3 lab/recovery_mcp.py --journal .lab/example-journal.sqlite
```

Populate a journal with `Coordinator.begin()` and `Coordinator.execute()` from `lab/recovery.py`. The MCP surface deliberately exposes evidence, preview, correction, and observability only. `lab/sdk_bridge.py` demonstrates routing coordinator writes through the patched SDK MCP while using REST for independent history reads. `lab/test_sdk_recovery.py` is the working integration example.

Automatic recovery is limited to device description, serial, asset tag, and status updates. It refuses structured fields and graph deletion. It leaves missing committed evidence and transport uncertainty visible. A fresh preview is computed inside apply; callers cannot submit arbitrary inverse payloads. A repeated correction request returns its existing receipt. Failed corrections require investigation; task-wide dependency-ordered rollback and automatic retry/resume are not implemented.

SQLite with full synchronization is sufficient for this single-process spike. Exported JSON and SHA-256 files are portable evidence; hashes are not signatures or protection from a privileged rewrite. A SQLite backup is an independently restorable file in the lab, not an off-host production backup. The archive rescans the full native changelog; scalability and independently privileged storage need production engineering.

Additional focused checks:

```sh
python3 lab/test_nbox.py
python3 lab/test_archive.py
python3 lab/license_inventory.py
python3 lab/journal_cli.py --journal .lab/example-journal.sqlite summary
```

The primary UI login is `spike-admin`, with the generated `admin_password` in `.lab/secrets.json`. This is solely for the isolated synthetic lab.
