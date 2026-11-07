"""Outgoing mail through an outbox table and one sender thread.

With `.local/mail.json` ({"host", "port", "username", "password", "from", "security": "ssl"|"starttls"}) mail is sent by
SMTP. Without it every message stays in the outbox as 'held' so the admin console can show what would have gone out.
Message bodies are plain text and never include passwords or session tokens.
"""
from email.message import EmailMessage
from email.utils import formataddr
import json
from pathlib import Path
import smtplib
import ssl
import threading

from . import errors
import time

MAX_ATTEMPTS = 5


class Mailer:
    def __init__(self, store, config_path=None, base_url='https://3mincurri.duckdns.org'):
        self.store = store
        self.base_url = base_url.rstrip('/')
        self.config = None
        if config_path and Path(config_path).is_file():
            self.config = json.loads(Path(config_path).read_text(encoding='utf-8'))
            missing = [k for k in ('host', 'port', 'from') if not self.config.get(k)]
            if missing:
                raise ValueError(f'메일 설정에 {", ".join(missing)} 값이 없습니다.')
        self.wake = threading.Event()
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY, to_addr TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
                kind TEXT NOT NULL, user_id INTEGER, status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0, error TEXT, created REAL NOT NULL, sent REAL);
            CREATE INDEX IF NOT EXISTS outbox_status ON outbox(status);
            ''')

    @property
    def enabled(self):
        return self.config is not None

    def link(self, path):
        return self.base_url + path

    def send(self, to_addr, subject, body, kind, user_id=None):
        footer = (f'\n\n—\n3분커리 · {self.base_url}\n알림 설정: {self.link("/profile")}\n'
                  '이 메일은 발신 전용입니다.')
        with self.store.db() as db:
            db.execute('INSERT INTO outbox(to_addr,subject,body,kind,user_id,status,created) VALUES (?,?,?,?,?,?,?)',
                       (to_addr, subject[:200], body + footer, kind, user_id, 'queued' if self.enabled else 'held', time.time()))
        self.wake.set()

    def _deliver(self, row):
        cfg = self.config
        msg = EmailMessage()
        msg['From'] = formataddr((cfg.get('from_name', '3분커리'), cfg['from']))
        msg['To'] = row['to_addr']
        msg['Subject'] = row['subject']
        msg.set_content(row['body'])
        context = ssl.create_default_context()
        if cfg.get('security', 'ssl') == 'ssl':
            server = smtplib.SMTP_SSL(cfg['host'], int(cfg['port']), context=context, timeout=20)
        else:
            server = smtplib.SMTP(cfg['host'], int(cfg['port']), timeout=20)
            server.starttls(context=context)
        with server:
            if cfg.get('username'):
                server.login(cfg['username'], cfg['password'])
            server.send_message(msg)

    def flush(self):
        """Send queued mail once. Returns the number sent."""
        if not self.enabled:
            return 0
        with self.store.db() as db:
            rows = db.execute("SELECT * FROM outbox WHERE status='queued' AND attempts<? ORDER BY id LIMIT 20", (MAX_ATTEMPTS,)).fetchall()
        sent = 0
        for row in rows:
            try:
                self._deliver(row)
                status, error = 'sent', None
                sent += 1
            except Exception as exc:
                status, error = ('queued' if row['attempts'] + 1 < MAX_ATTEMPTS else 'failed'), type(exc).__name__
                print(f'mail send failed: {error}', flush=True)
                errors.record('mail send', exc)
            with self.store.db() as db:
                db.execute('UPDATE outbox SET status=?, attempts=attempts+1, error=?, sent=? WHERE id=?',
                           (status, error, time.time() if status == 'sent' else None, row['id']))
        return sent

    def start(self):
        def loop():
            while True:
                self.wake.wait(30)
                self.wake.clear()
                try:
                    self.flush()
                except Exception as exc:
                    print(f'mail loop error: {type(exc).__name__}', flush=True)
                    errors.record('mailer', exc)
        threading.Thread(target=loop, daemon=True, name='mailer').start()
