"""SQLite ownership, guest limits and local password accounts."""
from contextlib import contextmanager
import hashlib
import hmac
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time


class LoginRequired(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class ProfileRequired(Exception):
    pass


# Added after the MVP; existing local DBs are migrated in place.
USER_COLUMNS = {'nickname': 'TEXT', 'role': "TEXT NOT NULL DEFAULT 'student'", 'lab_id': 'TEXT', 'account': "TEXT NOT NULL DEFAULT '{}'", 'dummy': 'INTEGER NOT NULL DEFAULT 0',
                'email_verified': 'INTEGER NOT NULL DEFAULT 0', 'notify': "TEXT NOT NULL DEFAULT '{}'", 'deleted': 'INTEGER NOT NULL DEFAULT 0',
                'suspended': 'INTEGER NOT NULL DEFAULT 0', 'grad_status': 'TEXT', 'created': 'REAL'}
NOTIFY_DEFAULTS = {'messages': True, 'meetings': True, 'watch': True, 'qna': True}
REQUIRED_ACCOUNT = ('real_name', 'school')


def profile_complete(nickname, account):
    return bool(nickname) and all(account.get(k) for k in REQUIRED_ACCOUNT) and bool(account.get('interest_tags') or account.get('interest_text'))


def password_digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64*1024*1024).hex()


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt TEXT NOT NULL,
                password_hash TEXT NOT NULL, profile TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id),
                first_lab_id TEXT, profile TEXT NOT NULL DEFAULT '{}', expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS explorations (
                owner TEXT NOT NULL, lab_id TEXT NOT NULL, selected_ids TEXT NOT NULL,
                guide TEXT, note TEXT NOT NULL, saved INTEGER NOT NULL,
                previous_versions TEXT NOT NULL DEFAULT '[]', updated REAL NOT NULL,
                PRIMARY KEY(owner,lab_id));
            CREATE TABLE IF NOT EXISTS guide_variant_counts (
                day TEXT NOT NULL, variant TEXT NOT NULL, event TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day, variant, event));
            ''')
            existing = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
            for name, kind in USER_COLUMNS.items():
                if name not in existing:
                    db.execute(f'ALTER TABLE users ADD COLUMN {name} {kind}')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS users_nickname ON users(nickname COLLATE NOCASE) WHERE nickname IS NOT NULL')

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_session(self, token):
        if not isinstance(token, str) or len(token) > 200:
            return None
        with self.db() as db:
            row = db.execute('SELECT * FROM sessions WHERE token=? AND expires>?', (token_hash(token), time.time())).fetchone()
            return dict(row) if row else None

    def session(self, token):
        if token and self.get_session(token):
            return token
        new = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute('INSERT INTO sessions(token,expires) VALUES (?,?)', (token_hash(new), time.time() + 30 * 86400))
        return new

    @staticmethod
    def _owner(session):
        return f'user:{session["user_id"]}' if session['user_id'] else f'guest:{session["token"]}'

    def _session(self, db, token):
        row = db.execute('SELECT * FROM sessions WHERE token=? AND expires>?', (token_hash(token), time.time())).fetchone()
        if row is None:
            raise InvalidCredentials('세션이 만료되었습니다. 새로고침해 주세요.')
        return row

    def _authorize(self, db, session, lab_id):
        if not session['user_id']:
            if session['first_lab_id'] and session['first_lab_id'] != lab_id:
                raise LoginRequired('다른 연구실도 탐색하려면 로그인해 주세요. 첫 탐색은 그대로 이어집니다.')
            if not session['first_lab_id']:
                db.execute('UPDATE sessions SET first_lab_id=? WHERE token=?', (lab_id, session['token']))

    def open_lab(self, token, lab_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            session = self._session(db, token)
            self._authorize(db, session, lab_id)

    def set_profile(self, token, profile):
        encoded = json.dumps(profile, ensure_ascii=False)
        with self.db() as db:
            session = self._session(db, token)
            db.execute('UPDATE sessions SET profile=? WHERE token=?', (encoded, session['token']))
            if session['user_id']:
                db.execute('UPDATE users SET profile=? WHERE id=?', (encoded, session['user_id']))

    @staticmethod
    def _decode(row):
        r = dict(row)
        for key in ('selected_ids', 'guide', 'previous_versions'):
            r[key] = json.loads(r[key]) if r[key] is not None else None
        r['saved'] = bool(r['saved'])
        r.pop('owner', None)
        return r

    def snapshot(self, token):
        with self.db() as db:
            session = self._session(db, token)
            user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone() if session['user_id'] else None
            rows = db.execute('SELECT * FROM explorations WHERE owner=? ORDER BY updated DESC', (self._owner(session),)).fetchall()
            profile = user['profile'] if user else session['profile']
            return {'user': self.public_self(user) if user else None, 'profile': json.loads(profile), 'first_lab_id': session['first_lab_id'], 'explorations': [self._decode(row) for row in rows]}

    @staticmethod
    def public_self(user):
        """What the signed-in user sees about their own account. Never includes credentials."""
        account = json.loads(user['account'])
        keys = user.keys()
        notify = {**NOTIFY_DEFAULTS, **json.loads(user['notify'] if 'notify' in keys else '{}')}
        return {'email': user['email'], 'nickname': user['nickname'], 'role': user['role'], 'lab_id': user['lab_id'], 'account': account,
                'profile_complete': profile_complete(user['nickname'], account), 'email_verified': bool(user['email_verified']) if 'email_verified' in keys else False,
                'notify': notify, 'grad_status': user['grad_status'] if 'grad_status' in keys else None}

    def current_user(self, token, complete=False):
        """The signed-in user row for this session; raises LoginRequired (or ProfileRequired)."""
        with self.db() as db:
            session = self._session(db, token)
            user = db.execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone() if session['user_id'] else None
        if user is None or user['deleted']:
            raise LoginRequired('로그인이 필요해요.')
        if user['suspended']:
            raise LoginRequired('이용이 제한된 계정이에요. 문의는 개인정보 처리방침의 연락처로 보내 주세요.')
        if complete and not profile_complete(user['nickname'], json.loads(user['account'])):
            raise ProfileRequired('필수 프로필(이름·별명·학교·관심 분야)을 먼저 완성해 주세요.')
        return dict(user)

    def update_account(self, token, nickname, account):
        user = self.current_user(token)
        with self.db() as db:
            try:
                db.execute('UPDATE users SET nickname=?, account=? WHERE id=?', (nickname, json.dumps(account, ensure_ascii=False), user['id']))
            except sqlite3.IntegrityError:
                raise ValueError('이미 사용 중인 별명이에요. 다른 별명을 입력해 주세요.') from None

    def save_exploration(self, token, lab_id, selected_ids, guide, note, saved):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            session = self._session(db, token)
            self._authorize(db, session, lab_id)
            db.execute('''INSERT INTO explorations(owner,lab_id,selected_ids,guide,note,saved,updated)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(owner,lab_id) DO UPDATE SET
                selected_ids=excluded.selected_ids,guide=excluded.guide,note=excluded.note,
                saved=excluded.saved,updated=excluded.updated''',
                (self._owner(session), lab_id, json.dumps(selected_ids), json.dumps(guide, ensure_ascii=False) if guide is not None else None, note, int(saved), time.time()))

    def count_guide_event(self, variant, event):
        if variant not in ('A', 'B') or event not in ('explore', 'guide'):
            raise ValueError('Invalid guide event')
        day = time.strftime('%Y-%m-%d', time.gmtime())
        with self.db() as db:
            db.execute('''INSERT INTO guide_variant_counts(day, variant, event, count) VALUES (?, ?, ?, 1)
                          ON CONFLICT(day, variant, event) DO UPDATE SET count=count+1''',
                       (day, variant, event))

    def authenticate(self, token, email, password, register=False, nickname=None, account=None):
        email = email.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254:
            raise ValueError('이메일 형식을 확인해 주세요.')
        if not 10 <= len(password) <= 128:
            raise ValueError('비밀번호는 10~128자로 입력해 주세요.')
        # scrypt includes a per-user random salt. No plaintext credentials are stored.
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            guest = self._session(db, token)
            if guest['user_id']:
                raise ValueError('이미 로그인되어 있습니다.')
            user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if register and user:
                raise ValueError('이미 등록된 이메일입니다. 로그인해 주세요.')
            if register and nickname and db.execute('SELECT 1 FROM users WHERE nickname=? COLLATE NOCASE', (nickname,)).fetchone():
                raise ValueError('이미 사용 중인 별명이에요. 다른 별명을 입력해 주세요.')
            salt = secrets.token_hex(16) if register else (user['salt'] if user else '0' * 32)
            digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64*1024*1024).hex()
            if register:
                try:
                    uid = db.execute('INSERT INTO users(email,salt,password_hash,nickname,account,created) VALUES (?,?,?,?,?,?)', (email, salt, digest, nickname, json.dumps(account or {}, ensure_ascii=False), time.time())).lastrowid
                except sqlite3.IntegrityError:
                    raise ValueError('이미 등록된 이메일 또는 별명이에요.') from None
                profile = guest['profile']
            else:
                if not user or user['deleted'] or not hmac.compare_digest(user['password_hash'], digest):
                    raise InvalidCredentials('이메일 또는 비밀번호를 확인해 주세요.')
                if user['suspended']:
                    raise InvalidCredentials('이용이 제한된 계정이에요. 문의는 개인정보 처리방침의 연락처로 보내 주세요.')
                uid = user['id']
                profile = guest['profile'] if json.loads(guest['profile']) else user['profile']
            owner = f'user:{uid}'
            for row in db.execute('SELECT * FROM explorations WHERE owner=?', (self._owner(guest),)).fetchall():
                previous = db.execute('SELECT * FROM explorations WHERE owner=? AND lab_id=?', (owner, row['lab_id'])).fetchone()
                history = json.loads(row['previous_versions'])
                if previous:
                    history.append(self._decode(previous))
                    db.execute('DELETE FROM explorations WHERE owner=? AND lab_id=?', (owner, row['lab_id']))
                db.execute('UPDATE explorations SET owner=?,previous_versions=? WHERE owner=? AND lab_id=?', (owner, json.dumps(history, ensure_ascii=False), self._owner(guest), row['lab_id']))
            db.execute('UPDATE users SET profile=? WHERE id=?', (profile, uid))
            new = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions(token,user_id,first_lab_id,profile,expires) VALUES (?,?,?,?,?)', (token_hash(new), uid, guest['first_lab_id'], profile, time.time() + 30*86400))
            db.execute('DELETE FROM sessions WHERE token=?', (guest['token'],))
        return new

    def logout(self, token):
        with self.db() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (token_hash(token),))
        return self.session(None)
