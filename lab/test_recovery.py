"""Destructive only to synthetic fixtures in the isolated nbai-spike lab."""
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
import ipaddress
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from api import API
from lab import ROOT, STATE
from recovery import Coordinator

class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifact_dir=ROOT/'evidence/runs'/('recovery-'+time.strftime('%Y%m%dT%H%M%S'))
        cls.artifact_dir.mkdir(parents=True)
        cls.api=API(); cls.ids=json.loads((STATE/'fixtures.json').read_text())
        cls.path=f"dcim/devices/{cls.ids['recovery']}/"
        cls.results=[]

    def setUp(self):
        self.api.ok('PATCH',self.path,{'description':'A','serial':'','asset_tag':None,'status':'active'})
        self.store=self.artifact_dir/(self._testMethodName+'.sqlite')
        self.c=Coordinator(self.store)
        self.task=self.c.begin(self._testMethodName)

    def tearDown(self):
        self.c.export(self.artifact_dir/(self._testMethodName+'.json'))
        self.c.db.close()
        # Binary databases live outside checked-in evidence; JSON export is the artifact.
        self.store.unlink(missing_ok=True)

    def change(self,body=None):
        r=self.c.execute(self.task,'PATCH',self.path,body or {'description':'B'})
        self.assertEqual(r['status'],'committed'); self.assertIsNotNone(r['change_id'])
        return r

    def test_T02_unrelated_edit_preserved(self):
        r=self.change(); self.api.ok('PATCH',self.path,{'serial':'new-serial'})
        undo=self.c.undo(r['id']); self.assertEqual(undo['status'],'committed')
        obj=self.api.ok('GET',self.path); self.assertEqual(obj['description'],'A'); self.assertEqual(obj['serial'],'new-serial')
        self.assertEqual(self.c.undo(r['id'])['status'],'already_requested')

    def test_T03_same_field_conflict(self):
        r=self.change(); self.api.ok('PATCH',self.path,{'description':'C'})
        self.assertEqual(self.c.undo(r['id'])['status'],'conflicted')
        self.assertEqual(self.api.ok('GET',self.path)['description'],'C')

    def test_T03_apply_time_race(self):
        r=self.change()
        undo=self.c.undo(r['id'],before_apply=lambda:self.api.ok('PATCH',self.path,{'description':'race'}))
        self.assertEqual(undo['status'],'failed')
        self.assertEqual(self.api.ok('GET',self.path)['description'],'race')
        responses=[json.loads(x[0]) for x in self.c.db.execute("SELECT body FROM events WHERE kind='response'")]
        self.assertEqual(responses[-1]['status'],412)

    def test_T04_null_and_empty(self):
        r=self.change({'asset_tag':'asset-'+uuid.uuid4().hex[:8],'serial':'xyz'})
        self.assertEqual(self.c.undo(r['id'])['status'],'committed')
        obj=self.api.ok('GET',self.path); self.assertIsNone(obj['asset_tag']); self.assertEqual(obj['serial'],'')

    def test_T05_response_lost_after_create(self):
        api=self.api
        class Drop(BaseHTTPRequestHandler):
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                result=api.request('POST',self.path.split('/api/')[1],body)
                self.server.result=result
                self.connection.shutdown(2); self.connection.close()
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Drop)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            self.c.api=API(base=f'http://127.0.0.1:{server.server_port}')
            r=self.c.execute(self.task,'POST','ipam/ip-addresses/',{'address':str(ipaddress.IPv6Address((0x20010db8<<96)|(uuid.uuid4().int & ((1<<96)-1))))+'/128','description':'lost response'})
            self.assertEqual(r['status'],'uncertain'); self.assertEqual(server.result['status'],201)
            self.c.api=api; self.c.archive(); self.c.reconcile()
            r=self.c.operation(r['id']); self.assertEqual(r['status'],'committed')
            matches=[x for x in self.c.records() if x['message']=='nbai:'+r['id']]
            self.assertEqual(len(matches),1)
            self.assertEqual(self.c.preview(r['id'])['status'],'manual')
        finally: server.shutdown(); server.server_close()

    def test_T06_process_death_boundaries(self):
        for point,exit_code in [('after_response',99),('before_send',98)]:
            code = """import os,sys
sys.path.insert(0,'lab')
from recovery import Coordinator
c=Coordinator(sys.argv[1])
def die(point):
    if point==sys.argv[4]:os._exit(int(sys.argv[5]))
c.execute(sys.argv[2],'PATCH',sys.argv[3],{'description':'B' if sys.argv[4]=='after_response' else 'never-sent'},fault=die)
"""
            result=subprocess.run([sys.executable,'-c',code,str(self.store),self.task,self.path,point,str(exit_code)],cwd=ROOT)
            self.assertEqual(result.returncode,exit_code)
        self.c.db.close();self.c=Coordinator(self.store)
        statuses=[r[0] for r in self.c.db.execute('SELECT status FROM operations ORDER BY created')]
        self.assertEqual(statuses,['uncertain','intent'])
        self.c.archive();self.c.reconcile()
        self.assertEqual(self.api.ok('GET',self.path)['description'],'B')
        self.assertEqual(self.c.metrics()['operations'],{'committed':1,'intent':1})
        self.assertEqual(self.c.metrics()['unresolved'],1)

    def test_T07_partial_task(self):
        self.change()
        bad=self.c.execute(self.task,'PATCH',self.path,{'status':'invalid-choice'})
        self.assertEqual(bad['status'],'failed')
        self.assertEqual(self.c.metrics()['operations'],{'committed':1,'failed':1})
        self.assertEqual(self.api.ok('GET',self.path)['description'],'B')

    def test_T08_ABA_intervening_change(self):
        r=self.change()
        self.api.ok('PATCH',self.path,{'description':'C'})
        self.api.ok('PATCH',self.path,{'description':'B'})
        self.assertEqual(self.c.preview(r['id'])['status'],'conflicted')

    def test_T10_archive_replay_backup_and_integrity(self):
        self.change(); self.c.archive(); count=len(self.c.records()); self.c.archive()
        self.assertEqual(len(self.c.records()),count)
        backup=STATE/'recovery-backup.sqlite'; backup.unlink(missing_ok=True)
        self.c.backup(backup)
        restored=Coordinator(backup)
        self.assertEqual(restored.records(),self.c.records())
        self.assertEqual(restored.metrics()['operations'],self.c.metrics()['operations']); restored.db.close()
        # Verify fail-closed archive consistency without altering live NetBox.
        old=self.c.api
        class Rewritten:
            def all(self,path):
                rows=old.all(path); rows[0]['message']='rewritten'; return rows
        self.c.api=Rewritten()
        with self.assertRaisesRegex(RuntimeError,'rewritten'): self.c.archive()
        self.c.api=old
        self.assertEqual(len(self.c.records()),count)

    def test_T10_archive_outage(self):
        old=self.c.api
        class Outage:
            def request(self,*args,**kw): return old.request(*args,**kw)
            def all(self,path): raise ConnectionError('injected archive outage')
        self.c.api=Outage()
        r=self.c.execute(self.task,'PATCH',self.path,{'description':'B'})
        self.assertEqual(r['status'],'committed'); self.assertIsNone(r['change_id'])
        self.assertTrue(self.c.metrics()['archive_stale']); self.assertEqual(self.c.metrics()['unresolved'],1)
        self.c.api=old; self.c.archive(); self.c.reconcile()
        self.assertFalse(self.c.metrics()['archive_stale']); self.assertEqual(self.c.metrics()['unresolved'],0)

    def test_T10_fail_closed_archive_outage(self):
        old=self.c.api
        class Outage:
            def all(self,path): raise ConnectionError('archive unavailable')
        self.c.api=Outage(); self.c.fail_closed=True
        with self.assertRaises(ConnectionError): self.c.execute(self.task,'PATCH',self.path,{'description':'must-not-write'})
        self.assertEqual(old.ok('GET',self.path)['description'],'A')
        self.assertEqual(self.c.metrics()['archive_failures'],1)
        self.c.api=old

    def test_T11_two_actors_identical_values(self):
        # Separate operations share an actor here; distinct user identity is tested in baseline.
        a=self.change(); b=self.c.execute(self.c.begin('other task'),'PATCH',self.path,{'description':'B'})
        self.assertEqual(b['status'],'committed')
        self.assertNotEqual(a['id'],b['id']); self.assertNotEqual(a['request_id'],b['request_id'])
        self.assertIsNone(b['change_id'])  # Native history omits a no-op, even with a message.
        self.assertEqual(self.c.metrics()['unresolved'],1)

    def test_T12_unsupported_fields_fail_closed(self):
        with self.assertRaises(ValueError): self.c.execute(self.task,'PATCH',self.path,{'tags':[]})
        with self.assertRaises(ValueError): self.c.execute(self.task,'DELETE',self.path,{})
        self.assertEqual(self.api.ok('GET',self.path)['description'],'A')

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (RecoveryTests.artifact_dir/'results.json').write_text(json.dumps({'tests':result.testsRun,'failures':[(str(t),s) for t,s in result.failures],'errors':[(str(t),s) for t,s in result.errors],'success':result.wasSuccessful()},indent=2))
    raise SystemExit(not result.wasSuccessful())
