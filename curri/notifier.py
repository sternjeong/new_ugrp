"""Notification mail for conversations, meetings and Q&A, found by scanning the tables once a minute.

Community code stays unaware of mail. New messages are found by id above a stored watermark (set to the current
maximum on first start, so turning notifications on never mails old history). Each mail type is sent once per
reference, recorded in `notifications_sent`. Only verified, non-dummy, non-deleted accounts receive mail, and each
person's settings are respected.
"""
from datetime import datetime
import json
import threading

from . import errors
import time

from .community import KST, WEEKDAYS

DELAY = 120               # wait so a quick reply or read cancels the mail and bursts become one mail
NUDGE_AFTER = 48 * 3600
REMIND_BEFORE = 24 * 3600


class Notifier:
    def __init__(self, store, mailer):
        self.store, self.mailer = store, mailer
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notifications_sent (kind TEXT NOT NULL, ref TEXT NOT NULL, sent REAL NOT NULL, PRIMARY KEY(kind, ref));
            ''')
            for key, table in (('notify_message_id', 'messages'), ('notify_answer_id', 'qna_answers')):
                if not db.execute('SELECT 1 FROM meta WHERE key=?', (key,)).fetchone():
                    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                    top = db.execute(f'SELECT COALESCE(MAX(id),0) FROM {table}').fetchone()[0] if exists else 0
                    db.execute('INSERT INTO meta(key,value) VALUES (?,?)', (key, str(top)))

    @staticmethod
    def _wants(user, kind):
        return (user['email_verified'] and not user['deleted'] and not user['dummy'] and not user['suspended']
                and json.loads(user['notify'] or '{}').get(kind, True))

    def _once(self, db, kind, ref):
        return db.execute('INSERT OR IGNORE INTO notifications_sent(kind,ref,sent) VALUES (?,?,?)', (kind, str(ref), time.time())).rowcount == 1

    @staticmethod
    def _when(ts):
        d = datetime.fromtimestamp(ts, KST)
        return f'{d.month}월 {d.day}일({WEEKDAYS[d.weekday()]}) {d.hour:02d}:{d.minute:02d}'

    def messages(self, now):
        with self.store.db() as db:
            mark = int(db.execute("SELECT value FROM meta WHERE key='notify_message_id'").fetchone()['value'])
            rows = db.execute('''SELECT m.*, t.student_id, t.graduate_id, t.subject, s.nickname sender
                                 FROM messages m JOIN threads t ON t.id=m.thread_id JOIN users s ON s.id=m.sender_id
                                 WHERE m.id>? AND m.created<=? ORDER BY m.id''', (mark, now - DELAY)).fetchall()
            if not rows:
                return 0
            per_user = {}
            for r in rows:
                recipient = r['graduate_id'] if r['sender_id'] == r['student_id'] else r['student_id']
                if not r['read']:
                    per_user.setdefault(recipient, []).append(r)
            db.execute("UPDATE meta SET value=? WHERE key='notify_message_id'", (str(rows[-1]['id']),))
            users = {u['id']: u for u in db.execute(f'SELECT * FROM users WHERE id IN ({",".join("?" * len(per_user))})', list(per_user))} if per_user else {}
        sent = 0
        for uid, items in per_user.items():
            user = users.get(uid)
            kind = 'meetings' if all(i['body'][:1] in '📅✅↩' for i in items) else 'messages'
            if not user or not self._wants(user, kind):
                continue
            lines = [f"• {i['sender'] or '탈퇴한 사용자'} — {i['subject']}: {i['body'][:80]}" for i in items[:10]]
            self.mailer.send(user['email'], f'[3분커리] 새 쪽지 {len(items)}개', '읽지 않은 쪽지가 있어요.\n\n' + '\n'.join(lines)
                             + f'\n\n쪽지함: {self.mailer.link("/inbox")}', kind, uid)
            sent += 1
        return sent

    def reminders(self, now):
        with self.store.db() as db:
            rows = db.execute('''SELECT m.*, t.student_id, t.graduate_id, t.subject FROM meetings m JOIN threads t ON t.id=m.thread_id
                                 WHERE m.status='confirmed' AND m.start BETWEEN ? AND ?''', (now, now + REMIND_BEFORE)).fetchall()
            todo = [r for r in rows if self._once(db, 'meeting_reminder', r['id'])]
            users = {u['id']: u for u in db.execute('SELECT * FROM users WHERE id IN (%s)' % ','.join('?' * (2 * len(todo))),
                                                     [x for r in todo for x in (r['student_id'], r['graduate_id'])])} if todo else {}
        for r in todo:
            where = r['join_url'] or r['place'] or ''
            for uid in (r['student_id'], r['graduate_id']):
                user = users.get(uid)
                if user and self._wants(user, 'meetings'):
                    self.mailer.send(user['email'], '[3분커리] 내일 만남이 있어요',
                                     f"{self._when(r['start'])} · {r['minutes']}분 · {r['subject']}\n{where}\n\n대화 보기: {self.mailer.link('/inbox')}",
                                     'meetings', uid)
        return len(todo)

    def nudges(self, now):
        """Graduates who left a student's first message unanswered for 48 hours get one reminder."""
        with self.store.db() as db:
            rows = db.execute('''SELECT t.*, (SELECT sender_id FROM messages WHERE thread_id=t.id ORDER BY id DESC LIMIT 1) last_sender,
                                        (SELECT MAX(id) FROM messages WHERE thread_id=t.id) last_id,
                                        (SELECT created FROM messages WHERE thread_id=t.id ORDER BY id DESC LIMIT 1) last_at
                                 FROM threads t WHERE t.dummy=0''').fetchall()
            todo = [r for r in rows if r['last_sender'] == r['student_id'] and r['last_at'] and now - NUDGE_AFTER > r['last_at'] > now - 7 * 86400
                    and self._once(db, 'nudge', r['last_id'])]
            users = {u['id']: u for u in db.execute('SELECT * FROM users WHERE id IN (%s)' % ','.join('?' * len(todo)), [r['graduate_id'] for r in todo])} if todo else {}
        for r in todo:
            user = users.get(r['graduate_id'])
            if user and self._wants(user, 'messages'):
                self.mailer.send(user['email'], '[3분커리] 답장을 기다리는 쪽지가 있어요',
                                 f"‘{r['subject']}’ 쪽지에 이틀째 답장이 없어요. 어렵다면 짧게라도 알려 주시면 학생에게 큰 도움이 돼요.\n\n{self.mailer.link('/inbox')}",
                                 'messages', r['graduate_id'])
        return len(todo)

    def answers(self, now):
        with self.store.db() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='qna_answers'").fetchone():
                return 0
            mark = int(db.execute("SELECT value FROM meta WHERE key='notify_answer_id'").fetchone()['value'])
            rows = db.execute('''SELECT a.id AS answer_id, q.lab_id, q.body AS question, u.* FROM qna_answers a JOIN qna_questions q ON q.id=a.question_id
                                 JOIN users u ON u.id=q.user_id WHERE a.id>? AND a.created<=? AND a.hidden=0 ORDER BY a.id''', (mark, now - DELAY)).fetchall()
            if rows:
                db.execute("UPDATE meta SET value=? WHERE key='notify_answer_id'", (str(rows[-1]['answer_id']),))
        for r in rows:
            if self._wants(r, 'qna'):
                self.mailer.send(r['email'], '[3분커리] 질문에 선배가 답했어요', f"질문: {r['question'][:120]}\n\n답변 보기: {self.mailer.link('/lab/' + r['lab_id'])}",
                                 'qna', r['id'])
        return len(rows)

    def meeting_feedback(self, now):
        """One mail to both people about an hour after a confirmed meeting ended, asking how it went."""
        with self.store.db() as db:
            rows = db.execute('''SELECT m.*, t.student_id, t.graduate_id, t.subject FROM meetings m JOIN threads t ON t.id=m.thread_id
                                 WHERE m.status='confirmed' AND m.start + m.minutes*60 BETWEEN ? AND ?''', (now - 2 * 86400, now - 3600)).fetchall()
            todo = [r for r in rows if self._once(db, 'meeting_feedback', r['id'])]
            users = {u['id']: u for u in db.execute('SELECT * FROM users WHERE id IN (%s)' % ','.join('?' * (2 * len(todo))),
                                                     [x for r in todo for x in (r['student_id'], r['graduate_id'])])} if todo else {}
        for r in todo:
            for uid in (r['student_id'], r['graduate_id']):
                user = users.get(uid)
                if user and self._wants(user, 'meetings'):
                    self.mailer.send(user['email'], '[3분커리] 만남은 어떠셨나요?',
                                     f"‘{r['subject']}’ 만남이 끝났어요. 10초면 되는 평가를 남겨 주시면 다음 학생과 선배에게 큰 도움이 돼요.\n\n평가하기: {self.mailer.link('/inbox')}",
                                     'meetings', uid)
        return len(todo)

    def run_once(self, now=None):
        now = now or time.time()
        return {'messages': self.messages(now), 'reminders': self.reminders(now), 'nudges': self.nudges(now), 'answers': self.answers(now),
                'meeting_feedback': self.meeting_feedback(now)}

    def start(self):
        def loop():
            while True:
                try:
                    self.run_once()
                except Exception as exc:
                    print(f'notifier error: {type(exc).__name__}', flush=True)
                    errors.record('notifier', exc)
                time.sleep(60)
        threading.Thread(target=loop, daemon=True, name='notifier').start()
