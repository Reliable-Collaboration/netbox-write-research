"""Record dependency license metadata; unknown fields need source review."""
import json
from lab import ROOT,pod
py='''import importlib.metadata as m,json
print(json.dumps([{'name':d.metadata['Name'],'version':d.version,'license_expression':d.metadata.get('License-Expression'),'license':d.metadata.get('License'),'classifiers':[c for c in d.metadata.get_all('Classifier',[]) if c.startswith('License')]} for d in m.distributions()]))'''
r={}
for name in ['sdk','zenix']:
 if name=='sdk':data=pod('run','--rm','--entrypoint','python','localhost/nbai-spike/sdk','-c',py,capture_output=True,text=True).stdout
 else:
  js='''const fs=require('fs'),path=require('path');let out=[];function walk(p){for(const x of fs.readdirSync(p,{withFileTypes:true})){const f=path.join(p,x.name);if(x.isDirectory())walk(f);else if(x.name==='package.json'){try{const d=JSON.parse(fs.readFileSync(f));if(d.name&&d.version)out.push({name:d.name,version:d.version,license:d.license})}catch{}}}}walk('/app/node_modules');console.log(JSON.stringify(out));'''
  data=pod('run','--rm','--entrypoint','node','localhost/nbai-spike/zenix','-e',js,capture_output=True,text=True).stdout
 r[name]=json.loads(data)
(ROOT/'evidence/dependency-licenses.json').write_text(json.dumps(r,indent=2)+'\n')
print({k:len(v) for k,v in r.items()})
