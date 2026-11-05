"""Personal profiles, research-participation reviews, in-app contact and meetings with graduate students.

Authentication and session ownership stay in `store.Store`; this module only adds tables that
reference `users`. The acting user is always derived from the session token, never from the body.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
from .meeting_links import MeetingLinkError
from .store import ProfileRequired, profile_complete

DEPARTMENTS = ['수학과', '물리학과', '화학과', '생명과학과', '신소재공학과', '기계공학과', '산업경영공학과', '전자전기공학과', '컴퓨터공학과', '화학공학과', 'IT융합공학과', '반도체공학과', '기타']
GRADES = ['1학년', '2학년', '3학년', '4학년', '5학년 이상', '휴학·기타']
GOALS = {'explore': '아직 알아보는 중', 'research': '연구참여', 'graduate': '연구실 진학'}
RATINGS = {'mentoring': '지도·소통', 'learning': '배운 점', 'workload': '업무량 적절성', 'atmosphere': '분위기'}
GRADUATE_ONLY = ('program', 'research', 'contact_consent')
DAILY_MESSAGES = 30
KST = timezone(timedelta(hours=9))  # no daylight saving in Korea
WEEKDAYS = '월화수목금토일'
MEETING_MODES = {'online': '온라인', 'offline': '대면'}
MEETING_MINUTES = (20, 30)  # free Zoom accounts end meetings at 40 minutes
MEETING_SLOTS = 3
MEETING_HORIZON_DAYS = 60


class NotFound(Exception):
    pass


def _text(body, key, label, limit, minimum=0):
    value = body.get(key, '')
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ValueError(f'{label} 입력을 확인해 주세요.')
    value = value.strip()
    if minimum and len(value) < minimum:
        raise ValueError(f'{label}을(를) {minimum}자 이상 입력해 주세요.' if minimum > 1 else f'{label}을(를) 입력해 주세요.')
    if len(value) > limit:
        raise ValueError(f'{label}은(는) {limit}자 이내로 입력해 주세요.')
    return value


def _choice(body, key, label, allowed):
    value = body.get(key) or ''
    if value not in allowed and value != '':
        raise ValueError(f'{label} 선택을 확인해 주세요.')
    return value


def load_concepts(data_dir):
    path = Path(data_dir) / 'concepts.json' if data_dir else None
    if not path or not path.exists():
        return []
    return [{'id': c['id'], 'ko': c['ko'], 'kind': c['kind']} for c in json.loads(path.read_text())['concepts']]


class Community:
    def __init__(self, store, catalog, data_dir=None, seed=True, meeting_links=None):
        self.store, self.catalog = store, catalog
        self.meeting_links = meeting_links
        self.concepts = load_concepts(data_dir)
        self.concept_names = {c['id']: c['ko'] for c in self.concepts}
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), lab_id TEXT NOT NULL,
                term TEXT NOT NULL, duration TEXT NOT NULL, activity TEXT NOT NULL, ratings TEXT NOT NULL,
                good TEXT NOT NULL, improve TEXT NOT NULL, recommend_for TEXT NOT NULL,
                dummy INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
                UNIQUE(user_id, lab_id));
            CREATE TABLE IF NOT EXISTS threads (
                id INTEGER PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES users(id),
                graduate_id INTEGER NOT NULL REFERENCES users(id), lab_id TEXT, subject TEXT NOT NULL,
                dummy INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL, updated REAL NOT NULL,
                UNIQUE(student_id, graduate_id));
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES threads(id),
                sender_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL,
                created REAL NOT NULL, read INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id);
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES threads(id),
                proposer_id INTEGER NOT NULL REFERENCES users(id), mode TEXT NOT NULL, minutes INTEGER NOT NULL,
                slots TEXT NOT NULL, place TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL,
                start REAL, provider TEXT, join_url TEXT, external_id TEXT, closed_by INTEGER REFERENCES users(id),
                created REAL NOT NULL, updated REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS meetings_thread ON meetings(thread_id);
            ''')
        self.migrate_lab_ids()
        path = Path(data_dir) / 'community_seed.json' if data_dir else None
        if seed and path and path.exists():
            self.seed(json.loads(path.read_text()))

    # ---- profiles ----
    def clean_account(self, body):
        """Validate the personal profile; returns (nickname, account). Required: 이름·별명·학교·관심 분야."""
        if not isinstance(body, dict):
            raise ValueError('프로필 입력을 확인해 주세요.')
        nickname = _text(body, 'nickname', '별명', 20, 2)
        if re.search(r'[\s@<>]', nickname):
            raise ValueError('별명에는 공백, @, <, >를 쓸 수 없어요.')
        tags = body.get('interest_tags', [])
        if not isinstance(tags, list) or len(tags) > 8 or any(t not in self.concept_names for t in tags):
            raise ValueError('관심 분야 태그는 목록에서 8개까지 고를 수 있어요.')
        account = {
            'real_name': _text(body, 'real_name', '이름', 40, 2),
            'school': _text(body, 'school', '학교', 60, 2),
            'interest_tags': list(dict.fromkeys(tags)),
            'interest_text': _text(body, 'interest_text', '관심 분야 설명', 300),
            'department': _choice(body, 'department', '학과', DEPARTMENTS),
            'second_major': _choice(body, 'second_major', '복수전공', DEPARTMENTS),
            'grade': _choice(body, 'grade', '학년', GRADES),
            'goal': _choice(body, 'goal', '목표', GOALS),
            'timing': _text(body, 'timing', '희망 시기', 60),
            'headline': _text(body, 'headline', '한 줄 소개', 80),
            'intro': _text(body, 'intro', '자기소개', 1500),
        }
        if not account['interest_tags'] and len(account['interest_text']) < 2:
            raise ValueError('관심 분야를 태그로 하나 이상 고르거나 직접 적어 주세요.')
        return nickname, account

    def update_account(self, token, body):
        user = self.store.current_user(token)
        nickname, account = self.clean_account(body)
        previous = json.loads(user['account'])
        account.update({k: previous[k] for k in GRADUATE_ONLY if k in previous})
        self.store.update_account(token, nickname, account)

    def interests(self, account):
        return [self.concept_names.get(t, t) for t in account.get('interest_tags', [])]

    # ---- labs ----
    def _lab(self, lab_id):
        try:
            card = self.catalog.card(lab_id)
        except KeyError:
            return None
        return {'id': card['id'], 'professors': card['professors'], 'department': card['department']}

    def _resolve(self, lab_id):
        if not isinstance(lab_id, str):
            raise ValueError('연구실을 선택해 주세요.')
        try:
            return self.catalog.resolve(lab_id)
        except KeyError:
            raise NotFound('연구실을 찾지 못했습니다.') from None

    def _optional_user(self, token):
        try:
            return self.store.current_user(token)
        except Exception:
            return None

    # ---- reviews ----
    @staticmethod
    def _author(row):
        account = json.loads(row['account'])
        return {'nickname': row['nickname'] or '익명', 'department': account.get('department', ''), 'grade': account.get('grade', '')}

    def _review(self, row, me=None, lab=False):
        out = {'id': row['id'], 'lab_id': row['lab_id'], 'term': row['term'], 'duration': row['duration'], 'activity': row['activity'],
               'ratings': json.loads(row['ratings']), 'good': row['good'], 'improve': row['improve'], 'recommend_for': row['recommend_for'],
               'author': self._author(row), 'mine': bool(me and row['user_id'] == me['id']), 'created': row['created']}
        if lab:
            out['lab'] = self._lab(row['lab_id'])
        return out

    @staticmethod
    def summary(reviews):
        if not reviews:
            return {'count': 0, 'averages': {}, 'overall': None}
        averages = {k: round(sum(r['ratings'][k] for r in reviews) / len(reviews), 1) for k in RATINGS}
        return {'count': len(reviews), 'averages': averages, 'overall': round(sum(averages.values()) / len(averages), 1)}

    def lab_community(self, token, lab_id):
        lab_id = self._resolve(lab_id)
        me = self._optional_user(token)
        with self.store.db() as db:
            rows = db.execute('SELECT r.*, u.nickname, u.account FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.lab_id=? ORDER BY r.created DESC', (lab_id,)).fetchall()
            grads = db.execute("SELECT * FROM users WHERE role='graduate' AND lab_id=? ORDER BY id", (lab_id,)).fetchall()
            mine = {t['graduate_id']: t['id'] for t in db.execute('SELECT id, graduate_id FROM threads WHERE student_id=?', (me['id'],))} if me else {}
        reviews = [self._review(r, me) for r in rows]
        graduates = []
        for g in grads:
            account = json.loads(g['account'])
            if not account.get('contact_consent'):
                continue
            graduates.append({'id': g['id'], 'name': account.get('real_name', ''), 'program': account.get('program', ''), 'research': account.get('research', ''),
                              'interests': self.interests(account), 'headline': account.get('headline', ''),
                              'email': g['email'] if me else None, 'thread_id': mine.get(g['id'])})
        return {'lab_id': lab_id, 'summary': self.summary(reviews), 'reviews': reviews, 'graduates': graduates,
                'my_review': next((r for r in reviews if r['mine']), None), 'rating_labels': RATINGS,
                'viewer': {'signed_in': bool(me), 'role': me['role'] if me else None,
                           'profile_complete': bool(me and profile_complete(me['nickname'], json.loads(me['account'])))}}

    def board(self, token):
        me = self._optional_user(token)
        with self.store.db() as db:
            rows = db.execute('SELECT r.*, u.nickname, u.account FROM reviews r JOIN users u ON u.id=r.user_id ORDER BY r.created DESC LIMIT 300').fetchall()
        reviews = [r for r in (self._review(row, me, lab=True) for row in rows) if r['lab']]
        by_lab = {}
        for r in reviews:
            by_lab.setdefault(r['lab_id'], []).append(r)
        labs = sorted(({'lab': items[0]['lab'], **self.summary(items)} for items in by_lab.values()), key=lambda x: (-x['count'], x['lab']['professors'][0]))
        return {'reviews': reviews, 'labs': labs, 'rating_labels': RATINGS}

    def save_review(self, token, body):
        user = self.store.current_user(token, complete=True)
        if user['role'] != 'student':
            raise ValueError('대학원생 선배 계정은 연구참여 후기를 작성할 수 없어요.')
        lab_id = self._resolve(body.get('lab_id'))
        if body.get('completed') is not True:
            raise ValueError('연구참여를 마친 경우에만 후기를 남길 수 있어요.')
        ratings = body.get('ratings')
        if not isinstance(ratings, dict) or set(ratings) != set(RATINGS) or any(type(v) is not int or not 1 <= v <= 5 for v in ratings.values()):
            raise ValueError('네 가지 항목을 모두 1~5점으로 평가해 주세요.')
        fields = {'term': _text(body, 'term', '참여 시기', 40, 2), 'duration': _text(body, 'duration', '참여 기간', 40, 1),
                  'activity': _text(body, 'activity', '했던 일', 800, 10), 'good': _text(body, 'good', '좋았던 점', 1500, 10),
                  'improve': _text(body, 'improve', '아쉬운 점', 1500), 'recommend_for': _text(body, 'recommend_for', '추천 대상', 300)}
        now = time.time()
        with self.store.db() as db:
            db.execute('''INSERT INTO reviews(user_id,lab_id,term,duration,activity,ratings,good,improve,recommend_for,created,updated)
                VALUES (:user_id,:lab_id,:term,:duration,:activity,:ratings,:good,:improve,:recommend_for,:now,:now)
                ON CONFLICT(user_id,lab_id) DO UPDATE SET term=excluded.term,duration=excluded.duration,activity=excluded.activity,
                ratings=excluded.ratings,good=excluded.good,improve=excluded.improve,recommend_for=excluded.recommend_for,updated=excluded.updated''',
                {**fields, 'user_id': user['id'], 'lab_id': lab_id, 'ratings': json.dumps(ratings), 'now': now})
        return self.lab_community(token, lab_id)

    def delete_review(self, token, body):
        user = self.store.current_user(token)
        lab_id = self._resolve(body.get('lab_id'))
        with self.store.db() as db:
            db.execute('DELETE FROM reviews WHERE user_id=? AND lab_id=?', (user['id'], lab_id))
        return self.lab_community(token, lab_id)

    # ---- messages ----
    def _rate_limit(self, db, user_id):
        sent = db.execute('SELECT COUNT(*) FROM messages WHERE sender_id=? AND created>?', (user_id, time.time() - 86400)).fetchone()[0]
        if sent >= DAILY_MESSAGES:
            raise ValueError('오늘 보낼 수 있는 쪽지를 모두 사용했어요. 내일 다시 시도해 주세요.')

    def contact(self, token, body):
        user = self.store.current_user(token, complete=True)
        if user['role'] != 'student':
            raise ValueError('학부생 계정에서만 선배에게 연락할 수 있어요.')
        graduate_id = body.get('graduate_id')
        subject = _text(body, 'subject', '제목', 80, 2)
        message = _text(body, 'body', '내용', 2000, 10)
        if type(graduate_id) is not int:
            raise ValueError('연락할 선배를 선택해 주세요.')
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            grad = db.execute("SELECT * FROM users WHERE id=? AND role='graduate'", (graduate_id,)).fetchone()
            if grad is None or not json.loads(grad['account']).get('contact_consent'):
                raise NotFound('연락할 수 있는 선배를 찾지 못했습니다.')
            self._rate_limit(db, user['id'])
            thread = db.execute('SELECT id FROM threads WHERE student_id=? AND graduate_id=?', (user['id'], graduate_id)).fetchone()
            if thread:
                thread_id = thread['id']
                db.execute('UPDATE threads SET updated=? WHERE id=?', (now, thread_id))
            else:
                thread_id = db.execute('INSERT INTO threads(student_id,graduate_id,lab_id,subject,created,updated) VALUES (?,?,?,?,?,?)',
                                       (user['id'], graduate_id, grad['lab_id'], subject, now, now)).lastrowid
            db.execute('INSERT INTO messages(thread_id,sender_id,body,created) VALUES (?,?,?,?)', (thread_id, user['id'], message, now))
        return {'thread_id': thread_id}

    def _thread_for(self, db, user, thread_id):
        if type(thread_id) is not int:
            raise ValueError('대화를 선택해 주세요.')
        thread = db.execute('SELECT * FROM threads WHERE id=? AND (student_id=? OR graduate_id=?)', (thread_id, user['id'], user['id'])).fetchone()
        if thread is None:
            raise NotFound('대화를 찾지 못했습니다.')
        return thread

    def reply(self, token, body):
        user = self.store.current_user(token)
        message = _text(body, 'body', '내용', 2000, 1)
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            thread = self._thread_for(db, user, body.get('thread_id'))
            self._rate_limit(db, user['id'])
            db.execute('INSERT INTO messages(thread_id,sender_id,body,created) VALUES (?,?,?,?)', (thread['id'], user['id'], message, now))
            db.execute('UPDATE threads SET updated=? WHERE id=?', (now, thread['id']))
        return self.thread(token, thread['id'])

    def _party(self, row, viewer_is_graduate, full=False):
        """The other person in a thread as this viewer may see them."""
        account = json.loads(row['account'])
        if viewer_is_graduate:
            # A student who started a conversation shares their profile with that graduate.
            card = {'name': account.get('real_name', ''), 'nickname': row['nickname'], 'department': account.get('department', ''), 'grade': account.get('grade', '')}
            if full:
                card.update({'email': row['email'], 'school': account.get('school', ''), 'second_major': account.get('second_major', ''),
                             'goal': GOALS.get(account.get('goal', ''), ''), 'timing': account.get('timing', ''), 'headline': account.get('headline', ''),
                             'intro': account.get('intro', ''), 'interests': self.interests(account), 'interest_text': account.get('interest_text', '')})
            return card
        card = {'name': account.get('real_name', ''), 'program': account.get('program', ''), 'research': account.get('research', '')}
        if full:
            card.update({'email': row['email'], 'headline': account.get('headline', ''), 'interests': self.interests(account)})
        return card

    def inbox(self, token):
        user = self.store.current_user(token)
        graduate = user['role'] == 'graduate'
        with self.store.db() as db:
            threads = db.execute('SELECT * FROM threads WHERE student_id=? OR graduate_id=? ORDER BY updated DESC', (user['id'], user['id'])).fetchall()
            out = []
            for t in threads:
                other = db.execute('SELECT * FROM users WHERE id=?', (t['student_id'] if graduate else t['graduate_id'],)).fetchone()
                last = db.execute('SELECT * FROM messages WHERE thread_id=? ORDER BY created DESC, id DESC LIMIT 1', (t['id'],)).fetchone()
                unread = db.execute('SELECT COUNT(*) FROM messages WHERE thread_id=? AND sender_id!=? AND read=0', (t['id'], user['id'])).fetchone()[0]
                out.append({'id': t['id'], 'subject': t['subject'], 'lab': self._lab(t['lab_id']) if t['lab_id'] else None, 'other': self._party(other, graduate),
                            'last': {'body': last['body'][:120], 'mine': last['sender_id'] == user['id'], 'created': last['created']} if last else None,
                            'unread': unread, 'updated': t['updated']})
        return {'role': user['role'], 'threads': out}

    def thread(self, token, thread_id):
        user = self.store.current_user(token)
        graduate = user['role'] == 'graduate'
        with self.store.db() as db:
            t = self._thread_for(db, user, thread_id)
            db.execute('UPDATE messages SET read=1 WHERE thread_id=? AND sender_id!=?', (t['id'], user['id']))
            other = db.execute('SELECT * FROM users WHERE id=?', (t['student_id'] if graduate else t['graduate_id'],)).fetchone()
            messages = db.execute('SELECT * FROM messages WHERE thread_id=? ORDER BY created, id', (t['id'],)).fetchall()
            meetings = db.execute('SELECT * FROM meetings WHERE thread_id=? ORDER BY created DESC, id DESC', (t['id'],)).fetchall()
        return {'id': t['id'], 'subject': t['subject'], 'lab': self._lab(t['lab_id']) if t['lab_id'] else None, 'role': user['role'],
                'other': self._party(other, graduate, full=True),
                'messages': [{'id': m['id'], 'body': m['body'], 'mine': m['sender_id'] == user['id'], 'created': m['created']} for m in messages],
                'meetings': [self._meeting(m, user) for m in meetings],
                'meeting_link': {'provider': self.meeting_links.name, 'label': self.meeting_links.label} if self.meeting_links else None}

    # ---- meetings ----
    @staticmethod
    def _when(ts):
        d = datetime.fromtimestamp(ts, KST)
        return f'{d.month}월 {d.day}일({WEEKDAYS[d.weekday()]}) {d:%H:%M}'

    @staticmethod
    def _active(m, now=None):
        return m['status'] == 'requested' or (m['status'] == 'confirmed' and m['start'] + m['minutes'] * 60 > (now or time.time()))

    def _meeting(self, m, user):
        mine = m['proposer_id'] == user['id']
        return {'id': m['id'], 'mode': m['mode'], 'minutes': m['minutes'], 'slots': json.loads(m['slots']), 'place': m['place'], 'note': m['note'],
                'status': m['status'], 'start': m['start'], 'provider': m['provider'], 'join_url': m['join_url'], 'mine': mine,
                'can_confirm': m['status'] == 'requested' and not mine, 'can_cancel': self._active(m), 'created': m['created']}

    @staticmethod
    def _slots(value, now):
        """`YYYY-MM-DDTHH:MM` strings from the browser are Korean local time."""
        if not isinstance(value, list) or not 1 <= len(value) <= MEETING_SLOTS:
            raise ValueError(f'가능한 시간을 1~{MEETING_SLOTS}개 골라 주세요.')
        out = []
        for raw in value:
            try:
                d = datetime.fromisoformat(raw) if isinstance(raw, str) and len(raw) <= 25 else None
            except ValueError:
                d = None
            if d is None:
                raise ValueError('시간 형식을 확인해 주세요.')
            ts = int((d.replace(tzinfo=KST) if d.tzinfo is None else d).timestamp()) // 60 * 60
            if ts < now + 3600:
                raise ValueError('지금부터 1시간 이후의 시간을 골라 주세요.')
            if ts > now + MEETING_HORIZON_DAYS * 86400:
                raise ValueError(f'{MEETING_HORIZON_DAYS}일 이내의 시간을 골라 주세요.')
            out.append(ts)
        if len(set(out)) != len(out):
            raise ValueError('같은 시간이 두 번 들어갔어요.')
        return sorted(out)

    @staticmethod
    def _join_url(body):
        value = _text(body, 'join_url', '화상회의 링크', 500)
        if value and (urlsplit(value).scheme != 'https' or not urlsplit(value).netloc):
            raise ValueError('화상회의 링크는 https://로 시작하는 주소여야 해요.')
        return value

    def _meeting_for(self, db, user, meeting_id):
        if type(meeting_id) is not int:
            raise ValueError('만남 약속을 선택해 주세요.')
        m = db.execute('''SELECT m.* FROM meetings m JOIN threads t ON t.id=m.thread_id
            WHERE m.id=? AND (t.student_id=? OR t.graduate_id=?)''', (meeting_id, user['id'], user['id'])).fetchone()
        if m is None:
            raise NotFound('만남 약속을 찾지 못했습니다.')
        return m

    @staticmethod
    def _notice(db, thread_id, user_id, body, now):
        """Meeting changes are posted in the conversation so the other person sees them as unread."""
        db.execute('INSERT INTO messages(thread_id,sender_id,body,created) VALUES (?,?,?,?)', (thread_id, user_id, body, now))
        db.execute('UPDATE threads SET updated=? WHERE id=?', (now, thread_id))

    def request_meeting(self, token, body):
        """Either party proposes 1–3 times; the other one picks a time to confirm."""
        user = self.store.current_user(token)
        now = time.time()
        mode, minutes = body.get('mode'), body.get('minutes', 20)
        if mode not in MEETING_MODES:
            raise ValueError('대면 또는 온라인을 골라 주세요.')
        if type(minutes) is not int or minutes not in MEETING_MINUTES:
            raise ValueError('만남 시간을 확인해 주세요.')
        slots = self._slots(body.get('slots'), now)
        place = _text(body, 'place', '만날 장소', 100, 2) if mode == 'offline' else ''
        note = _text(body, 'note', '전달할 말', 500)
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            thread = self._thread_for(db, user, body.get('thread_id'))
            if any(self._active(m, now) for m in db.execute('SELECT * FROM meetings WHERE thread_id=?', (thread['id'],))):
                raise ValueError('이미 진행 중인 만남 약속이 있어요. 기존 약속을 취소한 뒤 새로 요청해 주세요.')
            self._rate_limit(db, user['id'])
            db.execute('''INSERT INTO meetings(thread_id,proposer_id,mode,minutes,slots,place,note,status,created,updated)
                VALUES (?,?,?,?,?,?,?,'requested',?,?)''', (thread['id'], user['id'], mode, minutes, json.dumps(slots), place, note, now, now))
            lines = [f'📅 만남 요청 · {MEETING_MODES[mode]} {minutes}분' + (f' · {place}' if place else '')]
            lines += [f'{n}) {self._when(ts)}' for n, ts in enumerate(slots, 1)]
            lines += [note] if note else []
            self._notice(db, thread['id'], user['id'], '\n'.join(lines), now)
        return self.thread(token, thread['id'])

    def confirm_meeting(self, token, body):
        """Picks a proposed time. Online meetings get a Google Meet/Zoom link, or the one the confirmer pasted."""
        user = self.store.current_user(token)
        manual = self._join_url(body)
        start = body.get('start')
        with self.store.db() as db:
            m = self._meeting_for(db, user, body.get('meeting_id'))
            thread = db.execute('SELECT * FROM threads WHERE id=?', (m['thread_id'],)).fetchone()
            people = {r['id']: r for r in db.execute('SELECT * FROM users WHERE id IN (?,?)', (thread['student_id'], thread['graduate_id']))}
        if m['status'] != 'requested':
            raise ValueError('이미 확정되었거나 취소된 요청이에요.')
        if m['proposer_id'] == user['id']:
            raise ValueError('상대방이 시간을 골라야 약속이 확정돼요.')
        if type(start) is not int or start not in json.loads(m['slots']):
            raise ValueError('요청된 시간 중 하나를 골라 주세요.')
        if start < time.time():
            raise ValueError('이미 지난 시간이에요. 새 시간으로 다시 요청해 주세요.')
        provider = external_id = join_url = None
        if m['mode'] == 'online':
            if manual:
                provider, join_url = 'manual', manual
            elif self.meeting_links:
                # The booking call can take seconds, so it runs outside the write transaction; the update below re-checks the status.
                student, graduate = people[thread['student_id']], people[thread['graduate_id']]
                names = [json.loads(p['account']).get('real_name') or p['nickname'] for p in (student, graduate)]
                lab = self._lab(thread['lab_id']) if thread['lab_id'] else None
                description = '\n'.join(filter(None, [f'대화 제목: {thread["subject"]}',
                                                      lab and f'연구실: {" · ".join(lab["professors"])} ({lab["department"]})',
                                                      m['note'] and f'요청 메모: {m["note"]}', '3분커리 쪽지함에서 잡은 만남입니다.']))
                made = self.meeting_links.create(f'[3분커리] {names[0]} · {names[1]} 선배 만남', description,
                                                 datetime.fromtimestamp(start, KST), m['minutes'], [student['email'], graduate['email']])
                provider, external_id, join_url = self.meeting_links.name, made['external_id'], made['join_url']
            else:
                raise ValueError('온라인 만남 링크(Google Meet·Zoom 등)를 입력해 주세요.')
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('''UPDATE meetings SET status='confirmed', start=?, provider=?, join_url=?, external_id=?, closed_by=?, updated=?
                WHERE id=? AND status='requested' ''', (start, provider, join_url, external_id, user['id'], now, m['id'])).rowcount
            if changed:
                where = MEETING_MODES[m['mode']] + (f' · {m["place"]}' if m['place'] else '')
                self._notice(db, m['thread_id'], user['id'], f'✅ 만남 확정 · {self._when(start)}부터 {m["minutes"]}분 · {where}' +
                             (f'\n접속 링크: {join_url}' if join_url else ''), now)
        if not changed:
            self._release(provider, external_id)
            raise ValueError('그 사이 요청이 취소되었어요.')
        return self.thread(token, m['thread_id'])

    def _release(self, provider, external_id):
        if external_id and self.meeting_links and provider == self.meeting_links.name:
            try:
                self.meeting_links.cancel(external_id)
            except MeetingLinkError:
                pass  # already cancelled on our side; a leftover calendar entry is reported in the server log

    def cancel_meeting(self, token, body):
        """Either party withdraws a pending request (declines it) or cancels a confirmed meeting before it ends."""
        user = self.store.current_user(token)
        now = time.time()
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            m = self._meeting_for(db, user, body.get('meeting_id'))
            if not self._active(m, now):
                raise ValueError('이미 끝났거나 취소된 약속이에요.')
            db.execute("UPDATE meetings SET status='cancelled', closed_by=?, updated=? WHERE id=?", (user['id'], now, m['id']))
            if m['status'] == 'confirmed':
                text = f'{self._when(m["start"])} 만남 약속을 취소했어요.'
            elif m['proposer_id'] == user['id']:
                text = '만남 요청을 취소했어요.'
            else:
                text = '요청한 시간에는 만나기 어려워요. 다른 시간으로 다시 요청해 주세요.'
            self._notice(db, m['thread_id'], user['id'], f'↩ {text}', now)
        self._release(m['provider'], m['external_id'])
        return self.thread(token, m['thread_id'])

    def unread(self, token):
        try:
            user = self.store.current_user(token)
        except Exception:
            return 0
        with self.store.db() as db:
            return db.execute('''SELECT COUNT(*) FROM messages m JOIN threads t ON t.id=m.thread_id
                WHERE (t.student_id=? OR t.graduate_id=?) AND m.sender_id!=? AND m.read=0''', (user['id'], user['id'], user['id'])).fetchone()[0]

    # ---- dummy seed ----
    def migrate_lab_ids(self):
        """Rewrite stored lab IDs that the catalog now knows under another (canonical) ID. Unknown IDs stay as they are."""
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for table in ('users', 'reviews', 'threads'):
                for (old,) in db.execute(f'SELECT DISTINCT lab_id FROM {table} WHERE lab_id IS NOT NULL').fetchall():
                    try:
                        new = self.catalog.resolve(old)
                    except KeyError:
                        continue
                    if new != old:
                        # A review already saved for the new ID wins over the old duplicate.
                        db.execute(f'UPDATE OR IGNORE {table} SET lab_id=? WHERE lab_id=?', (new, old))

    def seed(self, data):
        """Idempotently insert the fictional demo community. Rows keep `dummy=1` for later removal."""
        ids, digest, salt = {}, None, None
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for u in data.get('users', []):
                row = db.execute('SELECT id FROM users WHERE email=?', (u['email'],)).fetchone()
                if row:
                    ids[u['key']] = row['id']
                    continue
                lab_id = None
                if u.get('lab_id'):
                    try:
                        lab_id = self.catalog.resolve(u['lab_id'])
                    except KeyError:
                        continue
                if digest is None:
                    # One shared salt for the demo accounts only; real accounts get their own in Store.authenticate.
                    salt = secrets.token_hex(16)
                    digest = hashlib.scrypt(data['demo_password'].encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, maxmem=64*1024*1024).hex()
                try:
                    ids[u['key']] = db.execute('INSERT INTO users(email,salt,password_hash,nickname,role,lab_id,account,dummy) VALUES (?,?,?,?,?,?,?,1)',
                                               (u['email'], salt, digest, u['nickname'], u['role'], lab_id, json.dumps(u['account'], ensure_ascii=False))).lastrowid
                except sqlite3.IntegrityError:
                    continue  # a real user already took this nickname
            for r in data.get('reviews', []):
                try:
                    lab_id = self.catalog.resolve(r['lab_id'])
                except KeyError:
                    continue
                if r['author'] in ids:
                    db.execute('''INSERT OR IGNORE INTO reviews(user_id,lab_id,term,duration,activity,ratings,good,improve,recommend_for,dummy,created,updated)
                        VALUES (?,?,?,?,?,?,?,?,?,1,?,?)''', (ids[r['author']], lab_id, r['term'], r['duration'], r['activity'], json.dumps(r['ratings']),
                                                          r['good'], r['improve'], r['recommend_for'], r['created'], r['created']))
            for t in data.get('threads', []):
                student, grad = ids.get(t['student']), ids.get(t['graduate'])
                if not student or not grad or db.execute('SELECT 1 FROM threads WHERE student_id=? AND graduate_id=?', (student, grad)).fetchone():
                    continue
                lab_id = db.execute('SELECT lab_id FROM users WHERE id=?', (grad,)).fetchone()['lab_id']
                created = t['messages'][0]['created']
                tid = db.execute('INSERT INTO threads(student_id,graduate_id,lab_id,subject,dummy,created,updated) VALUES (?,?,?,?,1,?,?)',
                                 (student, grad, lab_id, t['subject'], created, t['messages'][-1]['created'])).lastrowid
                for n, m in enumerate(t['messages']):
                    # Anything before the latest message has been answered, so it was read.
                    db.execute('INSERT INTO messages(thread_id,sender_id,body,created,read) VALUES (?,?,?,?,?)',
                               (tid, ids[m['from']], m['body'], m['created'], int(n < len(t['messages']) - 1)))
