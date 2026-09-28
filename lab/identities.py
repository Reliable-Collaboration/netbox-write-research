import json
import secrets
from lab import STATE, PREFIX, pod
p=STATE/'identities.json'
if not p.exists():
    p.write_text(json.dumps({k:secrets.token_hex(20) for k in ['observer','second','restricted']}));p.chmod(0o600)
tokens=json.loads(p.read_text())
script='''
from django.contrib.auth import get_user_model
from users.models import Token,ObjectPermission
from core.models import ObjectType
for name,token in TOKENS.items():
    u,_=get_user_model().objects.get_or_create(username='spike-'+name,defaults={'is_superuser':name!='restricted'})
    Token.objects.get_or_create(plaintext=token,defaults={'token':token,'version':1,'user':u,'write_enabled':name!='observer'})
u=get_user_model().objects.get(username='spike-restricted')
p,_=ObjectPermission.objects.get_or_create(name='spike-device-view',defaults={'actions':['view']})
p.object_types.add(ObjectType.objects.get(app_label='dcim',model='device'));p.users.add(u)
print('Three lab identities ready')
'''.replace('TOKENS',repr(tokens))
pod('exec','-i',PREFIX+'-netbox','/opt/netbox/venv/bin/python','/opt/netbox/netbox/manage.py','shell',input=script,text=True)
