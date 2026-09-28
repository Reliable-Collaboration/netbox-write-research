import json
import time
from api import API
from lab import ROOT,STATE
from mcp_client import candidate
from compare import unpack
api=API();ids=json.loads((STATE/'fixtures.json').read_text());path=f"dcim/devices/{ids['nbox']}/"
out=ROOT/'evidence/runs'/('nbox-'+time.strftime('%Y%m%dT%H%M%S'));out.mkdir(parents=True)
c=candidate('nbox')
try:
    api.ok('PATCH',path,{'status':'active'})
    plan=unpack(c.tool('nbox_plan_write',operation={'kind':'device_status','device':'spike-nbox','status':'planned'}))
    if 'plan' in plan:plan=plan['plan']
    first=c.tool('nbox_apply_write',plan=plan);assert api.ok('GET',path)['status']['value']=='planned'
    count=api.ok('GET','core/object-changes/?limit=1')['count']
    replay=c.tool('nbox_apply_write',plan=plan)
    assert api.ok('GET','core/object-changes/?limit=1')['count']==count
    api.ok('PATCH',path,{'status':'active'})
    stale=unpack(c.tool('nbox_plan_write',operation={'kind':'device_status','device':'spike-nbox','status':'planned'}))
    if 'plan' in stale:stale=stale['plan']
    api.ok('PATCH',path,{'status':'offline'})
    result=c.tool('nbox_apply_write',plan=stale)
    assert api.ok('GET',path)['status']['value']=='offline'
    (out/'results.json').write_text(json.dumps({'write_succeeded':True,'replay_no_change':True,'stale_plan_preserved_external_change':True,'replay_response':replay,'stale_response':result},indent=2))
finally:
    (out/'transcript.json').write_text(json.dumps(c.transcript,indent=2));c.close()
print(out)
