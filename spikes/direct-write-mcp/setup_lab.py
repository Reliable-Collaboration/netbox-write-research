#!/usr/bin/env python3
"""Create isolated fixtures/least-privilege identity in the EXISTING nbai-spike lab.

This helper is deliberately fixed to the synthetic lab, not arbitrary production.
The MCP server itself only needs a normal config and has no dependency on this helper.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid
from direct_mcp.api import NetBox

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STATE = HERE / '.state'
os.umask(0o077)
STATE.mkdir(mode=0o700, exist_ok=True)
admin = json.loads((ROOT / '.lab/secrets.json').read_text())['token']
api = NetBox('http://127.0.0.1:18780', admin)
fixtures = json.loads((ROOT / '.lab/fixtures.json').read_text())
ids = []
for name in ['direct-spike-target', 'direct-spike-secondary']:
    found = api.get('dcim/devices/?name=' + name)['body']['results']
    if found:
        ids.append(found[0]['id'])
    else:
        response = api.request('POST', 'dcim/devices/', {'name': name, 'site': fixtures['site'],
                               'device_type': fixtures['type'], 'role': fixtures['role'],
                               'status': 'active', 'description': 'A'})
        assert response['status'] == 201, response
        ids.append(response['body']['id'])
token_path = STATE / 'token'
if not token_path.exists():
    token_path.write_text(secrets.token_hex(20))
script = '''
from django.contrib.auth import get_user_model
from users.models import Token,ObjectPermission
from core.models import ObjectType
u,_=get_user_model().objects.get_or_create(username='direct-spike-agent',defaults={'is_superuser':False})
Token.objects.get_or_create(plaintext=TOKEN,defaults={'token':TOKEN,'version':1,'user':u,'write_enabled':True})
p,_=ObjectPermission.objects.update_or_create(name='direct-spike-device-edits',defaults={'actions':['view','change'],'constraints':{'id__in':IDS}})
p.users.add(u);p.object_types.add(ObjectType.objects.get(app_label='dcim',model='device'))
p,_=ObjectPermission.objects.get_or_create(name='direct-spike-history',defaults={'actions':['view']})
p.users.add(u);p.object_types.add(ObjectType.objects.get(app_label='core',model='objectchange'))
print('Restricted direct-write lab identity ready')
'''.replace('TOKEN', repr(token_path.read_text().strip())).replace('IDS', repr(ids))
subprocess.run(['podman', 'exec', '-i', 'nbai-spike-netbox', '/opt/netbox/venv/bin/python',
                '/opt/netbox/netbox/manage.py', 'shell'], input=script, text=True, check=True)
config_path = STATE / 'config.json'
config = {'netbox_url': api.url, 'token_file': str(token_path), 'journal': str(STATE / 'journal.sqlite'),
          'instance_id': str(uuid.uuid4()), 'actor': 'direct-spike-agent', 'allowed_device_ids': ids}
if config_path.exists():
    config['instance_id'] = json.loads(config_path.read_text())['instance_id']
config_path.write_text(json.dumps(config, indent=2) + '\n')
print('Config:', config_path)
print('Synthetic device IDs:', ids)
