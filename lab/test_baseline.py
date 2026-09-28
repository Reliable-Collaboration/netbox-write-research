import concurrent.futures
import json
import time
import unittest
import uuid
from api import API
from lab import ROOT, STATE, PREFIX, LABEL, pod

class Baseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api=API(); cls.ids=json.loads((STATE/'fixtures.json').read_text()); cls.tokens=json.loads((STATE/'identities.json').read_text())
        cls.out=ROOT/'evidence/runs'/('baseline-'+time.strftime('%Y%m%dT%H%M%S')); cls.out.mkdir(parents=True)
        cls.path=f"dcim/devices/{cls.ids['baseline']}/"
        cls.evidence={}

    def test_T01_actual_snapshots_and_invalid(self):
        self.api.ok('PATCH',self.path,{'description':'before'})
        r=self.api.request('PATCH',self.path,{'description':'after'})
        rid=r['headers']['x-request-id']; rows=self.api.all('core/object-changes/?request_id='+rid)
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['prechange_data']['description'],'before'); self.assertEqual(rows[0]['postchange_data']['description'],'after')
        self.evidence['snapshots']=rows
        bad=self.api.request('PATCH',self.path,{'status':'invalid'})
        self.assertEqual(bad['status'],400); self.assertEqual(self.api.all('core/object-changes/?request_id='+bad['headers']['x-request-id']),[])

    def test_T03_simultaneous_stale_writers(self):
        self.api.ok('PATCH',self.path,{'description':'race-start'})
        etag=self.api.request('GET',self.path)['headers']['etag']
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda s:self.api.request('PATCH',self.path,{'description':s},{'If-Match':etag}),['writer-one','writer-two']))
        self.assertEqual(sorted(r['status'] for r in responses),[200,412]); self.evidence['race']=responses

    def test_T04_structured_snapshot_values(self):
        fields=self.api.ok('GET','extras/custom-fields/?name=spike_flag')['results']
        if not fields: self.api.ok('POST','extras/custom-fields/',{'name':'spike_flag','type':'boolean','object_types':['dcim.device']})
        self.api.ok('PATCH',self.path,{'custom_fields':{'spike_flag':True},'tags':[],'asset_tag':'baseline-temp'})
        r=self.api.request('PATCH',self.path,{'custom_fields':{'spike_flag':False},'tags':[self.ids['tag']],'asset_tag':None,'changelog_message':'snapshot-test-'+uuid.uuid4().hex})
        self.assertEqual(r['status'],200)
        change=self.api.all('core/object-changes/?request_id='+r['headers']['x-request-id'])[0]
        self.assertIs(change['postchange_data']['custom_fields']['spike_flag'],False)
        self.assertIsNone(change['postchange_data']['asset_tag']); self.assertTrue(change['postchange_data']['tags'])
        self.evidence['structured']=change

    def test_T07_bulk_validation_atomicity(self):
        p2=f"dcim/devices/{self.ids['sdk']}/"
        old=self.api.ok('GET',self.path)['description']
        r=self.api.request('PATCH','dcim/devices/',[{'id':self.ids['baseline'],'description':'should-not-commit'},{'id':self.ids['sdk'],'status':'invalid'}])
        self.assertEqual(r['status'],400); self.assertEqual(self.api.ok('GET',self.path)['description'],old)
        self.evidence['bulk']=r

    def test_T09_delete_relationship_and_new_identity(self):
        iface=self.api.ok('POST','dcim/interfaces/',{'device':self.ids['baseline'],'name':'restore-'+uuid.uuid4().hex[:8],'type':'virtual'})
        ip=self.api.ok('POST','ipam/ip-addresses/',{'address':'203.0.113.77/32','assigned_object_type':'dcim.interface','assigned_object_id':iface['id']})
        r=self.api.request('DELETE',f"dcim/interfaces/{iface['id']}/")
        self.assertEqual(r['status'],204)
        after=self.api.request('GET',f"ipam/ip-addresses/{ip['id']}/")
        new=self.api.ok('POST','dcim/interfaces/',{'device':self.ids['baseline'],'name':iface['name'],'type':'virtual'})
        self.assertNotEqual(new['id'],iface['id'])
        self.evidence['delete']={'old_interface_id':iface['id'],'new_interface_id':new['id'],'ip_after':after,'changes':self.api.all('core/object-changes/?request_id='+r['headers']['x-request-id'])}

    def test_T11_actor_attribution(self):
        other=API(token=self.tokens['second'])
        a=self.api.request('PATCH',self.path,{'description':'same-value'})
        b=other.request('PATCH',self.path,{'description':'second-actor-value'})
        ca=self.api.all('core/object-changes/?request_id='+a['headers']['x-request-id'])[0]
        cb=self.api.all('core/object-changes/?request_id='+b['headers']['x-request-id'])[0]
        self.assertEqual(ca['user_name'],'spike-admin'); self.assertEqual(cb['user_name'],'spike-second')
        self.evidence['actors']=[ca,cb]
        noop=other.request('PATCH',self.path,{'description':'second-actor-value'})
        self.assertEqual(noop['status'],200)
        self.evidence['noop_history']=self.api.all('core/object-changes/?request_id='+noop['headers']['x-request-id'])

    def test_T12_readonly_and_object_permission(self):
        results={}
        for name in ['observer','restricted']:
            api=API(token=self.tokens[name]); self.assertEqual(api.request('GET',self.path)['status'],200)
            r=api.request('PATCH',self.path,{'description':'forbidden'})
            self.assertEqual(r['status'],403); results[name]=r
        self.evidence['permissions']=results

    def test_T13_webhook_survives_correction(self):
        events=STATE/'events'; events.mkdir(exist_ok=True)
        import subprocess
        if subprocess.run(['podman','container','exists',PREFIX+'-capture']).returncode:
            pod('run','-d','--name',PREFIX+'-capture','--label',LABEL,'--network',PREFIX,'--entrypoint','python','-v',str(ROOT/'lab/capture.py')+':/capture.py:ro','-v',str(events)+':/events','localhost/nbai-spike/sdk','/capture.py',capture_output=True)
        suffix=uuid.uuid4().hex[:8]
        hook=self.api.ok('POST','extras/webhooks/',{'name':'capture-'+suffix,'payload_url':'http://nbai-spike-capture:8000/'})
        rule=self.api.ok('POST','extras/event-rules/',{'name':'capture-'+suffix,'object_types':['dcim.device'],'event_types':['object_updated'],'action_type':'webhook','action_object_type':'extras.webhook','action_object_id':hook['id']})
        try:
            a=self.api.request('PATCH',self.path,{'description':'webhook-mistake'})
            b=self.api.request('PATCH',self.path,{'description':'webhook-corrected'})
            expected={a['headers']['x-request-id'],b['headers']['x-request-id']}
            found=[]
            for _ in range(25):
                if (events/'webhooks.jsonl').exists():
                    found=[json.loads(l) for l in (events/'webhooks.jsonl').read_text().splitlines() if l]
                seen={x['body']['request_id'] for x in found}
                if expected<=seen: break
                time.sleep(1)
            self.assertTrue(expected<=seen)
            self.evidence['webhooks']=[x for x in found if x['body']['request_id'] in expected]
        finally:
            self.api.ok('DELETE',f"extras/event-rules/{rule['id']}/")
            self.api.ok('DELETE',f"extras/webhooks/{hook['id']}/")

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Baseline))
    (Baseline.out/'evidence.json').write_text(json.dumps(Baseline.evidence,indent=2))
    (Baseline.out/'results.json').write_text(json.dumps({'tests':result.testsRun,'success':result.wasSuccessful(),'failures':[(str(t),s) for t,s in result.failures],'errors':[(str(t),s) for t,s in result.errors]},indent=2))
    raise SystemExit(not result.wasSuccessful())
