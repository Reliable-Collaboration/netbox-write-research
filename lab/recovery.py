"""Experimental external journal, full-scan archive, and bounded scalar recovery.

Supported automatic inverse: device description/serial/asset_tag/status updates.
No blanket undo, graph delete, or inference of success from time/value similarity.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import uuid
from api import API

FIELDS={'description','serial','asset_tag','status'}

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)

def immutable_change(row):
    # Related-object URLs/displays can change after a rename or deletion.
    # Keep committed snapshots and scalar audit identity, not mutable expansions.
    return {k:row[k] for k in ['id','time','user_name','request_id','action','changed_object_type','changed_object_id','object_repr','message','prechange_data','postchange_data']}

class Coordinator:
    def __init__(self,path,api=None,lineage='spike-4.6.10-initial',fail_closed=False):
        self.api=api or API(); self.lineage=lineage; self.fail_closed=fail_closed
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,purpose TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,task TEXT NOT NULL,method TEXT NOT NULL,path TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,request_id TEXT,change_id INTEGER,reverses TEXT UNIQUE,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS changes(lineage TEXT NOT NULL,id INTEGER NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(lineage,id));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,operation TEXT,kind TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        old=self.db.execute("SELECT value FROM meta WHERE key='lineage'").fetchone()
        if old and old[0]!=lineage: raise ValueError('Use a new journal after a database restore/lineage change')
        self.db.execute("INSERT OR IGNORE INTO meta VALUES('lineage',?)",(lineage,)); self.db.commit()

    def event(self,operation,kind,body):
        self.db.execute('INSERT INTO events(operation,kind,body,created) VALUES(?,?,?,?)',(operation,kind,canonical(body),time.time()))
        self.db.commit()

    def begin(self,purpose):
        task=str(uuid.uuid4())
        self.db.execute('INSERT INTO tasks VALUES(?,?,?)',(task,purpose,time.time())); self.db.commit()
        return task

    def archive(self):
        # Full rescans are intentionally simple and replayable. At scale use an
        # overlapping export + periodic full reconciliation, not max(id) alone.
        try:
            rows=self.api.all('core/object-changes/?limit=1000&ordering=id')
            for row in rows:
                data=canonical(immutable_change(row)); digest=hashlib.sha256(data.encode()).hexdigest()
                old=self.db.execute('SELECT sha256 FROM changes WHERE lineage=? AND id=?',(self.lineage,row['id'])).fetchone()
                if old and old[0]!=digest: raise RuntimeError(f"Archived change {row['id']} was rewritten; check lineage/integrity")
                self.db.execute('INSERT OR IGNORE INTO changes VALUES(?,?,?,?)',(self.lineage,row['id'],data,digest))
            seen={row['id'] for row in rows}
            missing=[r[0] for r in self.db.execute('SELECT id FROM changes WHERE lineage=?',(self.lineage,)) if r[0] not in seen]
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('missing_native_records',?)",(str(len(missing)),))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('last_archive',?)",(str(time.time()),))
            self.db.commit()
            return len(rows)
        except Exception as exc:
            self.db.rollback(); self.event(None,'archive_failed',{'error':str(exc)})
            raise

    def records(self):
        return [json.loads(x[0]) for x in self.db.execute('SELECT body FROM changes WHERE lineage=? ORDER BY id',(self.lineage,))]

    def operation(self,op):
        row=self.db.execute('SELECT * FROM operations WHERE id=?',(op,)).fetchone()
        if not row: raise KeyError(op)
        return dict(row)

    def execute(self,task,method,path,payload,headers=None,reverses=None,fault=None):
        if not self.db.execute('SELECT 1 FROM tasks WHERE id=?',(task,)).fetchone(): raise ValueError('Unknown task')
        if method not in {'PATCH','POST'}: raise ValueError('Prototype only exposes PATCH/POST; deletes need model-specific support')
        # Narrow lab write surface; do not expose arbitrary NetBox routes to agents.
        if method=='PATCH':
            parts=path.strip('/').split('/')
            if len(parts)!=3 or parts[:2]!=['dcim','devices'] or not parts[2].isdigit() or not set(payload)<=FIELDS or not payload:
                raise ValueError('Only selected scalar device fields supported')
        elif path!='ipam/ip-addresses/':
            raise ValueError('Only direct IP creation is enabled for uncertainty experiments')
        if reverses:
            previous=self.db.execute('SELECT id FROM operations WHERE reverses=?',(reverses,)).fetchone()
            if previous: return self.operation(previous[0])
        if self.fail_closed: self.archive()
        op=str(uuid.uuid4())
        self.db.execute('INSERT INTO operations(id,task,method,path,payload,status,reverses,created) VALUES(?,?,?,?,?,?,?,?)',(op,task,method,path,canonical(payload),'intent',reverses,time.time()))
        self.db.commit(); self.event(op,'intent',{'method':method,'path':path,'payload':payload})
        if fault: fault('before_send')
        body={**payload,'changelog_message':'nbai:'+op}
        self.db.execute("UPDATE operations SET status='uncertain' WHERE id=?",(op,)); self.db.commit()
        try:
            r=self.api.request(method,path,body,headers)
            if fault: fault('after_response')
        except Exception as exc:
            self.event(op,'transport_uncertain',{'error':str(exc)})
            return self.operation(op)
        status=('committed' if r['status'] in (200,201) else 'failed' if 400<=r['status']<500 else 'uncertain')
        self.db.execute('UPDATE operations SET status=?,request_id=? WHERE id=?',(status,r['headers'].get('x-request-id'),op)); self.db.commit()
        self.event(op,'response',r)
        try: self.archive(); self.reconcile()
        except Exception: pass # archive_failed event + stale last_archive remain visible
        return self.operation(op)

    def reconcile(self):
        records=self.records()
        for row in self.db.execute("SELECT * FROM operations WHERE status IN ('intent','uncertain','committed')").fetchall():
            matches=[r for r in records if r['message']=='nbai:'+row['id']]
            expected_type='dcim.device' if row['method']=='PATCH' else 'ipam.ipaddress'
            matches=[r for r in matches if r['changed_object_type']==expected_type and r['action']['value']==('update' if row['method']=='PATCH' else 'create')]
            if row['method']=='PATCH': matches=[r for r in matches if r['changed_object_id']==int(row['path'].strip('/').split('/')[-1])]
            if len(matches)==1:
                change=matches[0]
                if row['request_id'] and row['request_id']!=change['request_id']:
                    self.event(row['id'],'correlation_conflict',{'change_id':change['id']}); continue
                self.db.execute("UPDATE operations SET status='committed',request_id=?,change_id=? WHERE id=?",(change['request_id'],change['id'],row['id']))
            elif len(matches)>1:
                self.event(row['id'],'correlation_ambiguous',{'matches':len(matches)})
        self.db.commit()

    def preview(self,op):
        original=self.operation(op)
        if original['status']!='committed' or original['change_id'] is None:
            return {'status':'uncertain','operation':op,'reason':'Committed evidence is not available; do not retry the original write.'}
        if original['method']!='PATCH':
            return {'status':'manual','operation':op,'reason':'Create/delete dependency restoration is not implemented.'}
        self.archive() # fail closed if current history cannot be verified
        # Read current object BEFORE checking archived intervening history. The
        # final ETag ensures a write after this read invalidates the apply.
        current=self.api.request('GET',original['path'])
        if current['status']!=200: return {'status':'manual','reason':'Object is unavailable','operation':op}
        self.archive() # catch changes between the preceding archive and GET
        records=self.records(); evidence=next(r for r in records if r['id']==original['change_id'])
        fields=set(json.loads(original['payload']))
        before=evidence['prechange_data']; after=evidence['postchange_data']
        if any(k not in before or k not in after for k in fields): return {'status':'manual','reason':'Snapshot field absent','operation':op}
        fields={k for k in fields if before[k]!=after[k]}
        conflicts=[]
        for k in fields:
            value=current['body'][k]
            if k=='status': value=value['value']
            if value!=after[k]: conflicts.append({'field':k,'reason':'current value differs','expected':after[k],'current':value})
        for r in records:
            if r['id']<=evidence['id'] or r['changed_object_type']!=evidence['changed_object_type'] or r['changed_object_id']!=evidence['changed_object_id']: continue
            for k in fields:
                if r['prechange_data'].get(k)!=r['postchange_data'].get(k):
                    conflicts.append({'field':k,'reason':'intervening change (including ABA)','change_id':r['id']})
        etag=current['headers'].get('etag')
        if not etag: return {'status':'manual','reason':'No server precondition available','operation':op}
        return {'status':'conflicted' if conflicts else 'supported','operation':op,'path':original['path'],'change_id':evidence['id'],'etag':etag,'inverse':{k:before[k] for k in sorted(fields)},'conflicts':conflicts,'external_effects':'Not reversed; inspect webhook/downstream consumers.'}

    def undo(self,op,before_apply=None):
        previous=self.db.execute('SELECT id FROM operations WHERE reverses=?',(op,)).fetchone()
        if previous: return {'status':'already_requested','correction':self.operation(previous[0])}
        preview=self.preview(op)
        if preview['status']!='supported': return preview
        if not preview['inverse']: return {'status':'no_change','operation':op}
        if before_apply: before_apply()
        task=self.begin('Correct operation '+op)
        result=self.execute(task,'PATCH',preview['path'],preview['inverse'],headers={'If-Match':preview['etag']},reverses=op)
        return {'status':result['status'],'correction':result,'preview':preview}

    def metrics(self):
        last=self.db.execute("SELECT value FROM meta WHERE key='last_archive'").fetchone()
        age=time.time()-float(last[0]) if last else None
        counts={r[0]:r[1] for r in self.db.execute('SELECT status,count(*) FROM operations GROUP BY status')}
        return {'operations':counts,'archive_age_seconds':age,'archive_stale':age is None or age>60,'missing_native_records':int((self.db.execute("SELECT value FROM meta WHERE key='missing_native_records'").fetchone() or ['0'])[0]),'archived_changes':self.db.execute('SELECT count(*) FROM changes').fetchone()[0],'archive_failures':self.db.execute("SELECT count(*) FROM events WHERE kind='archive_failed'").fetchone()[0],'oldest_unresolved_seconds':self._oldest_unresolved(),'unresolved':self.db.execute("SELECT count(*) FROM operations WHERE status IN ('intent','uncertain') OR (status='committed' AND change_id IS NULL)").fetchone()[0]}

    def _oldest_unresolved(self):
        row=self.db.execute("SELECT min(created) FROM operations WHERE status IN ('intent','uncertain') OR (status='committed' AND change_id IS NULL)").fetchone()
        return None if row[0] is None else time.time()-row[0]

    def export(self,path):
        data={'schema_version':1,'lineage':self.lineage,'changes':self.records(),'tasks':[dict(r) for r in self.db.execute('SELECT * FROM tasks')],'operations':[dict(r) for r in self.db.execute('SELECT * FROM operations')],'events':[dict(r) for r in self.db.execute('SELECT * FROM events')]}
        raw=canonical(data).encode(); Path(path).write_bytes(raw)
        digest=hashlib.sha256(raw).hexdigest(); Path(str(path)+'.sha256').write_text(digest+'\n')
        return digest

    def backup(self,path):
        with sqlite3.connect(path) as dest: self.db.backup(dest)
