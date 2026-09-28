import json
import time
from lab import ROOT,STATE
from api import API
from recovery import Coordinator
from sdk_bridge import SDKBridge

run=ROOT/'evidence/runs'/('sdk-recovery-'+time.strftime('%Y%m%dT%H%M%S'));run.mkdir(parents=True)
ids=json.loads((STATE/'fixtures.json').read_text());path=f"dcim/devices/{ids['sdk']}/"
api=API();api.ok('PATCH',path,{'description':'SDK recovery A','serial':''})
bridge=SDKBridge();store=STATE/('sdk-recovery-'+str(int(time.time()))+'.sqlite');c=Coordinator(store,api=bridge)
try:
    op=c.execute(c.begin('MCP bridged recovery'),'PATCH',path,{'description':'SDK recovery B'})
    assert op['change_id'] is not None,op
    api.ok('PATCH',path,{'serial':'external-new-serial'})
    undo=c.undo(op['id']);assert undo['status']=='committed',undo
    (run/'recovery-response.json').write_text(json.dumps(undo,indent=2))
    obj=api.ok('GET',path);assert obj['description']=='SDK recovery A' and obj['serial']=='external-new-serial'
    op2=c.execute(c.begin('MCP bridged race'),'PATCH',path,{'description':'race-B'})
    race=c.undo(op2['id'],before_apply=lambda:api.ok('PATCH',path,{'description':'race-C'}))
    assert race['status'] in ['failed','uncertain'],race
    assert api.ok('GET',path)['description']=='race-C'
    (run/'results.json').write_text(json.dumps({'update_and_recovery':'passed','unrelated_serial_preserved':True,'race_protected':True,'race_receipt_status':race['status']},indent=2))
finally:
    c.export(run/'journal.json');(run/'transcript.json').write_text(json.dumps(bridge.mcp.transcript,indent=2));bridge.mcp.close();c.db.close()
print(run)
