"""Consent records, email verification, password reset, account deletion, notification settings,
graduate applications and user blocks."""
import hashlib
import hmac
import json
import re
import secrets
import time

from .privacy import CONSENTS, POLICY_VERSION, REQUIRED_CONSENTS
from .store import NOTIFY_DEFAULTS, password_digest, token_hash

CODE_TTL = 15 * 60
RESET_TTL = 60 * 60
CODES_PER_HOUR = 5
GRAD_DOMAINS = ('postech.ac.kr',)
PROGRAMS = ('석사과정', '박사과정', '석박통합과정', '박사후연구원')


def _text(body, key, label, limit, minimum=0):
    value = body.get(key, '')
    if not isinstance(value, str):
        raise ValueError(f'{label}을(를) 확인해 주세요.')
    value = value.strip()
    if not minimum <= len(value) <= limit:
        raise ValueError(f'{label}은(는) {minimum}~{limit}자로 입력해 주세요.' if minimum else f'{label}은(는) {limit}자 이내로 입력해 주세요.')
    return value


class Accounts:
    def __init__(self, store, mailer, catalog, grad_domains=GRAD_DOMAINS):
        self.store, self.mailer, self.catalog = store, mailer, catalog
        self.grad_domains = tuple(grad_domains)
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS consents (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), version TEXT NOT NULL,
                items TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS email_tokens (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), purpose TEXT NOT NULL,
                email TEXT NOT NULL, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS blocks (
                user_id INTEGER NOT NULL REFERENCES users(id), blocked_id INTEGER NOT NULL REFERENCES users(id),
                created REAL NOT NULL, PRIMARY KEY(user_id, blocked_id));
            ''')

    # ---- consent ----
    @staticmethod
    def clean_consents(body):
        consents = body.get('consents') if isinstance(body, dict) else None
        if not isinstance(consents, dict) or any(k not in CONSENTS or not isinstance(v, bool) for k, v in consents.items()):
            raise ValueError('동의 항목을 확인해 주세요.')
        missing = [CONSENTS[k]['label'] for k in REQUIRED_CONSENTS if not consents.get(k)]
        if missing:
            raise ValueError('필수 항목에 동의해 주세요: ' + ', '.join(missing))
        return {k: bool(consents.get(k)) for k in CONSENTS}

    def record_consent(self, user_id, items):
        with self.store.db() as db:
            db.execute('INSERT INTO consents(user_id,version,items,created) VALUES (?,?,?,?)',
                       (user_id, POLICY_VERSION, json.dumps(items), time.time()))

    def consent_state(self, user_id):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM consents WHERE user_id=? ORDER BY id DESC LIMIT 1', (user_id,)).fetchone()
        return {'version': row['version'], **json.loads(row['items'])} if row else None

    def overseas_allowed(self, token):
        """Members follow their own consent; guests follow the choice stored in the session (default allowed with notice)."""
        session = self.store.get_session(token)
        if not session:
            return False
        if session['user_id']:
            state = self.consent_state(session['user_id'])
            return bool(state and state.get('overseas'))
        return not json.loads(session['profile'] or '{}').get('no_overseas')

    def set_overseas(self, token, allowed):
        if not isinstance(allowed, bool):
            raise ValueError('선택을 확인해 주세요.')
        session = self.store.get_session(token)
        if session and session['user_id']:
            state = self.consent_state(session['user_id']) or {k: k in REQUIRED_CONSENTS for k in CONSENTS}
            state.pop('version', None)
            self.record_consent(session['user_id'], {**state, 'overseas': allowed})
        else:
            profile = json.loads(session['profile'] or '{}') if session else {}
            self.store.set_profile(token, {**profile, 'no_overseas': not allowed})

    # ---- email codes ----
    def _rate(self, db, user_id, purpose):
        count = db.execute('SELECT COUNT(*) FROM email_tokens WHERE user_id=? AND purpose=? AND created>?',
                           (user_id, purpose, time.time() - 3600)).fetchone()[0]
        if count >= CODES_PER_HOUR:
            raise ValueError('요청이 많아요. 한 시간 뒤에 다시 시도해 주세요.')

    def send_verification(self, token, body=None):
        user = self.store.current_user(token)
        if user['email_verified']:
            return {'sent': False, 'verified': True}
        code = f'{secrets.randbelow(10 ** 6):06d}'
        with self.store.db() as db:
            self._rate(db, user['id'], 'verify')
            db.execute('INSERT INTO email_tokens(token,user_id,purpose,email,expires,created) VALUES (?,?,?,?,?,?)',
                       (token_hash(f'{user["id"]}:{code}'), user['id'], 'verify', user['email'], time.time() + CODE_TTL, time.time()))
        self.mailer.send(user['email'], '[3분커리] 이메일 인증 코드',
                         f'인증 코드: {code}\n\n15분 안에 입력해 주세요. 요청하지 않았다면 이 메일을 무시하세요.', 'verify', user['id'])
        return {'sent': True, 'mail_enabled': self.mailer.enabled}

    def verify_email(self, token, body):
        user = self.store.current_user(token)
        code = body.get('code')
        if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code.strip()):
            raise ValueError('6자리 인증 코드를 입력해 주세요.')
        with self.store.db() as db:
            row = db.execute("SELECT * FROM email_tokens WHERE token=? AND purpose='verify' AND used=0 AND expires>?",
                             (token_hash(f'{user["id"]}:{code.strip()}'), time.time())).fetchone()
            if row is None or row['email'] != user['email']:
                raise ValueError('인증 코드가 맞지 않거나 만료됐어요.')
            db.execute('UPDATE email_tokens SET used=1 WHERE token=?', (row['token'],))
            db.execute('UPDATE users SET email_verified=1 WHERE id=?', (user['id'],))
        return {'verified': True}

    def forgot_password(self, body):
        """Always answers the same way so the response does not reveal whether an email is registered."""
        email = body.get('email')
        if not isinstance(email, str) or len(email) > 254:
            raise ValueError('이메일을 입력해 주세요.')
        with self.store.db() as db:
            user = db.execute('SELECT * FROM users WHERE email=? AND deleted=0 AND dummy=0', (email.strip().lower(),)).fetchone()
            if user:
                try:
                    self._rate(db, user['id'], 'reset')
                except ValueError:
                    user = None
            if user:
                raw = secrets.token_urlsafe(32)
                db.execute('INSERT INTO email_tokens(token,user_id,purpose,email,expires,created) VALUES (?,?,?,?,?,?)',
                           (token_hash(raw), user['id'], 'reset', user['email'], time.time() + RESET_TTL, time.time()))
        if user:
            self.mailer.send(user['email'], '[3분커리] 비밀번호 재설정',
                             f'아래 링크에서 1시간 안에 새 비밀번호를 정해 주세요.\n{self.mailer.link("/reset?token=" + raw)}\n\n'
                             '요청하지 않았다면 이 메일을 무시하세요. 비밀번호는 바뀌지 않습니다.', 'reset', user['id'])
        return {'ok': True}

    def reset_password(self, body):
        raw, password = body.get('token'), body.get('password')
        if not isinstance(raw, str) or not isinstance(password, str) or not 10 <= len(password) <= 128:
            raise ValueError('비밀번호는 10~128자로 입력해 주세요.')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM email_tokens WHERE token=? AND purpose='reset' AND used=0 AND expires>?",
                             (token_hash(raw), time.time())).fetchone()
            if row is None:
                raise ValueError('재설정 링크가 만료됐어요. 다시 요청해 주세요.')
            salt = secrets.token_hex(16)
            db.execute('UPDATE users SET salt=?, password_hash=?, email_verified=1 WHERE id=?', (salt, password_digest(password, salt), row['user_id']))
            db.execute('UPDATE email_tokens SET used=1 WHERE token=?', (row['token'],))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))  # sign out everywhere
        return {'ok': True}

    # ---- notification settings ----
    def set_notify(self, token, body):
        user = self.store.current_user(token)
        prefs = body.get('notify')
        if not isinstance(prefs, dict) or any(k not in NOTIFY_DEFAULTS or not isinstance(v, bool) for k, v in prefs.items()):
            raise ValueError('알림 설정을 확인해 주세요.')
        merged = {**NOTIFY_DEFAULTS, **json.loads(user['notify'] or '{}'), **prefs}
        with self.store.db() as db:
            db.execute('UPDATE users SET notify=? WHERE id=?', (json.dumps(merged), user['id']))
        return {'notify': merged}

    # ---- deletion ----
    def delete_account(self, token, body):
        """Deletes the account. Messages a counterpart already received stay, shown as from '탈퇴한 사용자'."""
        user = self.store.current_user(token)
        password = body.get('password')
        if not isinstance(password, str) or not hmac.compare_digest(password_digest(password, user['salt']), user['password_hash']):
            raise ValueError('비밀번호가 맞지 않아요.')
        uid = user['id']
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM explorations WHERE owner=?', (f'user:{uid}',))
            db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
            db.execute('DELETE FROM email_tokens WHERE user_id=?', (uid,))
            db.execute('DELETE FROM consents WHERE user_id=?', (uid,))
            db.execute('DELETE FROM blocks WHERE user_id=? OR blocked_id=?', (uid, uid))
            for table in ('reviews', 'watches', 'qna_questions'):
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                    if table == 'qna_questions':
                        db.execute('DELETE FROM qna_answers WHERE question_id IN (SELECT id FROM qna_questions WHERE user_id=?)', (uid,))
                    db.execute(f'DELETE FROM {table} WHERE user_id=?', (uid,))
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='qna_answers'").fetchone():
                db.execute("UPDATE qna_answers SET body='(탈퇴한 선배의 답변이 삭제되었습니다)', hidden=1 WHERE user_id=?", (uid,))
            db.execute('''UPDATE users SET email=?, salt=?, password_hash='', nickname=NULL, account='{}', profile='{}',
                          notify='{}', lab_id=NULL, deleted=1, email_verified=0, grad_status=NULL WHERE id=?''',
                       (f'deleted-{uid}-{secrets.token_hex(4)}@invalid', secrets.token_hex(16), uid))
        return {'deleted': True}

    # ---- graduates ----
    def apply_graduate(self, token, body):
        user = self.store.current_user(token, complete=True)
        if user['role'] == 'graduate':
            raise ValueError('이미 선배 계정이에요.')
        if not user['email'].endswith(tuple('@' + d for d in self.grad_domains)):
            raise ValueError(f'대학원생 인증은 학교 메일({", ".join(self.grad_domains)})로 가입한 계정에서만 할 수 있어요.')
        if not user['email_verified']:
            raise ValueError('먼저 이메일 인증을 완료해 주세요.')
        lab_id = body.get('lab_id')
        if not isinstance(lab_id, str):
            raise ValueError('소속 연구실을 골라 주세요.')
        lab_id = self.catalog.resolve(lab_id)
        program = body.get('program')
        if program not in PROGRAMS:
            raise ValueError('과정을 골라 주세요.')
        limit = body.get('monthly_limit', 4)
        if type(limit) is not int or not 0 <= limit <= 30:
            raise ValueError('월 문의 상한은 0~30 사이로 정해 주세요.')
        application = {'lab_id': lab_id, 'program': program, 'research': _text(body, 'research', '연구 분야', 120, 2),
                       'availability': _text(body, 'availability', '가능 시간', 120),
                       'contact_consent': bool(body.get('contact_consent')), 'monthly_limit': limit,
                       'note': _text(body, 'note', '확인 메모', 300), 'applied': time.time()}
        account = json.loads(user['account'])
        account['grad_application'] = application
        with self.store.db() as db:
            db.execute("UPDATE users SET account=?, grad_status='pending' WHERE id=?", (json.dumps(account, ensure_ascii=False), user['id']))
        return {'grad_status': 'pending'}

    def decide_graduate(self, user_id, approve, note=''):
        """Admin decision. Approval turns the account into a graduate of the applied lab."""
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            user = db.execute("SELECT * FROM users WHERE id=? AND grad_status='pending'", (user_id,)).fetchone()
            if user is None:
                raise ValueError('대기 중인 신청이 아니에요.')
            account = json.loads(user['account'])
            app = account.get('grad_application') or {}
            if approve:
                account.update({'program': app['program'], 'research': app['research'], 'contact_consent': app['contact_consent'],
                                'monthly_limit': app['monthly_limit'], 'availability': app.get('availability', '')})
                db.execute("UPDATE users SET role='graduate', lab_id=?, account=?, grad_status='approved' WHERE id=?",
                           (app['lab_id'], json.dumps(account, ensure_ascii=False), user_id))
            else:
                db.execute("UPDATE users SET grad_status='rejected' WHERE id=?", (user_id,))
        self.mailer.send(user['email'], '[3분커리] 선배 인증 결과',
                         ('선배 인증이 승인되었어요. 이제 연구실 상세 화면에 선배로 소개되고 쪽지와 질문에 답할 수 있어요.'
                          if approve else '선배 인증이 승인되지 않았어요.' + (f'\n사유: {note}' if note else '')),
                         'graduate', user_id)
        return {'approved': bool(approve)}

    def update_graduate(self, token, body):
        """A graduate changes contact settings: whether students may write, monthly cap and available times."""
        user = self.store.current_user(token)
        if user['role'] != 'graduate':
            raise ValueError('선배 계정에서만 바꿀 수 있어요.')
        limit = body.get('monthly_limit')
        if type(limit) is not int or not 0 <= limit <= 30:
            raise ValueError('월 문의 상한은 0~30 사이로 정해 주세요.')
        account = json.loads(user['account'])
        account.update({'contact_consent': bool(body.get('contact_consent')), 'monthly_limit': limit,
                        'show_email': bool(body.get('show_email')), 'availability': _text(body, 'availability', '가능 시간', 120)})
        with self.store.db() as db:
            db.execute('UPDATE users SET account=? WHERE id=?', (json.dumps(account, ensure_ascii=False), user['id']))
        return {'ok': True}

    # ---- blocks ----
    def block(self, token, body):
        user = self.store.current_user(token)
        other = body.get('user_id')
        if type(other) is not int or other == user['id']:
            raise ValueError('차단할 사용자를 확인해 주세요.')
        with self.store.db() as db:
            if body.get('unblock'):
                db.execute('DELETE FROM blocks WHERE user_id=? AND blocked_id=?', (user['id'], other))
            else:
                db.execute('INSERT OR IGNORE INTO blocks(user_id,blocked_id,created) VALUES (?,?,?)', (user['id'], other, time.time()))
        return {'blocked': not body.get('unblock')}

    def blocked_between(self, db, a, b):
        return db.execute('SELECT 1 FROM blocks WHERE (user_id=? AND blocked_id=?) OR (user_id=? AND blocked_id=?)', (a, b, b, a)).fetchone() is not None


def session_hash(token, secret):
    """Pseudonymous, stable id for a session (events, A/B assignment). Not reversible without the server secret."""
    return hmac.new(secret.encode(), (token or '').encode(), hashlib.sha256).hexdigest()[:16]
