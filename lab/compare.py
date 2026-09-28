"""Run actual MCP calls, independently verify committed NetBox state/history."""
import json
import time
import uuid
import os
from api import API
from lab import ROOT, STATE
from mcp_client import candidate

def unpack(r):
    result=r.get('result',{})
    if 'structuredContent' in result: return result['structuredContent']
    for c in result.get('content',[]):
        if c.get('type')=='text':
            try: return json.loads(c['text'])
            except ValueError: return c['text']
    return result

def main():
    api=API(); ids=json.loads((STATE/'fixtures.json').read_text())
    run=ROOT/'evidence/runs'/('candidates-'+time.strftime('%Y%m%dT%H%M%S'))
    run.mkdir(parents=True)
    report={}
    for name in ['sdk','zenix','nbox']:
        c=candidate('sdk-patched' if name=='sdk' and os.environ.get('SDK_PATCHED') else name); checks=[]
        path=f"dcim/devices/{ids[name]}/"
        api.ok('PATCH',path,{'description':'A','status':'active'})
        before={x['id'] for x in api.all('core/object-changes/?limit=1000')}
        try:
            c.call('tools/list')
            if name=='sdk':
                r=c.tool('patch',group='dcim',resource='devices',id=ids[name],payload={'description':'MCP B'})
            elif name=='zenix':
                r=c.tool('netbox_write',object_type='dcim.device',operation='update',id=ids[name],data={'description':'MCP B'})
            else:
                r=c.tool('nbox_plan_write',operation={'kind':'device_status','device':'spike-nbox','status':'planned'})
                plan=unpack(r)
                (run/'nbox-plan.json').write_text(json.dumps(plan,indent=2))
                # Tool returns an envelope on some versions; preserve original response.
                if isinstance(plan,dict) and 'plan' in plan: plan=plan['plan']
                r=c.tool('nbox_apply_write',plan=plan)
            obj=api.ok('GET',path)
            checks.append({'case':'write','passed':obj['status']['value']=='planned' if name=='nbox' else obj['description']=='MCP B','response':r})
            if name in ['sdk','zenix']:
                if name=='sdk':
                    r=c.tool('patch',group='dcim',resource='devices',id=ids[name],payload={'status':'not-a-status'})
                    stale=c.tool('patch',group='dcim',resource='devices',id=ids[name],payload={'description':'unsafe'},header=['If-Match: "stale"'])
                    checks.append({'case':'stale_etag','passed':api.ok('GET',path)['description']=='MCP B','response':stale})
                else:
                    r=c.tool('netbox_write',object_type='dcim.device',operation='update',id=ids[name],data={'status':'not-a-status'})
                checks.append({'case':'invalid_status','passed':api.ok('GET',path)['status']['value']=='active','response':r})
                slug='spike-'+name+'-'+uuid.uuid4().hex[:8]
                if name=='sdk': r=c.tool('create',group='dcim',resource='sites',payload={'name':slug,'slug':slug})
                else: r=c.tool('netbox_write',object_type='dcim.site',operation='create',data={'name':slug,'slug':slug})
                found=api.ok('GET','dcim/sites/?slug='+slug)['results']
                checks.append({'case':'create','passed':len(found)==1,'response':r})
                if found:
                    if name=='sdk': r=c.tool('delete',group='dcim',resource='sites',id=found[0]['id'])
                    else: r=c.tool('netbox_write',object_type='dcim.site',operation='delete',id=found[0]['id'],confirm=slug)
                    checks.append({'case':'delete','passed':api.request('GET',f"dcim/sites/{found[0]['id']}/")['status']==404,'response':r})
            changes=[x for x in api.all('core/object-changes/?limit=1000') if x['id'] not in before]
            (run/(name+'-changes.json')).write_text(json.dumps(changes,indent=2))
        except Exception as e:
            checks.append({'case':'execution','passed':False,'error':str(e)})
        finally:
            (run/(name+'-transcript.json')).write_text(json.dumps(c.transcript,indent=2))
            c.close()
        report[name]=checks
        report[name+'_variant']='patched' if name=='sdk' and os.environ.get('SDK_PATCHED') else 'upstream'
        print(name,[(x['case'],x['passed']) for x in checks],flush=True)
    (run/'results.json').write_text(json.dumps(report,indent=2))
    print(run)

if __name__=='__main__': main()
