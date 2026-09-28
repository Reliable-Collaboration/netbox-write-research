"""Inspect/export a spike journal without depending on model output."""
import argparse
import json
from recovery import Coordinator
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--journal',required=True)
p.add_argument('action',choices=['summary','archive','tasks','operations','history','preview','correct','export'])
p.add_argument('--operation');p.add_argument('--output')
a=p.parse_args();c=Coordinator(a.journal)
if a.action=='summary':r=c.metrics()
elif a.action=='archive':r={'native_rows_seen':c.archive()};c.reconcile();r.update(c.metrics())
elif a.action=='tasks':r=[dict(x) for x in c.db.execute('SELECT * FROM tasks ORDER BY created')]
elif a.action=='operations':r=[dict(x) for x in c.db.execute('SELECT * FROM operations ORDER BY created')]
elif a.action=='history':r=c.records()
elif a.action in ['preview','correct']:
    if not a.operation:p.error('--operation is required')
    r=c.preview(a.operation) if a.action=='preview' else c.undo(a.operation)
else:
    if not a.output:p.error('--output is required')
    r={'sha256':c.export(a.output)}
print(json.dumps(r,indent=2));c.db.close()
