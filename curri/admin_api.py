"""Admin operations for the separate admin VM. Reached only through an SSH tunnel (loopback, no proxy header) with a
bearer token; every call is written to `admin_audit` (안전성 확보조치 기준 제8조: 접속기록 보관)."""
import hmac
import json
import threading
import time
from .llm_jobs import QuotaExceeded
from pathlib import Path

AUDIT_RETENTION = 2 * 365 * 86400


def mask(email):
    name, _, domain = (email or '').partition('@')
    return (name[:2] + '***@' + domain) if domain else '***'


class AdminAPI:
    def __init__(self, store, catalog, accounts, events, mailer, llm, guide, watch, broker=None, token=None, backup_dir=None):
        self.store, self.catalog, self.accounts, self.events = store, catalog, accounts, events
        self.mailer, self.llm, self.guide, self.watch, self.broker = mailer, llm, guide, watch, broker
        self.token = token
        self.backup_dir = Path(backup_dir) if backup_dir else None
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS admin_audit (
                id INTEGER PRIMARY KEY, ts REAL NOT NULL, admin TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
            ''')
            db.execute('DELETE FROM admin_audit WHERE ts<?', (time.time() - AUDIT_RETENTION,))

    def enabled(self):
        return bool(self.token)

    def authorized(self, header):
        return self.enabled() and isinstance(header, str) and hmac.compare_digest(header, f'Bearer {self.token}')

    def audit(self, admin, action, detail):
        with self.store.db() as db:
            db.execute('INSERT INTO admin_audit(ts,admin,action,detail) VALUES (?,?,?,?)',
                       (time.time(), (admin or 'unknown')[:40], action, json.dumps(detail, ensure_ascii=False)[:1000]))

    def _lab(self, lab_id):
        try:
            card = self.catalog.card(lab_id)
            return f"{', '.join(card['professors'])} · {card['department']}"
        except KeyError:
            return lab_id

    # ---- reads ----
    def overview(self, query):
        with self.store.db() as db:
            roles = {r['role']: r['n'] for r in db.execute('SELECT role, COUNT(*) n FROM users WHERE dummy=0 AND deleted=0 GROUP BY role')}
            out = {'users': roles, 'dummies': db.execute('SELECT COUNT(*) FROM users WHERE dummy=1').fetchone()[0],
                   'verified': db.execute('SELECT COUNT(*) FROM users WHERE email_verified=1 AND deleted=0').fetchone()[0],
                   'pending_graduates': db.execute("SELECT COUNT(*) FROM users WHERE grad_status='pending'").fetchone()[0],
                   'open_reports': db.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0],
                   'outbox': {r['status']: r['n'] for r in db.execute('SELECT status, COUNT(*) n FROM outbox GROUP BY status')},
                   'threads': db.execute('SELECT COUNT(*) FROM threads WHERE dummy=0').fetchone()[0],
                   'meetings': db.execute("SELECT COUNT(*) FROM meetings WHERE status='confirmed'").fetchone()[0],
                   'questions': db.execute('SELECT COUNT(*) FROM qna_questions').fetchone()[0],
                   'watches': db.execute('SELECT COUNT(*) FROM watches').fetchone()[0],
                   'feedback_new': db.execute("SELECT COUNT(*) FROM feedback WHERE status='new' AND comment!=''").fetchone()[0]}
            last = db.execute("SELECT value FROM meta WHERE key='watch_last_run'").fetchone()
        backups = sorted(self.backup_dir.glob('curri-*.sqlite')) if self.backup_dir and self.backup_dir.is_dir() else []
        out.update({'mail_enabled': self.mailer.enabled, 'llm': self.llm.stats(), 'embedding_online': bool(self.broker and self.broker.available()),
                    'watch_last_run': float(last['value']) if last else None,
                    'last_backup': {'name': backups[-1].name, 'time': backups[-1].stat().st_mtime} if backups else None,
                    'experiments': self.events.experiments(), 'metrics': self.events.metrics(int(query.get('days', 14)))})
        return out

    def users(self, query):
        q = (query.get('q') or '').strip().lower()
        with self.store.db() as db:
            rows = db.execute('''SELECT id,email,nickname,role,lab_id,email_verified,suspended,deleted,dummy,grad_status,created FROM users
                                 WHERE (?='' OR lower(email) LIKE ? OR lower(nickname) LIKE ?) ORDER BY id DESC LIMIT 100''',
                              (q, f'%{q}%', f'%{q}%')).fetchall()
        return {'users': [{**dict(r), 'email': mask(r['email']), 'lab': self._lab(r['lab_id']) if r['lab_id'] else ''} for r in rows]}

    def graduates(self, query):
        with self.store.db() as db:
            rows = db.execute("SELECT id,email,nickname,account FROM users WHERE grad_status='pending' ORDER BY id").fetchall()
        out = []
        for r in rows:
            app = json.loads(r['account']).get('grad_application', {})
            out.append({'id': r['id'], 'email': r['email'], 'nickname': r['nickname'], 'lab': self._lab(app.get('lab_id')), **app})
        return {'pending': out}

    def _content(self, db, kind, ref):
        if kind == 'review':
            row = db.execute('SELECT user_id, good, improve FROM reviews WHERE id=?', (ref,)).fetchone()
            return (row['user_id'], f"{row['good']} / {row['improve']}") if row else (None, '(삭제됨)')
        if kind == 'message':
            row = db.execute('SELECT sender_id, body FROM messages WHERE id=?', (ref,)).fetchone()
            return (row['sender_id'], row['body']) if row else (None, '(삭제됨)')
        if kind in ('question', 'answer'):
            row = db.execute(f"SELECT user_id, body FROM qna_{kind}s WHERE id=?", (ref,)).fetchone()
            return (row['user_id'], row['body']) if row else (None, '(삭제됨)')
        return (ref, '(사용자 신고)')

    def reports(self, query):
        status = query.get('status', 'open')
        with self.store.db() as db:
            rows = db.execute('SELECT * FROM reports WHERE status=? ORDER BY id DESC LIMIT 100', (status,)).fetchall()
            out = []
            for r in rows:
                author, content = self._content(db, r['kind'], r['ref_id'])
                out.append({**dict(r), 'author_id': author, 'content': (content or '')[:500]})
        return {'reports': out}

    def outbox(self, query):
        with self.store.db() as db:
            rows = db.execute('SELECT id,to_addr,subject,kind,status,attempts,error,created,sent FROM outbox ORDER BY id DESC LIMIT 100').fetchall()
        return {'mail_enabled': self.mailer.enabled, 'outbox': [{**dict(r), 'to_addr': mask(r['to_addr'])} for r in rows]}

    def audit_log(self, query):
        with self.store.db() as db:
            rows = db.execute('SELECT * FROM admin_audit ORDER BY id DESC LIMIT 200').fetchall()
        return {'audit': [dict(r) for r in rows]}

    # ---- writes ----
    def decide_graduate(self, body):
        if type(body.get('user_id')) is not int or not isinstance(body.get('approve'), bool):
            raise ValueError('user_id와 approve가 필요합니다.')
        return self.accounts.decide_graduate(body['user_id'], body['approve'], str(body.get('note', ''))[:300])

    def resolve_report(self, body):
        rid, action = body.get('id'), body.get('action')
        if type(rid) is not int or action not in ('hide', 'dismiss', 'suspend'):
            raise ValueError('id와 action(hide·dismiss·suspend)이 필요합니다.')
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r = db.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
            if r is None:
                raise ValueError('신고를 찾지 못했습니다.')
            author, _ = self._content(db, r['kind'], r['ref_id'])
            if action in ('hide', 'suspend'):
                if r['kind'] == 'review':
                    db.execute('DELETE FROM reviews WHERE id=?', (r['ref_id'],))
                elif r['kind'] == 'message':
                    db.execute("UPDATE messages SET body='(운영자가 숨긴 메시지입니다)' WHERE id=?", (r['ref_id'],))
                elif r['kind'] in ('question', 'answer'):
                    db.execute(f'UPDATE qna_{r["kind"]}s SET hidden=1 WHERE id=?', (r['ref_id'],))
            if action == 'suspend' and author:
                db.execute('UPDATE users SET suspended=1 WHERE id=?', (author,))
                db.execute('DELETE FROM sessions WHERE user_id=?', (author,))
            db.execute("UPDATE reports SET status='resolved', resolution=?, resolved=? WHERE kind=? AND ref_id=? AND status='open'",
                       (action, time.time(), r['kind'], r['ref_id']))
        return {'ok': True}

    def suspend_user(self, body):
        uid, on = body.get('user_id'), body.get('suspended')
        if type(uid) is not int or not isinstance(on, bool):
            raise ValueError('user_id와 suspended가 필요합니다.')
        with self.store.db() as db:
            db.execute('UPDATE users SET suspended=? WHERE id=?', (int(on), uid))
            if on:
                db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        return {'ok': True}

    def retry_mail(self, body):
        with self.store.db() as db:
            n = db.execute("UPDATE outbox SET status='queued', attempts=0 WHERE status IN ('failed','held')").rowcount if self.mailer.enabled else 0
        self.mailer.wake.set()
        return {'requeued': n}

    def set_experiments(self, body):
        return {'experiments': self.events.set_experiments(body.get('experiments'))}

    def prefill_summaries(self, body):
        queued = 0
        for lab_id in self.catalog.profiles:
            payload = self.guide.summary_payload(lab_id)
            if payload:
                try:
                    job = self.llm.submit('summary', self.guide.summary_key(lab_id), payload)
                except QuotaExceeded:
                    break
                queued += job['status'] == 'queued'
        return {'queued': queued}

    def run_watch(self, body):
        threading.Thread(target=self.watch.run, daemon=True).start()
        return {'started': True}

    def warm_phrases(self, body):
        """Ask the embedding worker for common phrases so their similarities are cached for cold starts."""
        phrases = body.get('phrases')
        if not isinstance(phrases, list) or not phrases or len(phrases) > 2000 or any(not isinstance(p, str) or not 1 <= len(p) <= 60 for p in phrases):
            raise ValueError('phrases는 1~2000개의 짧은 문자열 목록이어야 합니다.')
        if not self.broker or not self.broker.available():
            raise ValueError('임베딩 워커가 연결돼 있지 않습니다.')

        def work():
            for i in range(0, len(phrases), 20):
                self.broker.request(phrases[i:i + 20], 60)
        threading.Thread(target=work, daemon=True).start()
        return {'started': len(phrases)}

    def backup_bytes(self):
        """A consistent copy of the live database for the admin VM's off-site backup."""
        import sqlite3
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.sqlite') as tmp:
            source, dest = sqlite3.connect(self.store.path), sqlite3.connect(tmp.name)
            with dest:
                source.backup(dest)
            source.close()
            dest.close()
            return Path(tmp.name).read_bytes()

    def errors_view(self, query):
        from . import errors
        with self.store.db() as db:
            failed_mail = [dict(r) for r in db.execute("SELECT id,kind,error,attempts,created FROM outbox WHERE status='failed' ORDER BY id DESC LIMIT 30")]
            failed_jobs = [dict(r) for r in db.execute("SELECT id,kind,error,attempts,created FROM llm_jobs WHERE status='failed' ORDER BY id DESC LIMIT 30")]
        return {'errors': errors.recent(), 'failed_mail': failed_mail, 'failed_jobs': failed_jobs,
                'system': errors.system(self.store.path), 'llm_online': self.llm.online(),
                'embedding_online': bool(self.broker and self.broker.available()), 'mail_enabled': self.mailer.enabled}

    def feedback_view(self, query):
        fb = self.feedback
        zero = self.events.metrics(int(query.get('days', 30)))['zero_queries']
        return {**fb.summary(int(query.get('days', 30))), 'candidates': fb.expansion_candidates(zero),
                'expansions': fb.saved_expansions(), 'evaluation_size': len(fb.judgments())}

    def feedback_eval(self, query):
        engine = getattr(self, 'engine', None)
        if engine is None:
            raise ValueError('검색 엔진이 꺼져 있어 평가할 수 없어요.')
        def search(text):
            found = engine.search(text, allow_remote=False) if 'allow_remote' in engine.search.__code__.co_varnames else engine.search(text)
            return [c['id'] for c in found.get('labs', [])]
        return self.feedback.evaluate(search)

    def feedback_export(self, query):
        return {'judgments': self.feedback.judgments(), 'exported': time.time()}

    def feedback_status(self, body):
        if type(body.get('id')) is not int:
            raise ValueError('id가 필요합니다.')
        return self.feedback.set_status(body['id'], body.get('status'))

    def add_expansion(self, body):
        variants = body.get('variants')
        if isinstance(variants, str):
            variants = [v for v in variants.split(',')]
        return self.feedback.add_expansion(body.get('term'), variants or [])

    READS = {'errors': errors_view, 'feedback': feedback_view, 'feedback/eval': feedback_eval, 'feedback/export': feedback_export, 'overview': overview, 'users': users, 'graduates': graduates, 'reports': reports, 'outbox': outbox, 'audit': audit_log}
    WRITES = {'graduates/decide': decide_graduate, 'reports/resolve': resolve_report, 'users/suspend': suspend_user,
              'mail/retry': retry_mail, 'experiments': set_experiments, 'summaries/prefill': prefill_summaries,
              'watch/run': run_watch, 'phrases/warm': warm_phrases, 'feedback/status': feedback_status,
              'expansions/add': add_expansion}

    def handle(self, method, name, data, admin):
        table = self.READS if method == 'GET' else self.WRITES
        if name not in table:
            raise KeyError(name)
        result = table[name](self, data)
        if method != 'GET' or name in ('users', 'graduates', 'reports', 'outbox'):
            self.audit(admin, f'{method} {name}', {k: v for k, v in data.items() if k not in ('phrases',)})
        return result
