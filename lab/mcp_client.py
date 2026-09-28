"""Minimal newline-delimited JSON-RPC MCP stdio driver with bounded reads."""
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from lab import ROOT, STATE, config

class MCP:
    def __init__(self, command, env=None):
        self.p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        self.q=queue.Queue(); self.stderr=[]; self.transcript=[]; self.seq=0
        def read():
            for line in self.p.stdout:
                try: self.q.put(json.loads(line))
                except ValueError: self.q.put({'invalid_line':line})
            self.q.put({'eof':True})
        def err():
            for line in self.p.stderr: self.stderr.append(line)
        threading.Thread(target=read,daemon=True).start()
        threading.Thread(target=err,daemon=True).start()
        self.call('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'nbai-spike','version':'0.1'}})
        self.notify('notifications/initialized',{})

    def notify(self,method,params):
        self.p.stdin.write(json.dumps({'jsonrpc':'2.0','method':method,'params':params})+'\n'); self.p.stdin.flush()

    def call(self,method,params=None):
        self.seq+=1; request={'jsonrpc':'2.0','id':self.seq,'method':method,'params':params or {}}
        start=time.monotonic()
        self.p.stdin.write(json.dumps(request)+'\n'); self.p.stdin.flush()
        while True:
            try: response=self.q.get(timeout=max(.01,90-(time.monotonic()-start)))
            except queue.Empty: raise TimeoutError('MCP timeout: '+''.join(self.stderr)[-1000:])
            if response.get('eof'): raise RuntimeError('MCP exited: '+''.join(self.stderr)[-1500:])
            if response.get('id')==self.seq: break
        self.transcript.append({'request':request,'response':response,'seconds':time.monotonic()-start})
        return response

    def tool(self,name,**args):
        return self.call('tools/call',{'name':name,'arguments':args})

    def close(self):
        self.p.stdin.close()
        try: self.p.wait(timeout=5)
        except subprocess.TimeoutExpired: self.p.terminate(); self.p.wait(timeout=5)

def candidate(name):
    c=config(); env=os.environ.copy()
    if name=='nbox':
        cfg=STATE/'nbox.toml'
        cfg.write_text('[profiles.default]\nurl = "http://127.0.0.1:18780"\n')
        env['NBOX_TOKEN']=c['token']
        return MCP([str(STATE/'build/nbox/nbox'),'--config',str(cfg),'--profile','default','serve','--local-writes'],env)
    conf=STATE/'sdk-config/netbox-sdk'; conf.mkdir(parents=True,exist_ok=True)
    (conf/'config.json').write_text(json.dumps({'base_url':'http://nbai-spike-netbox:8080','token_version':'v1','token_secret':c['token']}))
    (conf/'config.json').chmod(0o600)
    envfile=STATE/'candidate.env'
    envfile.write_text(f"NETBOX_URL=http://nbai-spike-netbox:8080\nNETBOX_TOKEN={c['token']}\n")
    envfile.chmod(0o600)
    command=['podman','run','--rm','-i','--label','io.netbox-ai-spike.project=nbai-spike','--network','nbai-spike','--env-file',str(envfile)]
    if name.startswith('sdk'): command+=['-v',str(STATE/'sdk-config/netbox-sdk/config.json')+':/root/.config/netbox-sdk/config.json:ro']
    command+=['localhost/nbai-spike/'+name]
    return MCP(command)

if __name__=='__main__':
    import sys
    name=sys.argv[1]; c=candidate(name)
    result=c.call('tools/list')
    (ROOT/'evidence'/f'{name}-tools.json').write_text(json.dumps(result,indent=2))
    print(name,[t['name'] for t in result.get('result',{}).get('tools',[])])
    c.close()
