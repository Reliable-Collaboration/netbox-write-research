# Recovering deleted NetBox objects: findings and recommendation

Investigated 2026-09-28 against NetBox 4.7.1, with source inspection and
[14 executable lab experiments](../spikes/deletion-recovery/README.md).

**Recommendation: retain stock PostgreSQL and NetBox REST for ordinary CRUD;
add an Apache-2.0 recovery plugin for original-ID, dependency-aware restoration.**
NetBox already contains useful deserialization and change-tracking machinery.
We do not need a different database or to assume every deleted object must
receive a new ID. We do need a recovery planner, conflict checks, durable recovery
receipts, and stronger evidence capture for cases where native history is incomplete.
This is a design recommendation supported by bounded experiments, not a delivered
or universally qualified recovery engine.

## Start with the human: “I deleted something; how do I get it back?”

Stock NetBox 4.7.1 does not expose a general recycle bin, undelete button, or
ObjectChange restore API. Its changelog API is read-only; core changelog views
provide inspection. The long-standing generic undo request is closed as not
planned. This conclusion comes from inspecting the pinned views/routes as well
as [upstream issue 9464](https://github.com/netbox-community/netbox/issues/9464).

A practical runbook today:

1. **Avoid further changes to the affected objects.** Preserve the current
   database and relevant media; save the deletion history before housekeeping
   can remove it. Avoid immediately creating a replacement with the same name.
2. **Find the deletion in Other → Change Log.** Open its pre-change data and
   identify the request UUID. Inspect *every* change from that request, including
   updates to objects which survived. Through REST, use
   `/api/core/object-changes/?request_id=<uuid>` and follow pagination. The current
   endpoint is `core`, despite some older documentation still showing `extras`.
3. **For a simple isolated object, recreate it through the GUI or API.** Translate
   snapshot fields into writable fields, select surviving parents and relationships,
   and inspect the result. This is a new object, ordinarily with a new ID. Repair
   references and integrations that depended on the original identity.
4. **For a related set of deleted objects, use an administrator-assisted restore.**
   Reconstruct parents, children, relations and affected surviving fields together.
   An administrator can use NetBox's Python environment to preserve original IDs,
   but should test the plan on a copy first. The experiment helper is not a safe
   production command: it lacks a complete graph planner and concurrency controls.
5. **If history is insufficient, recover a backup to a separate isolated instance.**
   Recover the needed graph there, then plan selective restoration into live NetBox.
   Disable outbound automation on the recovery instance. Restoring the whole live
   database backwards also discards unrelated later work; that is disaster recovery,
   not selective undo.

Wikimedia's operational runbook similarly starts with changelog inspection and
chooses between manual/API reversal and database restoration. Its experimental
revert project explicitly encountered broken relationships when recreated objects
received new IDs. [Runbook](https://wikitech.wikimedia.org/wiki/Netbox#Restore),
[implementation discussion](https://phabricator.wikimedia.org/T310589).

For point-in-time recovery, PostgreSQL requires a base backup and the necessary
archived WAL. Ordinary `pg_dump` files cannot be replayed with WAL. PITR restores
a cluster, not a selected row; use a separate instance for selective extraction.
Back up media/configuration separately. [PostgreSQL 18 recovery documentation](https://www.postgresql.org/docs/18/continuous-archiving.html).

## What already exists inside NetBox

The inspected core source is Apache-2.0, tag `v4.7.1`, commit
`abccf4e03650fecd366e676b392729320258c49e`.

| Existing mechanism | What it gives us | What it does not establish |
| --- | --- | --- |
| `ObjectChange` | Original model/ID, actor, request UUID, pre/post snapshots | Every private relation, file byte, or external effect is recoverable |
| Deletion signals | Delete records for logged cascades; additional records for some surviving FK/M2M changes | Universal complete graph capture for every model/plugin |
| `deserialize_object(model, data, pk=...)` | Rebuild a Python model instance with the original ID; translate custom fields and M2M data | Authorization, conflict detection, dependency planning, safe insertion |
| Model validation and save methods | Existing business rules and lifecycle behavior | Exactly replaying old behavior after schema/config/template changes |
| Database transactions | Roll back a failed multi-object database correction | Atomicity with external systems or an external MCP journal |
| Detail DELETE with `If-Match` | Reject stale target state, rechecked under a target-row lock | Unchanged related-object graph or race-free restoration of an absent row |

Sources: [serialization helper](https://github.com/netbox-community/netbox/blob/abccf4e03650fecd366e676b392729320258c49e/netbox/utilities/serialization.py),
[core deletion signals](https://github.com/netbox-community/netbox/blob/abccf4e03650fecd366e676b392729320258c49e/netbox/core/signals.py),
[conditional DELETE](https://github.com/netbox-community/netbox/blob/abccf4e03650fecd366e676b392729320258c49e/netbox/netbox/api/viewsets/__init__.py).

**The REST representation is not the raw historical record.**
`ObjectChangeSerializer` exposes `prechange_data_clean` and `postchange_data_clean`.
Those omit diff-excluded timestamps/tree bookkeeping and underscore-prefixed
attributes. The live probe observed `created` in the database snapshot but not in
API history. Ordinary POST also ignored the supplied original `id` and assigned a
new one. Thus an external archive of API responses is valuable audit evidence,
but should not be advertised as a complete identity-preserving restore image.
[History serializer](https://github.com/netbox-community/netbox/blob/abccf4e03650fecd366e676b392729320258c49e/netbox/core/api/serializers_/change_logging.py),
[snapshot cleaning](https://github.com/netbox-community/netbox/blob/abccf4e03650fecd366e676b392729320258c49e/netbox/core/models/change_logging.py).

The core deserializer returns a Django deserialized-object wrapper. Its bare
`.save()` is not a complete restoration lifecycle: it can update an existing row
with the same ID, and does not invoke the model's overridden `save()` in the same
way as normal creation. Use validated, insert-only model operations for absent
rows, restore M2M data deliberately, and verify the result. Internal utilities
are an integration surface requiring version-specific tests, not a promised
stable public recovery API.

## What the 14 experiments established

Tests used real 4.7.1 serializers, middleware, signals, models and PostgreSQL via
Django's in-process test client. Each test rolled back its fixture changes. They
were not HTTP transport, permissions, concurrent-user, crash-durability or PITR tests.

| Experiment | Observed result |
| --- | --- |
| POST replacement with original `id` | New ID assigned |
| Inspect database versus REST change history | API omitted original `created` |
| Restore deleted site internally | Original ID, description and tags restored; new creation history recorded; original delete history retained |
| Bare deserializer on occupied ID | Existing row overwritten: unsafe without guards |
| Guarded restore / forced insert collision | Refused occupied ID; database rejected duplicate insertion |
| Missing historical tag | Core helper silently resolved to an empty set; experimental guard refused restoration |
| Delete interface with assigned primary IP | IP deleted, device primary-IP field cleared, interface deleted, all under one request UUID |
| Restore interface and IP with original IDs | Assignment restored; device's primary-IP reference still needed its own correction |
| Restore device after its template changed | Same-ID insertion did not instantiate newly added template interfaces; ordinary fresh POST did |
| Restore deleted cable | Parent-only restore had no terminations; restoring both historical termination rows reconnected interfaces |
| Restore hierarchical region | Original ID, parent and trigger-maintained path restored |
| Reused site name/slug | Validation prevented overwriting the newer object |
| Failure after an earlier graph insertion | Database transaction rolled back inserted object and its new audit record |
| Stale DELETE ETag | HTTP 412; object remained |
| Custom-field JSON | False, zero, empty string and null preserved |

Some tests establish more than one observation. The checked-in
[results](../spikes/deletion-recovery/evidence/results.json) report 14 tests,
zero failures and zero errors.

The cable case is particularly useful: native history includes cable-termination
records, so this tested graph is recoverable without inventing replacement IDs.
But it requires rebuilding that graph, not calling the parent deserializer alone.
Cable snapshot handling is model-specific. [Cable source](https://github.com/netbox-community/netbox/blob/abccf4e03650fecd366e676b392729320258c49e/netbox/dcim/models/cables.py).

These experiments establish **identity-preserving restoration of tested state**,
not byte-for-byte restoration of every timestamp or every model. Normal saves may
set new timestamps; a product must explicitly distinguish original creation metadata,
restoration time, and new audit history. Never backdate the recovery audit to hide it.

## How other approaches handle this

| Approach | Recovery behavior | Fit for this project |
| --- | --- | --- |
| Wikimedia Revert, Apache-2.0 | Recreates deletes, deletes creations, skips updates | Useful prior work; not general recovery. Current source drops falsey values, translates a small FK list and does not preserve IDs. Old `extras.ObjectChange` import also needs 4.7 work. |
| `netbox-history`, GPL-3.0-or-later | Searches snapshot values, including deleted objects | Useful evidence discovery, not restoration or independent archival. Inspected 0.1.1 plugin explicitly caps NetBox at 4.6.99. |
| NetBox Branching, restricted license | Reverts merged branch changes, including original-ID reconstruction of deletes | Demonstrates feasibility, but ineligible under the open-source requirement. Only merged retained branches can be reverted; not a general undelete of arbitrary main-branch history. No dependency or code adopted. |
| `django-reversion`, BSD-3-Clause | Stores registered model revisions and can recreate deleted instances | Viable library candidate, not a ready NetBox integration. Requires prior capture/registration and relation configuration; duplicates native history and still needs NetBox lifecycle, authorization and conflict work. |
| Previously tested `netbox-sdk` | Broad REST CRUD; branch revert delegates to Branching API | Can execute operations, does not supply an independent object-restore engine |
| Previously tested Zenix MCP | REST create/update/delete; its write tool explicitly describes deletes as non-undoable | Useful generic write design; does not solve restoration |
| Previously assessed `nbox` | Narrow planned writes and preconditions | No demonstrated arbitrary deletion recovery; retain as concurrency/tool-design reference |
| GitOps / Ansible / OpenTofu | Reconcile desired state by creating missing resources | Can repopulate known configuration, normally with new identities; not restoration of everything that existed or later human changes |
| Doltgres / Nautobot version-control work | Versioned database alternatives | Does not establish a mature NetBox 4.7 restore integration. Avoid replacing PostgreSQL to solve an application recovery problem. |

Pinned source references:
[Wikimedia script](https://github.com/wikimedia/operations-software-netbox-extras/blob/3887a7014907cd10325e14ae697efc721e9f3e96/customscripts/revert.py),
[history compatibility](https://github.com/averyhabbott/netbox-history/blob/41a54cbd046f10b3061f0d23dc71b8c8f049c9af/netbox_history/__init__.py),
[Branching restore implementation](https://github.com/netboxlabs/netbox-branching/blob/7f68f81b7670f3a357ff5b6373059cc4fe9eb36c/netbox_branching/models/changes.py),
[Branching license](https://github.com/netboxlabs/netbox-branching/blob/7f68f81b7670f3a357ff5b6373059cc4fe9eb36c/LICENSE.md),
[Branching revert lifecycle](https://netboxlabs.com/docs/branching/using-branches/reverting-a-branch/),
[django-reversion API](https://django-reversion.readthedocs.io/en/latest/api.html),
[django-reversion source/license](https://github.com/etianen/django-reversion/tree/cc6d5b96c683a4a637321e00db8649728ce26e3c).
The prior [candidate comparison](options.md) and [hands-on findings](spike-findings.md)
provide the existing adapter evidence. Current source inspection reaffirmed the
SDK's delegation to `/plugins/branching/branches/<id>/revert/` and Zenix's lack
of an undo path. Neither was rerun as part of this deletion spike.

A standard Django recycle-bin/soft-delete library is not a clean shortcut: changing
core deletion semantics affects uniqueness, queryset visibility, cascades, allocation,
permissions and plugins. We should preserve NetBox's ordinary deletion behavior and
retain recovery evidence separately instead of hiding rows from selected querysets.

## The cleanest plugin boundary

Build a focused recovery service inside NetBox; expose its operations to both
humans and MCP. Keep one deterministic recovery implementation rather than giving
the agent unrestricted shell/SQL access.

**1. Capture a recovery record.** Retain the original model label/ID, instance
lineage, source versions, request/task UUID, raw snapshots, stable relationship
IDs, affected surviving fields and required file evidence. Preserve falsey and
missing values distinctly. Native tags are name-based, so supplementary stable tag
IDs are needed to distinguish rename, deletion and name reuse. Include explicit
through rows and model-specific data where ordinary history is insufficient.

For future operations, capture this in the same database transaction as the
mutation and retain an immutable, idempotent operation receipt. A transactional
outbox can drive external archival; it does not make database and off-host archive
one transaction. Cover ordinary GUI/API deletions as well as MCP if human mistakes
must be recoverable. Signal-only capture is not proof against bulk SQL paths or
plugins that bypass model hooks: coverage must be measured and gaps surfaced.

**2. Plan restoration by request, not by a single object.** Use native request
correlation, deletion metadata and live dependencies to construct a dependency
plan. Account for deleted children and updates to surviving objects. Reverse
chronological log order alone is insufficient for cycles and mixed cascade/update
records. Handle required-parent order, optional cyclic references in a later pass,
and model-specific constraints. Older deletions can use existing history if complete;
installing a plugin cannot recreate previously lost files or pruned evidence.

**3. Check conflicts and permissions.** Require authorized restore/add/change
permissions and object-level scope for the *whole affected set*, including sensitive
archived data. Verify original IDs are vacant and names, addresses and other unique
keys are not occupied. For surviving fields compare expected post-delete values
and subsequent history, including ABA changes, before applying corrections. Retain
unrelated newer fields. Missing or ambiguous parents/tags/schema must produce an
instructional conflict, not guesses, automatic new-ID fallback, or partial success.

**4. Execute the plan atomically with original IDs where feasible.** Use model
validation, insert-only reconstruction, explicit relationship handling, native
change logging and a new recovery request ID. Verify restored graph invariants
before commit. Bind execution to a stored plan/operation key and recheck under
appropriate database concurrency control. An advisory lock honored only by the
plugin does not exclude normal GUI writers; absent rows and new dependencies also
need an explicit race strategy. Row locks, uniqueness enforcement and transaction
isolation must be tested against normal NetBox writes. This spike did not qualify
that concurrency protocol.

**5. Report what happened and preserve history.** Provide `preview_restore`,
`restore`, `get_restore_operation`, and a portable recovery bundle. Record original
change IDs, restored IDs, conflicts, residual effects and evidence hashes. Repeated
or lost responses resolve from the durable receipt; never infer success merely
from a matching object now existing. Preview is analysis and conflict detection,
not a mandatory approval workflow. The original delete and corrective changes
remain visible indefinitely under the configured retention/archive contract.

A small API surface does not mean the recovery engine is trivial. The first
implementation should generalize model metadata and graph reconstruction, then
add adapters and fixtures for exceptional models until the full coverage matrix
is met. This is a delivery sequence, not a retreat from the all-CRUD product goal.

## Decision and next qualification work

Prefer **original-ID restoration with explicit conflict refusal** over default
new-ID recreation. Preserve REST recreation as an explicitly classified fallback
when identity cannot be restored and the caller understands the remapping plan.
Keep backup-based recovery as the last resort. No forced overwrite is needed.

Before describing the plugin as mature, test complete device graphs, cables and
ports, modules, virtualization, IPAM/VLANs/VRFs, circuits, contacts/tenancy, custom
fields/object references, files, plugin objects, and permission-bearing objects.
Add graph cycles, deletion of a shared parent, tag rename/reuse, template/schema
changes, missing backups, concurrent human writes, occupied-ID races, partial
failure, restart and response-loss tests. Verify permissions against constrained
users, not only the administrator used by this research probe.

The 4.7.1 release also fixed hierarchical cascade triggers missing after a 4.7.0
`pg_dump` restore. A backup restore test must check those invariants, not just that
PostgreSQL accepted the dump. [4.7 release notes](https://netbox.readthedocs.io/en/stable/release-notes/version-4.7/).

**Change from the earlier advice:** the standard REST limitation does not imply
that a plugin must assign new IDs. Original-ID restoration is already technically
possible using open-source NetBox internals and was demonstrated here. The actual
engineering gap is reliable, complete, authorized restoration of the affected
object graph while preserving subsequent legitimate work.
