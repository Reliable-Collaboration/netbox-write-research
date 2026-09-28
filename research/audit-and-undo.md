Scenario: trusted autonomous writes with retained history and recovery

Assessed 2026-09-28. This is an alternative to the approval-first scenario in [options.md](options.md). The open-source requirement remains unchanged.

**Recommendation: use a writable MCP adapter, NetBox's native change history, and a small task ledger with conflict-aware undo.** Approval queues, reviewer identities, branch isolation, and merge policy can leave the initial scope. Reliable reversal remains a separate capability from CRUD or history browsing.

NetBox's `ObjectChange` captures serialized before/after states for supported models, the action, actor, and request UUID. API responses expose the request UUID as `X-Request-ID`. Creates have an after-state; deletes have a before-state. These are application snapshots, not guaranteed round-trippable restore payloads. Source: [ObjectChange documentation](https://netboxlabs.com/docs/netbox/models/core/objectchange/).

Keep history for the required recovery horizon. The documented default is 90 days; `CHANGELOG_RETENTION=0` disables time-based pruning. Retention is not a backup: protect the database and independently archive history if recovery must survive loss of the live system. Source: [configuration](https://netboxlabs.com/docs/netbox/configuration/miscellaneous/#changelog_retention).

**What can be adopted now.**

| Component | Role under this scenario | Remaining gap |
|---|---|---|
| Stock NetBox Community | Object history and before/after inspection; normal API writes for corrective changes | No general automatic undo facility established by this research |
| `netbox-sdk` MCP (Apache-2.0) | Broad writes once mutations are enabled | Task grouping and reliable reversal |
| `skuldgerry/netbox-mcp` (Apache-2.0) | Generic and dedicated direct-write tools | Task grouping and reliable reversal |
| `ZenixSolutions/netbox-mcp-server` (MIT) | Compact schema-driven read/write interface | Same; stdio-only limitation |
| `nbox` (MIT OR Apache-2.0) | Useful narrow writes and concurrency handling | Limited write surface and no demonstrated general undo engine |
| `netbox-mcp-server-extended` (Apache-2.0) | Direct writes plus optional NetBox validation | Rolled-back validation does not undo a committed operation |
| `netbox-history` (GPL-3.0-or-later) | Search old snapshot field values, including deleted objects | Adds neither archival storage nor undo |
| Wikimedia `Revert` custom script (Apache-2.0 repository) | Existing experimental reversal implementation | Skips updates; limited relationship handling; compatibility work needed |

MCP licensing, source snapshots, and scope evidence are in [the original comparison](options.md). Their relative attraction changes: general writable adapters move ahead of approval-centric tools. Choosing an adapter still needs a compatibility test on the target NetBox. No inspected adapter has demonstrated complete automatic rollback for arbitrary models and plugins.

The [history plugin](https://github.com/averyhabbott/netbox-history) is a search layer over existing ObjectChange rows, useful for finding an old IP/DNS name after deletion. Its [0.1.1 package](https://pypi.org/project/netbox-history/) is classified alpha and documents testing through NetBox 4.6.x. Its license is eligible, but it cannot recover pruned history.

Wikimedia [deployed a basic revert script in 2024](https://phabricator.wikimedia.org/T310589). The [current inspected source](https://github.com/wikimedia/operations-software-netbox-extras/blob/master/customscripts/revert.py) explicitly skips updates, attempts recreation for deletes, and deletes objects to reverse creates. Foreign-key translation is limited, and recreated IDs/dependencies can break restoration. The [repository license](https://github.com/wikimedia/operations-software-netbox-extras/blob/master/LICENSE.txt) is Apache-2.0. Treat it as relevant prior work, not a universal production recovery service. The upstream [generic undo request](https://github.com/netbox-community/netbox/issues/9464) is closed as not planned. A separate [prefix-site reversal gist](https://gist.github.com/jsenecal/4175aa6fec46cb7a74ab43fcaaf3ec19) is narrowly targeted and has no explicit license shown in the inspected file, so it is not an adoption recommendation.

**Define undo as a new recorded corrective change.** Keep both the original mistake and its correction. Removing the original history would undermine observability.

| Original operation | Corrective operation | Conditions to establish |
|---|---|---|
| Update selected fields | PATCH those fields back | Current values/history are compatible; no newer same-field change is overwritten; restored values still validate |
| Create an object | Delete it | Object has not been repurposed and no unexpected dependents would be removed |
| Delete an object | Recreate it and restore relationships | Required objects/snapshots survive; identity remapping, uniqueness, and cascades are handled |
| Change a related object graph | Dependency-ordered corrections | Complete affected graph and side effects are known; partial recovery is explicitly represented |

Example: an agent changes a device description from A to B. Later someone changes its serial number. Undo should restore only the description, preserving the newer serial number. If the description subsequently changed to C, the undo operation should report a conflict instead of silently replacing C. Whole-object version checks are conservative but can reject harmless unrelated edits; field-aware checks can be more selective. Both need server-side concurrency protection at apply time, not just an earlier read.

For structured fields such as tags or custom-field maps, define whether the inverse operates on individual entries or the whole field. Missing, null, empty, and false values must remain distinct. Do not submit an entire changelog snapshot blindly as a REST payload: read-only, computed, relational, or version-specific fields require conversion. Preserve the relevant NetBox/plugin versions with exported records so old snapshots can be interpreted later.

**The smaller new tool has five responsibilities.**

1. Associate each AI task with its actual API requests and ObjectChange records. Store a server-generated task ID, purpose, target instance, actor, operation sequence, results, and failures. A task can span many NetBox request UUIDs.
2. Preserve recovery evidence. Use native committed change records as authoritative evidence where available; retain normalized inverse information for supported operations and immutable archived snapshots. A client GET before PATCH can be stale and is not by itself the actual pre-write state.
3. Expose history and diff inspection by task, object, field, and time. Include partial execution, failed requests, and uncertain outcomes after timeouts, which object history alone does not explain.
4. Compute and execute a deterministic inverse for supported operation types, with current-state/version checks. Log the reversal as a new task linked to the original. Never automatically retry an uncertain create/allocation without reconciling whether it already happened.
5. Report recovery coverage explicitly: automatic inverse supported, conditional on dependencies, or manual restoration required. The model can decide when to request a correction; the inverse calculation need not depend on model memory or reasoning.

A possible MCP surface is `begin_task`, normal CRUD carrying `task_id`, `get_task_changes`, `get_object_history`, `preview_undo`, and `undo_task`. Preview is an inspection/conflict-reporting capability, not a mandatory human approval step. The agent can be authorized to call undo directly. Existing NetBox views can provide the first human-facing history interface; a new dashboard is optional.

A crash can occur after NetBox commits but before the MCP service records its receipt. Use a durable operation intent, correlation markers, and reconciliation against native history to detect this gap. If journal completeness must be guaranteed in the same transaction as every write, a small NetBox plugin endpoint is stronger than an external wrapper. That is a separate requirement from trusting the AI or requiring approval.

**Suggested initial scope:** automatic undo for selected field updates; conditional reversal of simple creates; audited deletion only for model-specific tested restore paths. For objects without such paths, use a supported lifecycle-status change when possible, or accept that hard deletion requires assisted recovery. General restoration of arbitrary deleted graphs is the expensive part even after approvals disappear.

Retain PostgreSQL backups and, if warranted, point-in-time recovery for disaster recovery. Restore an old database to a separate instance when extracting selectively lost data. Restoring the entire production database to an earlier time also discards unrelated later work. Likewise, compensating a NetBox change cannot automatically retract already delivered webhooks or reverse device changes triggered by external consumers.

The project can now be a focused write-and-recovery adapter rather than a change-management product. A reliable general-purpose undo engine still needs model coverage tests, concurrent-edit tests, delete/relationship tests, and recovery-after-timeout tests. No live deployment or runtime verification was performed for this scenario assessment.
