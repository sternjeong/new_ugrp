"""3분커리 admin console for the separate admin VM (standard library only).

It listens on 127.0.0.1 (reach it with `ssh -L 8300:127.0.0.1:8300 <admin-vm>`), asks for an admin login (HTTP Basic,
passwords stored as scrypt hashes) and forwards /api/admin/* to the service through an SSH tunnel, adding the
service's admin token and the admin's name for the audit log. `backup` pulls a database copy through the same tunnel.

    python3 admin_server.py adduser <name>          # set or change an admin password
    python3 admin_server.py serve                   # run the console
    python3 admin_server.py backup [keep=30]        # save a DB copy into ./backups (run daily by a timer)

Config (admin.json next to this file): {"main_url": "http://127.0.0.1:18200", "token": "...", "port": 8300, "users": {}}
"""
import base64
import getpass
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'admin.json'
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'), '/admin.js': ('admin.js', 'text/javascript; charset=utf-8'),
          '/admin.css': ('admin.css', 'text/css; charset=utf-8')}


def load():
    return json.loads(CONFIG.read_text())


def save(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    CONFIG.chmod(0o600)


def digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64 * 1024 * 1024).hex()


def check(cfg, header):
    if not header or not header.startswith('Basic '):
        return None
    try:
        name, _, password = base64.b64decode(header[6:]).decode().partition(':')
    except (ValueError, UnicodeDecodeError):
        return None
    user = cfg.get('users', {}).get(name)
    if user and hmac.compare_digest(user['hash'], digest(password, user['salt'])):
        return name
    return None


def forward(cfg, method, path, body, admin):
    request = urllib.request.Request(cfg['main_url'].rstrip('/') + path, data=body, method=method,
                                     headers={'Authorization': f'Bearer {cfg["token"]}', 'X-Admin-User': admin,
                                              'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(), response.headers.get('Content-Type', 'application/json')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get('Content-Type', 'application/json')
    except (urllib.error.URLError, OSError):
        return 502, json.dumps({'error': '서비스 서버에 연결하지 못했어요. 터널(curri-admin-tunnel)을 확인해 주세요.'}).encode(), 'application/json'


class Handler(BaseHTTPRequestHandler):
    server_version = 'CurriAdmin/1.0'

    def log_message(self, format, *args):
        pass

    def send(self, status, content, mime):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def admin(self):
        cfg = load()
        name = check(cfg, self.headers.get('Authorization'))
        if name is None:
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="3mincurri-admin", charset="UTF-8"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            time.sleep(1)  # slow down guessing
        return cfg, name

    def do_GET(self):
        cfg, name = self.admin()
        if not name:
            return
        if self.path.startswith('/api/admin/') and not self.path.startswith('/api/admin/backup'):
            return self.send(*forward(cfg, 'GET', self.path, None, name))
        if self.path in STATIC:
            file, mime = STATIC[self.path]
            return self.send(200, (HERE / 'static' / file).read_bytes(), mime)
        self.send(404, b'{}', 'application/json')

    def do_POST(self):
        cfg, name = self.admin()
        if not name:
            return
        if not self.path.startswith('/api/admin/') or self.headers.get('Origin', 'null') not in ('null', f'http://{self.headers.get("Host")}'):
            return self.send(403, b'{}', 'application/json')
        size = int(self.headers.get('Content-Length', '0'))
        self.send(*forward(cfg, 'POST', self.path, self.rfile.read(size) if 0 < size <= 262144 else b'{}', name))


def backup(keep=30):
    cfg = load()
    status, content, _ = forward(cfg, 'GET', '/api/admin/backup', None, 'backup-timer')
    if status != 200 or not content.startswith(b'SQLite format 3'):
        raise SystemExit(f'backup failed: HTTP {status}')
    folder = HERE / 'backups'
    folder.mkdir(exist_ok=True)
    target = folder / f'curri-{time.strftime("%Y%m%d-%H%M")}.sqlite'
    target.write_bytes(content)
    target.chmod(0o600)
    for old in sorted(folder.glob('curri-*.sqlite'))[:-keep]:
        old.unlink()
    print(target)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'serve'
    if command == 'adduser':
        cfg = load()
        name = sys.argv[2]
        password = getpass.getpass(f'{name} 비밀번호(12자 이상): ')
        if len(password) < 12 or password != getpass.getpass('한 번 더: '):
            raise SystemExit('비밀번호가 짧거나 서로 달라요.')
        salt = secrets.token_hex(16)
        cfg.setdefault('users', {})[name] = {'salt': salt, 'hash': digest(password, salt)}
        save(cfg)
        print(f'{name} 저장됨')
    elif command == 'backup':
        backup(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    else:
        cfg = load()
        server = ThreadingHTTPServer(('127.0.0.1', int(cfg.get('port', 8300))), Handler)
        print(f'3분커리 관리자: http://127.0.0.1:{server.server_port} → {cfg["main_url"]}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
