import json
from api import API
from lab import STATE

def seed():
    api=API(); ids={}
    def add(label,path,data,key='slug'):
        found=api.ok('GET',path+'?'+key+'='+str(data[key]))['results']
        obj=found[0] if found else api.ok('POST',path,data)
        ids[label]=obj['id']; return obj['id']
    site=add('site','dcim/sites/',{'name':'Spike Site','slug':'spike-site'})
    add('site2','dcim/sites/',{'name':'Spike Site Two','slug':'spike-site-two'})
    m=add('manufacturer','dcim/manufacturers/',{'name':'Spike Maker','slug':'spike-maker'})
    t=add('type','dcim/device-types/',{'model':'Spike Model','slug':'spike-model','manufacturer':m})
    role=add('role','dcim/device-roles/',{'name':'Spike Role','slug':'spike-role','color':'2196f3'})
    for name in ['baseline','sdk','zenix','nbox','recovery']:
        add(name,'dcim/devices/',{'name':'spike-'+name,'site':site,'device_type':t,'role':role,'status':'active','description':'A'},'name')
    add('tag','extras/tags/',{'name':'spike-tag','slug':'spike-tag','color':'2196f3'})
    add('prefix','ipam/prefixes/',{'prefix':'192.0.2.0/24','status':'active'},'prefix')
    (STATE/'fixtures.json').write_text(json.dumps(ids,indent=2))
    return ids

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--reset',action='store_true');args=p.parse_args()
    ids=seed()
    if args.reset:
        api=API()
        for name in ['baseline','sdk','zenix','nbox','recovery']:
            api.ok('PATCH',f"dcim/devices/{ids[name]}/",{'description':'A','serial':'','asset_tag':None,'status':'active','tags':[]})
        print('Reset known device fields; retained all history and ancillary test objects.')
    print(json.dumps(ids,indent=2))
