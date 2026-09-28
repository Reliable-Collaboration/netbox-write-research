# Deletion recovery investigation

Objectives: establish what a human can do after accidental deletion in stock
NetBox 4.7; distinguish REST recreation from original-ID restoration; investigate
eligible prior work; identify the smallest useful recovery plugin.

See the [findings and recommendation](../../research/deletion-recovery.md).
This is research code, **not a production restore endpoint**. It does not change
the supported operations of netbox-readwrite-mcp.

## Reproduce

Use the separately maintained netbox-readwrite-mcp disposable 4.7.1 lab. Set it up
and bootstrap it following that project's testing guide. With its four named
containers running, from this research repository:

```sh
podman exec -i nbrw-audit-4-7-1-netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell \
  < spikes/deletion-recovery/probe.py
```

The script refuses other database host names and any configured event rules.
It uses the existing lab-only audit-admin identity, synthetic fixtures, actual
NetBox API views via Django's test client, and PostgreSQL. Each test rolls back
its database changes; PostgreSQL sequence values still advance. It sends no
network HTTP requests and is not a durability, permissions, or concurrent-writer
test. Do not adapt the guard to run against production.

All 14 tests passed on 4.7.1. [Results](evidence/results.json) and
[source pins](evidence/sources.json) are checked in. Tests cover REST-assigned
IDs; cleaned versus raw history; original-ID, tag and audit restoration; ID and
uniqueness collisions; missing tags; interface/IP/device effects; template side
effects; cable terminations; tree paths; atomic rollback; stale DELETE ETags;
and false/zero/empty/null custom-field JSON.

The small restore helper deliberately lacks production authorization, graph
planning, concurrency coordination and idempotency. In particular, the cable
test proves it can return a parent row while restoration remains incomplete.
Its direct use is not recommended. Restricted Branching source was inspected
as prior art only; no code was copied or dependency introduced.
