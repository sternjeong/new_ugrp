"""Anonymous per-lab Q&A: signed-in students ask without showing who they are; approved graduates of that lab answer
under their program. Askers are known to the server (for abuse handling) but never shown to anyone."""
import json
import time

QUESTIONS_PER_DAY = 5
ANSWERS_PER_DAY = 30


def _body(body, key, label, limit, minimum):
    value = body.get(key)
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= limit:
        raise ValueError(f'{label}은(는) {minimum}~{limit}자로 입력해 주세요.')
    return value.strip()


class LabQnA:
    def __init__(self, store, catalog):
        self.store, self.catalog = store, catalog
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS qna_questions (
                id INTEGER PRIMARY KEY, lab_id TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
                body TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS qna_lab ON qna_questions(lab_id);
            CREATE TABLE IF NOT EXISTS qna_answers (
                id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES qna_questions(id),
                user_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL,
                hidden INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
            ''')

    def _viewer(self, token):
        session = self.store.get_session(token)
        if not session or not session['user_id']:
            return None
        try:
            return self.store.current_user(token)
        except Exception:
            return None

    def list(self, token, lab_id):
        lab_id = self.catalog.resolve(lab_id if isinstance(lab_id, str) else '')
        me = self._viewer(token)
        with self.store.db() as db:
            questions = db.execute('SELECT * FROM qna_questions WHERE lab_id=? AND hidden=0 ORDER BY created DESC LIMIT 50', (lab_id,)).fetchall()
            answers = {}
            if questions:
                marks = ','.join('?' * len(questions))
                for a in db.execute(f'''SELECT a.*, u.account, u.nickname FROM qna_answers a JOIN users u ON u.id=a.user_id
                                        WHERE a.question_id IN ({marks}) AND a.hidden=0 ORDER BY a.created''', [q['id'] for q in questions]):
                    account = json.loads(a['account'] or '{}')
                    answers.setdefault(a['question_id'], []).append({
                        'id': a['id'], 'body': a['body'], 'created': a['created'], 'mine': bool(me and me['id'] == a['user_id']),
                        'author': f"{account.get('program') or '선배'} · {a['nickname'] or '선배'}"})
        can_answer = bool(me and me['role'] == 'graduate' and me['lab_id'] == lab_id)
        return {'lab_id': lab_id, 'can_ask': bool(me and me['role'] == 'student'), 'can_answer': can_answer,
                'questions': [{'id': q['id'], 'body': q['body'], 'created': q['created'], 'author': '익명 학생',
                               'mine': bool(me and me['id'] == q['user_id']), 'answers': answers.get(q['id'], [])} for q in questions]}

    def ask(self, token, body):
        user = self.store.current_user(token, complete=True)
        if user['role'] != 'student':
            raise ValueError('학부생 계정에서 질문할 수 있어요.')
        lab_id = self.catalog.resolve(body.get('lab_id') if isinstance(body.get('lab_id'), str) else '')
        text = _body(body, 'body', '질문', 1000, 10)
        with self.store.db() as db:
            if db.execute('SELECT COUNT(*) FROM qna_questions WHERE user_id=? AND created>?', (user['id'], time.time() - 86400)).fetchone()[0] >= QUESTIONS_PER_DAY:
                raise ValueError('질문은 하루 5개까지 올릴 수 있어요.')
            qid = db.execute('INSERT INTO qna_questions(lab_id,user_id,body,created) VALUES (?,?,?,?)', (lab_id, user['id'], text, time.time())).lastrowid
        return {'question_id': qid, **self.list(token, lab_id)}

    def answer(self, token, body):
        user = self.store.current_user(token)
        qid = body.get('question_id')
        if type(qid) is not int:
            raise ValueError('질문을 선택해 주세요.')
        text = _body(body, 'body', '답변', 2000, 5)
        with self.store.db() as db:
            q = db.execute('SELECT * FROM qna_questions WHERE id=? AND hidden=0', (qid,)).fetchone()
            if q is None:
                raise ValueError('질문을 찾지 못했어요.')
            if user['role'] != 'graduate' or user['lab_id'] != q['lab_id']:
                raise ValueError('이 연구실 선배만 답할 수 있어요.')
            if db.execute('SELECT COUNT(*) FROM qna_answers WHERE user_id=? AND created>?', (user['id'], time.time() - 86400)).fetchone()[0] >= ANSWERS_PER_DAY:
                raise ValueError('오늘 답변 한도를 모두 사용했어요.')
            db.execute('INSERT INTO qna_answers(question_id,user_id,body,created) VALUES (?,?,?,?)', (qid, user['id'], text, time.time()))
        return self.list(token, q['lab_id'])

    def delete(self, token, body):
        """Authors may remove their own question (with its answers) or answer."""
        user = self.store.current_user(token)
        kind, ref = body.get('kind'), body.get('id')
        if kind not in ('question', 'answer') or type(ref) is not int:
            raise ValueError('삭제할 글을 확인해 주세요.')
        with self.store.db() as db:
            if kind == 'question':
                q = db.execute('SELECT * FROM qna_questions WHERE id=? AND user_id=?', (ref, user['id'])).fetchone()
                if q is None:
                    raise ValueError('내가 쓴 질문만 지울 수 있어요.')
                db.execute('DELETE FROM qna_answers WHERE question_id=?', (ref,))
                db.execute('DELETE FROM qna_questions WHERE id=?', (ref,))
                lab_id = q['lab_id']
            else:
                a = db.execute('SELECT a.*, q.lab_id FROM qna_answers a JOIN qna_questions q ON q.id=a.question_id WHERE a.id=? AND a.user_id=?', (ref, user['id'])).fetchone()
                if a is None:
                    raise ValueError('내가 쓴 답변만 지울 수 있어요.')
                db.execute('DELETE FROM qna_answers WHERE id=?', (ref,))
                lab_id = a['lab_id']
        return self.list(token, lab_id)
