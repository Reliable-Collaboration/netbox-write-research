"""Restore a baseline DB backup into a separately named PostgreSQL database, upgrade it."""
import json
import subprocess
import time
from api import API
from lab import ROOT,STATE,PREFIX,LABEL,pod
from recovery import Coordinator

def main():
    run=ROOT/'evidence/runs'/('upgrade-'+time.strftime('%Y%m%dT%H%M%S'));run.mkdir(parents=True)
    baseline=API(); old=baseline.all('core/object-changes/?limit=1000&ordering=id')
    dump=STATE/'baseline.dump'
    with dump.open('wb') as f: pod('exec',PREFIX+'-postgres','pg_dump','-U','netbox','-Fc','netbox',stdout=f)
    db='upgrade_'+str(int(time.time()))
    pod('exec',PREFIX+'-postgres','createdb','-U','netbox',db)
    with dump.open('rb') as f: pod('exec','-i',PREFIX+'-postgres','pg_restore','-U','netbox','-d',db,stdin=f)
    # First prove the copied DB has all history rows before applying migrations.
    count=pod('exec',PREFIX+'-postgres','psql','-U','netbox','-d',db,'-Atc','SELECT count(*) FROM core_objectchange',capture_output=True,text=True).stdout.strip()
    assert int(count)==len(old),(count,len(old))
    env=(STATE/'netbox.env').read_text().replace('DB_NAME=netbox','DB_NAME='+db).replace('REDIS_DATABASE=0','REDIS_DATABASE=4').replace('REDIS_CACHE_DATABASE=1','REDIS_CACHE_DATABASE=5')
    (STATE/'upgrade.env').write_text(env);(STATE/'upgrade.env').chmod(0o600)
    image=json.loads((ROOT/'evidence/runtime-images.json').read_text())['docker.io/netboxcommunity/netbox:v4.7.1-5.1.1']['digests'][0]
    if subprocess.run(['podman','image','exists',image]).returncode: pod('pull',image)
    info=json.loads(pod('image','inspect',image,capture_output=True,text=True).stdout)[0]
    name=PREFIX+'-upgrade'
    if subprocess.run(['podman','container','exists',name]).returncode==0: pod('rm','-f',name)
    pod('run','-d','--name',name,'--label',LABEL,'--network',PREFIX,'--env-file',str(STATE/'upgrade.env'),'-p','127.0.0.1:18782:8080','--memory','3g',info['RepoDigests'][0])
    api=API(base='http://127.0.0.1:18782')
    for _ in range(180):
        try:
            if api.request('GET','status/')['status']==200:break
        except Exception:pass
        time.sleep(2)
    else: raise RuntimeError('Upgrade instance not ready')
    new=api.all('core/object-changes/?limit=1000&ordering=id')
    old_by={r['id']:r for r in old};new_by={r['id']:r for r in new}
    keys=['prechange_data','postchange_data','request_id','message','action']
    differences=[]
    for i in old_by:
        for k in keys:
            before=old_by[i][k]; after=new_by[i][k]
            if before!=after:
                differences.append({'id':i,'field':k,'before':before,'after':after})
                assert isinstance(before,dict) and isinstance(after,dict) and all(after.get(key)==value for key,value in before.items()), differences[-1]
    (run/'pre-upgrade-history.json').write_text(json.dumps(old,indent=2))
    (run/'snapshot-differences.json').write_text(json.dumps(differences,indent=2))
    ids=json.loads((STATE/'fixtures.json').read_text());path=f"dcim/devices/{ids['recovery']}/"
    api.ok('PATCH',path,{'description':'upgrade-A'})
    c=Coordinator(STATE/(db+'-journal.sqlite'),api=api,lineage=db)
    op=c.execute(c.begin('Upgrade recovery drill'),'PATCH',path,{'description':'upgrade-B'})
    undo=c.undo(op['id']);assert undo['status']=='committed',undo
    assert api.ok('GET',path)['description']=='upgrade-A'
    c.export(run/'recovery.json')
    # Native-history deletion is scoped ONLY to the disposable restored database.
    # Prove exported evidence survives actual loss of native history.
    archived=c.records()
    pod('exec',PREFIX+'-postgres','psql','-U','netbox','-d',db,'-c','DELETE FROM core_objectchange',capture_output=True)
    assert api.all('core/object-changes/?limit=1000')==[]
    c.archive();assert c.records()==archived
    backup=STATE/'upgrade-archive-backup.sqlite';backup.unlink(missing_ok=True);c.backup(backup)
    restored=Coordinator(backup,api=api,lineage=db);assert restored.records()==archived;restored.db.close();c.db.close()
    report={'baseline':'4.6.10','upgrade':'4.7.1','image_digest':info['RepoDigests'][0],'backup_row_count':int(count),'original_snapshot_values_preserved':len(old),'snapshot_extensions':len(differences),'scalar_recovery':'passed','native_history_loss_and_archive_restore':'passed','lineage':db}
    (run/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
