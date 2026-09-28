"""Replay observed native records in reordered/late/interrupted export scenarios."""
import hashlib
import json
import tempfile
import time
from pathlib import Path
from api import API
from recovery import Coordinator
from lab import ROOT

source=API().all('core/object-changes/?limit=1000&ordering=id')
class Replay:
    def __init__(self):self.rows=source[:-1];self.fail=False
    def all(self,path):
        if self.fail:raise ConnectionError('interruption after first page, before complete enumeration')
        return self.rows
out=ROOT/'evidence/runs'/('archive-'+time.strftime('%Y%m%dT%H%M%S'));out.mkdir(parents=True)
with tempfile.TemporaryDirectory() as tmp:
    replay=Replay();c=Coordinator(Path(tmp)/'journal.sqlite',api=replay)
    c.archive();assert len(c.records())==len(source)-1
    replay.rows=list(reversed(source));c.archive();assert len(c.records())==len(source)
    replay.fail=True
    try:c.archive()
    except ConnectionError:pass
    else:raise AssertionError('Expected outage')
    assert len(c.records())==len(source)
    replay.fail=False;replay.rows=[];c.archive()
    assert c.metrics()['missing_native_records']==len(source)
    assert len(c.records())==len(source)
    digest=c.export(out/'archive.json');assert hashlib.sha256((out/'archive.json').read_bytes()).hexdigest()==digest
    # This read needs neither the coordinator nor live NetBox.
    independent=json.loads((out/'archive.json').read_text())
    assert len(independent['changes'])==len(source)
    (out/'results.json').write_text(json.dumps({'late_record_recovered':True,'reordered_replay_deduplicated':True,'interrupted_export_retained_prior_evidence':True,'native_history_loss_detected':True,'offline_export_readable':True,'records':len(source)},indent=2))
    c.db.close()
print(out)
