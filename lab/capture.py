from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
class Capture(BaseHTTPRequestHandler):
    def do_POST(self):
        body=self.rfile.read(int(self.headers['Content-Length']))
        with open('/events/webhooks.jsonl','a') as f:
            f.write(json.dumps({'received':time.time(),'body':json.loads(body)})+'\n')
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
HTTPServer(('0.0.0.0',8000),Capture).serve_forever()
