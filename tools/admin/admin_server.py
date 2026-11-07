"""3분커리 admin console for the separate admin VM (standard library only).

Served at https://3mincurri-admin.duckdns.org through Caddy (TLS). Admins sign in on a login page (scrypt password
hashes, HttpOnly Secure session cookie, 5 failed attempts per 15 minutes per IP). /api/admin/* is forwarded to the
service through an SSH tunnel with the service's admin token and the admin's name for the service audit log.
Admin account changes are logged to admin_accounts.log next to this file.

    python3 admin_server.py adduser <name>          # set or change an admin password from the shell
    python3 admin_server.py serve                   # run the console (127.0.0.1:8300, behind Caddy)
    python3 admin_server.py backup [keep=30]        # save a DB copy into ./backups (run daily by a timer)

Config (admin.json next to this file): {"main_url": "http://127.0.0.1:18200", "token": "...", "port": 8300, "users": {}}
"""
from collections import defaultdict, deque
import getpass
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'admin.json'
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'), '/admin.js': ('admin.js', 'text/javascript; charset=utf-8'),
          '/admin.css': ('admin.css', 'text/css; charset=utf-8')}
SESSION_TTL = 12 * 3600
FAILS, FAIL_WINDOW = 5, 15 * 60
sessions = {}               # token hash -> (name, expires)
failures = defaultdict(deque)
lock = threading.Lock()


def load():
    return json.loads(CONFIG.read_text())


def save(cfg):
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    CONFIG.chmod(0o600)


def digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64 * 1024 * 1024).hex()


def set_password(cfg, name, password):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{2,32}', name or ''):
        raise ValueError('관리자 이름은 영문·숫자 2~32자로 정해 주세요.')
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError('비밀번호는 12자 이상이어야 해요.')
    salt = secrets.token_hex(16)
    cfg.setdefault('users', {})[name] = {'salt': salt, 'hash': digest(password, salt), 'created': cfg.get('users', {}).get(name, {}).get('created', time.time())}


def account_log(actor, action, target):
    with open(HERE / 'admin_accounts.log', 'a') as f:
        f.write(json.dumps({'ts': time.time(), 'actor': actor, 'action': action, 'target': target}, ensure_ascii=False) + '\n')


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


def host_status():
    mem = {}
    try:
        for line in open('/proc/meminfo'):
            key, value = line.split(':')
            mem[key] = int(value.split()[0]) // 1024
    except OSError:
        pass
    disk = shutil.disk_usage('/')
    backups = sorted((HERE / 'backups').glob('curri-*.sqlite'))
    return {'load': os.getloadavg(), 'memory_mb': {'total': mem.get('MemTotal'), 'available': mem.get('MemAvailable')},
            'disk_gb': {'total': round(disk.total / 1e9, 1), 'free': round(disk.free / 1e9, 1)},
            'backups': [{'name': b.name, 'mb': round(b.stat().st_size / 1e6, 2), 'time': b.stat().st_mtime} for b in backups[-10:]]}


class Handler(BaseHTTPRequestHandler):
    server_version = 'CurriAdmin/2.0'

    def log_message(self, format, *args):
        pass

    def client_ip(self):
        ip = self.client_address[0]
        forwarded = self.headers.get('X-Forwarded-For', '')
        return forwarded.split(',')[-1].strip() if ip in ('127.0.0.1', '::1') and forwarded else ip

    def send(self, status, content, mime='application/json; charset=utf-8', cookie=None):
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; form-action 'self'")
        if cookie is not None:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(content)

    def current(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except CookieError:
            return None
        token = cookie['curri_admin'].value if 'curri_admin' in cookie else None
        if not token:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        with lock:
            entry = sessions.get(key)
            if not entry or entry[1] < time.time() or entry[0] not in load().get('users', {}):
                sessions.pop(key, None)
                return None
        return entry[0]

    def body(self):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= 262144:
            return b'{}'
        return self.rfile.read(size)

    def do_GET(self):
        if self.path in STATIC:
            file, mime = STATIC[self.path]
            return self.send(200, (HERE / 'static' / file).read_bytes(), mime)
        name = self.current()
        if self.path == '/me':
            return self.send(200, {'name': name})
        if not name:
            return self.send(401, {'error': '로그인이 필요해요.', 'code': 'login'})
        if self.path == '/admins':
            users = load().get('users', {})
            return self.send(200, {'admins': [{'name': n, 'created': u.get('created')} for n, u in users.items()], 'me': name})
        if self.path == '/host':
            return self.send(200, host_status())
        if self.path.startswith('/api/admin/') and not self.path.startswith('/api/admin/backup'):
            status, content, mime = forward(load(), 'GET', self.path, None, name)
            return self.send(status, content, mime)
        self.send(404, {'error': '없는 주소예요.'})

    def do_POST(self):
        host = self.headers.get('Host', '')
        if self.headers.get('Origin') not in (f'https://{host}', f'http://{host}') or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.send(403, {'error': '같은 사이트에서 다시 요청해 주세요.'})
        try:
            data = json.loads(self.body() or b'{}')
        except ValueError:
            return self.send(400, {'error': '입력 형식이 올바르지 않아요.'})
        secure = '; Secure' if self.headers.get('X-Forwarded-Proto') == 'https' else ''
        if self.path == '/login':
            ip = self.client_ip()
            with lock:
                recent = failures[ip]
                while recent and recent[0] < time.time() - FAIL_WINDOW:
                    recent.popleft()
                if len(recent) >= FAILS:
                    return self.send(429, {'error': '로그인 실패가 많아요. 15분 뒤 다시 시도해 주세요.'})
            cfg = load()
            user = cfg.get('users', {}).get(str(data.get('name', '')))
            if not user or not hmac.compare_digest(user['hash'], digest(str(data.get('password', '')), user['salt'])):
                with lock:
                    failures[ip].append(time.time())
                time.sleep(1)
                return self.send(401, {'error': '이름 또는 비밀번호가 맞지 않아요.'})
            token = secrets.token_urlsafe(32)
            with lock:
                sessions[hashlib.sha256(token.encode()).hexdigest()] = (data['name'], time.time() + SESSION_TTL)
            account_log(data['name'], 'login', ip)
            return self.send(200, {'name': data['name']}, cookie=f'curri_admin={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}{secure}')
        name = self.current()
        if not name:
            return self.send(401, {'error': '로그인이 필요해요.', 'code': 'login'})
        if self.path == '/logout':
            with lock:
                for key, entry in list(sessions.items()):
                    if entry[0] == name:
                        sessions.pop(key)
            return self.send(200, {'ok': True}, cookie=f'curri_admin=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}')
        if self.path == '/admins':
            cfg = load()
            action, target = data.get('action'), str(data.get('name', ''))
            try:
                if action == 'add':
                    if target in cfg.get('users', {}):
                        raise ValueError('이미 있는 이름이에요.')
                    set_password(cfg, target, data.get('password'))
                elif action == 'password':
                    me = cfg['users'][name]
                    if not hmac.compare_digest(me['hash'], digest(str(data.get('current', '')), me['salt'])):
                        raise ValueError('현재 비밀번호가 맞지 않아요.')
                    set_password(cfg, name, data.get('password'))
                    target = name
                elif action == 'delete':
                    if target == name:
                        raise ValueError('자기 계정은 지울 수 없어요.')
                    if target not in cfg.get('users', {}):
                        raise ValueError('없는 관리자예요.')
                    del cfg['users'][target]
                else:
                    raise ValueError('알 수 없는 작업이에요.')
            except ValueError as exc:
                return self.send(400, {'error': str(exc)})
            save(cfg)
            account_log(name, action, target)
            return self.send(200, {'ok': True})
        if self.path.startswith('/api/admin/'):
            status, content, mime = forward(load(), 'POST', self.path, json.dumps(data).encode(), name)
            return self.send(status, content, mime)
        self.send(404, {'error': '없는 주소예요.'})


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
        if password != getpass.getpass('한 번 더: '):
            raise SystemExit('두 비밀번호가 달라요.')
        set_password(cfg, name, password)
        save(cfg)
        account_log('shell', 'add', name)
        print(f'{name} 저장됨')
    elif command == 'backup':
        backup(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    else:
        cfg = load()
        server = ThreadingHTTPServer(('127.0.0.1', int(cfg.get('port', 8300))), Handler)
        server.daemon_threads = True
        print(f'3분커리 관리자: http://127.0.0.1:{server.server_port} → {cfg["main_url"]}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
