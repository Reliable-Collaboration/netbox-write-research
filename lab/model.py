"""Start the exact local inference runtime and weight artifact used by this spike."""
import hashlib
import json
import subprocess
import urllib.request
from lab import ROOT,STATE,PREFIX,LABEL,pod
m=json.loads((ROOT/'evidence/model-manifest.json').read_text())
p=STATE/'models/qwen.gguf';p.parent.mkdir(parents=True,exist_ok=True)
if not p.exists():
    urllib.request.urlretrieve('https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/'+m['gguf_revision']+'/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf',p)
assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==m['gguf_sha256']
if subprocess.run(['podman','container','exists',PREFIX+'-model']).returncode:
    pod('run','-d','--name',PREFIX+'-model','--label',LABEL,'--network',PREFIX,'--memory','3g','--cpus','8','-p','127.0.0.1:18781:8080','-v',str(p)+':/model.gguf:ro',m['runtime_digest'],'-m','/model.gguf','--host','0.0.0.0','--port','8080','-c','8192','-t','8','--parallel','1')
else:pod('start',PREFIX+'-model')
