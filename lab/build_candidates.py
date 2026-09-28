#!/usr/bin/env python3
"""Fetch pinned OSS candidates and build isolated runtimes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request
from lab import ROOT, STATE, pod

CANDIDATES = {
 'sdk': ('emersonfelipesp/netbox-sdk','b539b53eefbe289315fcbccf9bb34930bb09af37'),
 'zenix': ('ZenixSolutions/netbox-mcp-server','42d30025223dd525b1783d19f1fdf9d67f5168ba'),
}

def fetch(url, path):
    if not path.exists():
        urllib.request.urlretrieve(url,path)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    build=STATE/'build'; build.mkdir(parents=True,exist_ok=True)
    runtime=json.loads((ROOT/'evidence/runtime-images.json').read_text())
    python_image=runtime['docker.io/library/python:3.13-slim']['digests'][0]
    manifest={}
    for name,(repo,commit) in CANDIDATES.items():
        archive=build/(name+'.tgz')
        sha=fetch(f'https://api.github.com/repos/{repo}/tarball/{commit}',archive)
        expected=next(x['archive_sha256'] for x in json.loads((ROOT/'research/evidence/source-snapshots.json').read_text())['sources'] if x['repository']==repo)
        assert sha==expected, 'Source archive checksum mismatch: '+repo
        target=build/name; target.mkdir(exist_ok=True)
        if not (target/'src').exists():
            with tarfile.open(archive) as t:
                top=t.getnames()[0].split('/')[0]
                t.extractall(target,filter='data')
            (target/top).rename(target/'src')
        node=json.loads((ROOT/'lab/images.lock.json').read_text())['node']['digest']
        containerfile=(f'FROM {node}\nWORKDIR /app\nCOPY src/ ./\nRUN npm ci && npm run build\nENTRYPOINT ["node","dist/index.js"]\n' if name=='zenix' else
          f'FROM {python_image}\nWORKDIR /app\nCOPY src/ ./\nCOPY constraints.txt /constraints.txt\nRUN pip install --no-cache-dir -c /constraints.txt ".[mcp]" && pip freeze > /app/installed.txt\nENTRYPOINT ["nbx-mcp","--allow-mutations"]\n')
        if name=='sdk':
            locked=(ROOT/'lab/sdk-dependencies.lock').read_text().splitlines()
            (target/'constraints.txt').write_text('\n'.join(x for x in locked if not x.startswith('netbox-sdk'))+'\n')
        (target/'Containerfile').write_text(containerfile)
        with (build/(name+'-build.log')).open('w') as log:
            result=subprocess.run(['podman','build','-t','localhost/nbai-spike/'+name,str(target)],stdout=log,stderr=subprocess.STDOUT)
        manifest[name]={'repository':repo,'commit':commit,'archive_sha256':sha,'build_exit':result.returncode}
        print(name,manifest[name],flush=True)
    # Keep the repair separate from the unchanged upstream image.
    patched=build/'sdk-patched'; patched.mkdir(exist_ok=True)
    shutil.copy(build/'sdk/src/netbox_mcp/app.py',patched/'app.py')
    source=(patched/'app.py').read_text().replace('(**locals())','(**{k: v for k, v in locals().items() if k != "active"})')
    (patched/'app.py').write_text(source)
    (patched/'Containerfile').write_text('FROM localhost/nbai-spike/sdk\nCOPY app.py /usr/local/lib/python3.13/site-packages/netbox_mcp/app.py\nCOPY app.py /app/netbox_mcp/app.py\n')
    pod('build','-t','localhost/nbai-spike/sdk-patched',str(patched))
    url='https://github.com/lance0/nbox/releases/download/v0.14.1/nbox-x86_64-unknown-linux-musl.tar.gz'
    archive=build/'nbox.tgz'; sha=fetch(url,archive)
    assert sha=='a3f5fb9e97ed001d3d4ef5807f5ea36f5dcd9271dd6e74c2afb42ba56c3d5e28'
    with tarfile.open(archive) as t: t.extractall(build/'nbox',filter='data')
    manifest['nbox']={'release':'v0.14.1','commit':'214608d8ce573e554af4e887383d90ac9c2628f9','url':url,'archive_sha256':sha,'note':'Release binary differs from research master snapshot; no upstream source modifications.'}
    (ROOT/'evidence/candidate-builds.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__': main()
