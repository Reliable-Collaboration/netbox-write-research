#!/usr/bin/env python3
"""Actual MCP round-trip: read → task → edit → history → undo, on lab fixtures."""
import json
from pathlib import Path
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'tests'))
from mcp_client import Client

config = json.loads((HERE / '.state/config.json').read_text())
client = Client([sys.executable, str(HERE / 'run.py'), '--config', str(HERE / '.state/config.json')])
try:
    device = config['allowed_device_ids'][0]
    initial = client.tool('read_device', device_id=device)
    task = client.tool('begin_task', purpose='Direct REST MCP demonstration: temporary description edit')
    op = client.tool('update_device', task_id=task['task_id'], operation_key='demo:' + str(uuid.uuid4()),
                     device_id=device, expected_etag=initial['etag'], changes={'description': 'Direct MCP demo ' + uuid.uuid4().hex[:8]})
    if op.get('state') != 'applied':
        raise RuntimeError(op)
    bundle = client.tool('recovery_bundle', operation_id=op['id'])
    assert bundle['inverse']['description'] == initial['values']['description']
    preview = client.tool('preview_undo', operation_id=op['id'])
    if preview['status'] != 'ready':
        raise RuntimeError(preview)
    correction = client.tool('undo_operation', operation_id=op['id'], operation_key='demo-undo:' + str(uuid.uuid4()))
    assert correction['status'] == 'applied', correction
    final = client.tool('read_device', device_id=device)
    assert final['values'] == initial['values']
    output = {'task_id': task['task_id'], 'operation_id': op['id'], 'native_change_id': op['native_id'],
              'correction_id': correction['correction']['id'], 'values_restored': True,
              'write_path': 'Agent MCP → this server → NetBox REST', 'transcript': client.transcript}
    path = HERE / 'evidence' / ('demo-' + time.strftime('%Y%m%dT%H%M%S') + '.json')
    path.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({k: v for k, v in output.items() if k != 'transcript'}, indent=2))
    print('Evidence:', path)
finally:
    client.close()
