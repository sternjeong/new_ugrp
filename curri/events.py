"""Pseudonymous usage events, per-session random experiment arms, funnel metrics and reports (moderation).

Events carry a keyed hash of the session token, never the token, email or name. Zero-result search text is kept
separately for 90 days so search gaps can be fixed; everything else is purged after a year.
"""
import hashlib
import json
from pathlib import Path
import time

from .accounts import session_hash

EVENTS = {'search', 'zero_results', 'result_open', 'explore', 'guide_request', 'guide_ready', 'guide_failed',
          'guide_feedback', 'save', 'contact', 'coffeechat', 'meeting_request', 'meeting_confirm', 'qna_ask',
          'qna_answer', 'watch', 'summary_view', 'register', 'graduate_apply'}
CLIENT_EVENTS = {'result_open', 'summary_view'}
FUNNEL = ['search', 'result_open', 'explore', 'guide_request', 'guide_ready', 'save', 'contact']
DEFAULT_EXPERIMENTS = {'guide': {'R': 1.0, 'A': 0.0}}
REPORT_KINDS = {'review', 'message', 'question', 'answer', 'user'}
YEAR = 365 * 86400


class Events:
    def __init__(self, store, secret, experiments_path=None):
        self.store, self.secret = store, secret
        self.experiments_path = Path(experiments_path) if experiments_path else None
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, ts REAL NOT NULL, session TEXT NOT NULL, member INTEGER NOT NULL,
                name TEXT NOT NULL, props TEXT NOT NULL DEFAULT '{}');
            CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
            CREATE TABLE IF NOT EXISTS zero_queries (id INTEGER PRIMARY KEY, ts REAL NOT NULL, text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY, reporter_id INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
                ref_id INTEGER NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                resolution TEXT, created REAL NOT NULL, resolved REAL);
            ''')
            db.execute('DELETE FROM events WHERE ts<?', (time.time() - YEAR,))
            db.execute('DELETE FROM zero_queries WHERE ts<?', (time.time() - 90 * 86400,))

    # ---- experiments ----
    def experiments(self):
        if self.experiments_path and self.experiments_path.is_file():
            try:
                return {**DEFAULT_EXPERIMENTS, **json.loads(self.experiments_path.read_text())}
            except ValueError:
                pass
        return DEFAULT_EXPERIMENTS

    def set_experiments(self, value):
        if not isinstance(value, dict) or any(not isinstance(arms, dict) or not arms or
                                              any(not isinstance(w, (int, float)) or w < 0 for w in arms.values())
                                              for arms in value.values()):
            raise ValueError('실험 설정 형식을 확인해 주세요.')
        if self.experiments_path:
            self.experiments_path.write_text(json.dumps(value))
        return self.experiments()

    def arm(self, token, name):
        """Stable random arm for this session: hash of (session, experiment) mapped onto the weights."""
        arms = self.experiments().get(name) or {}
        total = sum(arms.values())
        if not total:
            return next(iter(arms), None)
        point = int(hashlib.sha256(f'{session_hash(token, self.secret)}:{name}'.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF * total
        for arm, weight in arms.items():
            point -= weight
            if point <= 0 and weight > 0:
                return arm
        return max(arms, key=arms.get)

    # ---- events ----
    def record(self, token, name, props=None, member=False):
        if name not in EVENTS:
            raise ValueError('알 수 없는 이벤트입니다.')
        props = {k: v for k, v in (props or {}).items() if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 80}
        with self.store.db() as db:
            db.execute('INSERT INTO events(ts,session,member,name,props) VALUES (?,?,?,?,?)',
                       (time.time(), session_hash(token, self.secret), int(member), name, json.dumps(props, ensure_ascii=False)))

    def zero_query(self, text):
        with self.store.db() as db:
            db.execute('INSERT INTO zero_queries(ts,text) VALUES (?,?)', (time.time(), text[:200]))

    def metrics(self, days=14):
        since = time.time() - days * 86400
        with self.store.db() as db:
            rows = db.execute('SELECT ts, session, name, props FROM events WHERE ts>=?', (since,)).fetchall()
            zero = db.execute('SELECT text, COUNT(*) n FROM zero_queries WHERE ts>=? GROUP BY text ORDER BY n DESC LIMIT 30', (since,)).fetchall()
        by_day, sessions, arms, feedback = {}, {}, {}, {'up': 0, 'down': 0}
        for r in rows:
            day = time.strftime('%Y-%m-%d', time.localtime(r['ts']))
            by_day.setdefault(day, {}).setdefault(r['name'], 0)
            by_day[day][r['name']] += 1
            sessions.setdefault(r['name'], set()).add(r['session'])
            props = json.loads(r['props'])
            if 'arm' in props:
                arms.setdefault(props['arm'], {}).setdefault(r['name'], set()).add(r['session'])
            if r['name'] == 'guide_feedback':
                feedback['up' if props.get('helpful') else 'down'] += 1
        funnel = [{'step': s, 'sessions': len(sessions.get(s, ()))} for s in FUNNEL]
        searches = len(sessions.get('search', ()))
        return {'days': days, 'funnel': funnel, 'by_day': by_day, 'guide_feedback': feedback,
                'zero_result_rate': round(sum(d.get('zero_results', 0) for d in by_day.values()) /
                                          max(1, sum(d.get('search', 0) for d in by_day.values())), 3),
                'search_sessions': searches,
                'arms': {arm: {name: len(s) for name, s in names.items()} for arm, names in arms.items()},
                'zero_queries': [dict(z) for z in zero]}

    # ---- reports ----
    def report(self, user_id, body):
        kind, ref = body.get('kind'), body.get('ref_id')
        reason = body.get('reason', '')
        if kind not in REPORT_KINDS or type(ref) is not int or not isinstance(reason, str) or not 2 <= len(reason.strip()) <= 500:
            raise ValueError('신고 대상과 사유(2~500자)를 확인해 주세요.')
        with self.store.db() as db:
            if db.execute("SELECT 1 FROM reports WHERE reporter_id=? AND kind=? AND ref_id=? AND status='open'", (user_id, kind, ref)).fetchone():
                return {'reported': True}
            db.execute('INSERT INTO reports(reporter_id,kind,ref_id,reason,created) VALUES (?,?,?,?,?)',
                       (user_id, kind, ref, reason.strip(), time.time()))
        return {'reported': True}
