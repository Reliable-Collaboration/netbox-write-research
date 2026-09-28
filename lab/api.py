"""Small REST client; never retries mutations or logs credentials."""
import json
import urllib.request
import urllib.error
from lab import config

class API:
    def __init__(self, base='http://127.0.0.1:18780', token=None):
        self.base=base
        self.token=token if token is not None else config()['token']

    def request(self, method, path, data=None, headers=None):
        req=urllib.request.Request(self.base+'/api/'+path.lstrip('/'),
            data=None if data is None else json.dumps(data).encode(),method=method,
            headers={'Authorization':'Token '+self.token,'Content-Type':'application/json',**(headers or {})})
        try:
            r=urllib.request.urlopen(req,timeout=45)
        except urllib.error.HTTPError as exc:
            r=exc
        raw=r.read()
        try: body=json.loads(raw) if raw else None
        except ValueError: body=raw.decode(errors='replace')[:1000]
        return {'status':r.status,'headers':dict(r.headers.items()),'body':body}

    def ok(self, method, path, data=None, headers=None):
        r=self.request(method,path,data,headers)
        if not 200<=r['status']<300: raise RuntimeError(f'{method} {path}: {r}')
        return r['body']

    def all(self,path):
        result=[]
        while path:
            page=self.ok('GET',path)
            result.extend(page['results'])
            nxt=page.get('next')
            path=nxt.split('/api/',1)[1] if nxt else None
        return result
