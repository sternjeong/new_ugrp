"""User feedback and how it flows back into search.

Collected:
- explicit: per result 👍/👎 with reasons, per search "found what I wanted?", per AI topic 👍/👎 with reasons,
  per meeting 1–5 after it happened, and a short service rating (1–5 + comment).
- implicit signals tied to the interpreted query: result opened (with rank), saved, contacted.

Used:
1. `rerank()` — for a query key with enough evidence, labs that students found useful move up and labs voted down
   repeatedly move down. Runs only for the 'feedback' arm of the 'rank' experiment so its effect can be measured.
2. `judgments()` / `evaluate()` — a growing evaluation set (query → relevant labs) for nDCG@10 and MRR of the engine.
3. `expansion_candidates()` — zero-result and down-voted query words for the dictionary; the admin adds variants,
   stored in `.local/expansions.json` and merged into the live dictionary.
4. AI guide retries carry the student's reasons so the next proposal avoids what did not fit.

Query keys are the interpreter's liked phrases, so differently worded queries with the same reading share evidence.
Signals and feedback use the pseudonymous session hash; free-text comments are kept 1 year, signals 180 days.
"""
import json
import math
from pathlib import Path
import time

from .accounts import session_hash
from .curated_catalog import EXPANSIONS, SEARCH_STOPWORDS, search_terms

KINDS = {'result', 'search', 'guide', 'meeting', 'service'}
RESULT_REASONS = {'off_topic': '관심 분야와 달라요', 'too_hard': '지금 하기엔 어려워요', 'known': '이미 알던 곳이에요',
                  'no_info': '정보가 부족해요', 'great': '딱 찾던 곳이에요', 'new': '몰랐는데 흥미로워요'}
GUIDE_REASONS = {'off_topic': '관심과 안 맞아요', 'too_hard': '너무 어려워요', 'too_easy': '너무 쉬워요',
                 'vague': '첫 단계가 막연해요', 'wrong_fact': '연구실 내용이 틀려요', 'courses': '과목 연결이 억지예요'}
SIGNAL_WEIGHT = {'open': 0.5, 'save': 2.0, 'contact': 3.0, 'up': 2.0, 'down': -2.5}
GENERIC_WORDS = {'비전', '로봇', '데이터', '시스템', '소재', '공정', '인공지능', 'ai', '컴퓨터', '공학', '수업', '과목', '하고', '싶어', '싶어요', '연구실', '궁금해요', '궁금한', '좋겠어요', '재밌어요', '분야', '교수님'}
MIN_EVIDENCE = 4       # weighted signals for a key before it changes anyone's ranking
PRIOR = 3.0            # smoothing: a lab needs repeated agreement, not one click
SIGNAL_RETENTION = 180 * 86400
COMMENT_RETENTION = 365 * 86400


def query_key(likes, norm=''):
    likes = [x.strip().lower() for x in (likes or []) if x and x.strip()]
    return ' | '.join(sorted(dict.fromkeys(likes))) or (norm or '').strip().lower()[:120]


class Feedback:
    def __init__(self, store, catalog, secret, expansions_path=None):
        self.store, self.catalog, self.secret = store, catalog, secret
        self.expansions_path = Path(expansions_path) if expansions_path else None
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY, ts REAL NOT NULL, session TEXT NOT NULL, user_id INTEGER, kind TEXT NOT NULL,
                query_key TEXT, query_text TEXT, lab_id TEXT, rank INTEGER, ref_id INTEGER, arm TEXT,
                rating INTEGER, helpful INTEGER, reasons TEXT NOT NULL DEFAULT '[]', comment TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new');
            CREATE INDEX IF NOT EXISTS feedback_kind ON feedback(kind, ts);
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY, ts REAL NOT NULL, session TEXT NOT NULL, query_key TEXT NOT NULL,
                lab_id TEXT NOT NULL, kind TEXT NOT NULL, rank INTEGER);
            CREATE INDEX IF NOT EXISTS signals_key ON signals(query_key);
            ''')
            db.execute('DELETE FROM signals WHERE ts<?', (time.time() - SIGNAL_RETENTION,))
            db.execute("UPDATE feedback SET comment='', query_text=NULL WHERE ts<? AND (comment!='' OR query_text IS NOT NULL)",
                       (time.time() - COMMENT_RETENTION,))
        self.load_expansions()

    # ---- dictionary expansions managed from the admin console ----
    def load_expansions(self):
        if self.expansions_path and self.expansions_path.is_file():
            for term, variants in json.loads(self.expansions_path.read_text()).items():
                EXPANSIONS[term] = list(dict.fromkeys(EXPANSIONS.get(term, []) + variants))

    def add_expansion(self, term, variants):
        term = (term or '').strip().lower()
        variants = [v.strip().lower() for v in variants if isinstance(v, str) and 2 <= len(v.strip()) <= 60][:8]
        if not 2 <= len(term) <= 30 or not variants:
            raise ValueError('단어(2~30자)와 확장 표현(1~8개)을 확인해 주세요.')
        saved = json.loads(self.expansions_path.read_text()) if self.expansions_path and self.expansions_path.is_file() else {}
        saved[term] = list(dict.fromkeys(saved.get(term, []) + variants))
        if self.expansions_path:
            self.expansions_path.write_text(json.dumps(saved, ensure_ascii=False, indent=1))
        EXPANSIONS[term] = list(dict.fromkeys(EXPANSIONS.get(term, []) + variants))
        self.catalog._search_cache.clear()
        return {'term': term, 'variants': EXPANSIONS[term]}

    def saved_expansions(self):
        return json.loads(self.expansions_path.read_text()) if self.expansions_path and self.expansions_path.is_file() else {}

    # ---- collection ----
    def _profile_key(self, token):
        """Query key of the session's current search (stored in the profile at search time)."""
        session = self.store.get_session(token)
        if not session:
            return None, None
        profile = json.loads(session['profile'] or '{}')
        if session['user_id']:
            with self.store.db() as db:
                row = db.execute('SELECT profile FROM users WHERE id=?', (session['user_id'],)).fetchone()
            profile = json.loads(row['profile'] or '{}') if row else profile
        return profile.get('query_key'), profile.get('interests')

    def signal(self, token, kind, lab_id, rank=None):
        key, _ = self._profile_key(token)
        if not key or kind not in SIGNAL_WEIGHT:
            return
        sess = session_hash(token, self.secret)
        with self.store.db() as db:
            # one signal of each kind per session, lab and query
            if db.execute('SELECT 1 FROM signals WHERE session=? AND query_key=? AND lab_id=? AND kind=?', (sess, key, lab_id, kind)).fetchone():
                return
            db.execute('INSERT INTO signals(ts,session,query_key,lab_id,kind,rank) VALUES (?,?,?,?,?,?)',
                       (time.time(), sess, key, lab_id, kind, rank if type(rank) is int else None))

    def submit(self, token, user_id, body, arm=None):
        kind = body.get('kind')
        if kind not in KINDS:
            raise ValueError('피드백 종류를 확인해 주세요.')
        comment = body.get('comment', '')
        if not isinstance(comment, str) or len(comment) > 1000:
            raise ValueError('의견은 1,000자 이내로 적어 주세요.')
        reasons = body.get('reasons', [])
        allowed = RESULT_REASONS if kind == 'result' else GUIDE_REASONS if kind == 'guide' else {}
        if not isinstance(reasons, list) or any(r not in allowed for r in reasons):
            raise ValueError('이유를 목록에서 골라 주세요.')
        rating, helpful = body.get('rating'), body.get('helpful')
        if rating is not None and (type(rating) is not int or not 1 <= rating <= 5):
            raise ValueError('점수는 1~5로 골라 주세요.')
        if helpful is not None and not isinstance(helpful, bool):
            raise ValueError('도움 여부를 확인해 주세요.')
        if kind in ('result', 'guide') and helpful is None:
            raise ValueError('도움이 됐는지 골라 주세요.')
        if kind in ('meeting', 'service') and rating is None:
            raise ValueError('점수를 골라 주세요.')
        lab_id = self.catalog.resolve(body['lab_id']) if isinstance(body.get('lab_id'), str) and body['lab_id'] else None
        if kind in ('result', 'guide') and not lab_id:
            raise ValueError('연구실을 확인해 주세요.')
        ref = body.get('ref_id') if type(body.get('ref_id')) is int else None
        if kind == 'meeting':
            ref = self._check_meeting(user_id, ref)
        key, text = self._profile_key(token)
        sess = session_hash(token, self.secret)
        rank = body.get('rank') if type(body.get('rank')) is int else None
        with self.store.db() as db:
            if db.execute('SELECT COUNT(*) FROM feedback WHERE session=? AND ts>?', (sess, time.time() - 3600)).fetchone()[0] >= 60:
                raise ValueError('피드백을 너무 많이 보냈어요. 잠시 후 다시 시도해 주세요.')
            same = {'result': 'kind=? AND session=? AND query_key IS ? AND lab_id=?', 'guide': 'kind=? AND session=? AND lab_id=? AND rank IS ?',
                    'search': 'kind=? AND session=? AND query_key IS ?', 'meeting': 'kind=? AND session=? AND ref_id=?'}.get(kind)
            args = {'result': (kind, sess, key, lab_id), 'guide': (kind, sess, lab_id, rank), 'search': (kind, sess, key),
                    'meeting': (kind, sess, ref)}.get(kind)
            if same:
                db.execute(f'DELETE FROM feedback WHERE {same}', args)  # the latest answer replaces an earlier one
            db.execute('''INSERT INTO feedback(ts,session,user_id,kind,query_key,query_text,lab_id,rank,ref_id,arm,rating,helpful,reasons,comment)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (time.time(), sess, user_id, kind, key if kind in ('result', 'search') else None,
                        text[:300] if text and kind in ('result', 'search') else None, lab_id, rank, ref, arm, rating,
                        None if helpful is None else int(helpful), json.dumps(reasons), comment.strip()))
        if kind == 'result':
            self.signal(token, 'up' if helpful else 'down', lab_id, rank)
        return {'ok': True}

    def _check_meeting(self, user_id, meeting_id):
        if not user_id or meeting_id is None:
            raise ValueError('만남을 확인해 주세요.')
        with self.store.db() as db:
            row = db.execute('''SELECT m.id FROM meetings m JOIN threads t ON t.id=m.thread_id
                                WHERE m.id=? AND m.status='confirmed' AND m.start<? AND (t.student_id=? OR t.graduate_id=?)''',
                             (meeting_id, time.time(), user_id, user_id)).fetchone()
        if row is None:
            raise ValueError('끝난 만남만 평가할 수 있어요.')
        return row['id']

    def pending_meetings(self, user_id):
        """Confirmed meetings that have ended and this person has not rated yet (shown in the inbox)."""
        with self.store.db() as db:
            rows = db.execute('''SELECT m.id, m.thread_id, m.start, m.minutes FROM meetings m JOIN threads t ON t.id=m.thread_id
                                 WHERE m.status='confirmed' AND m.start + m.minutes*60 < ? AND m.start > ? AND (t.student_id=? OR t.graduate_id=?)
                                 AND NOT EXISTS (SELECT 1 FROM feedback f WHERE f.kind='meeting' AND f.ref_id=m.id AND f.user_id=?)''',
                              (time.time(), time.time() - 30 * 86400, user_id, user_id, user_id)).fetchall()
        return [dict(r) for r in rows]

    # ---- use: reranking ----
    def lab_scores(self, key):
        with self.store.db() as db:
            rows = db.execute('SELECT lab_id, kind, COUNT(*) n FROM signals WHERE query_key=? GROUP BY lab_id, kind', (key,)).fetchall()
        scores, evidence = {}, 0.0
        for r in rows:
            w = SIGNAL_WEIGHT[r['kind']] * r['n']
            scores[r['lab_id']] = scores.get(r['lab_id'], 0.0) + w
            evidence += abs(w)
        return {lid: s / (PRIOR + abs(s)) for lid, s in scores.items()}, evidence

    def rerank(self, key, labs):
        """Blend the engine order with accumulated feedback for this query. Returns (labs, applied)."""
        scores, evidence = self.lab_scores(key)
        if evidence < MIN_EVIDENCE or not labs:
            return labs, False
        ids = [c['id'] for c in labs]
        base = {lid: 1 / (10 + i + 1) for i, lid in enumerate(ids)}
        extra = [lid for lid, s in sorted(scores.items(), key=lambda kv: -kv[1]) if s > 0.4 and lid not in base and lid in self.catalog.profiles][:2]
        cards = {c['id']: c for c in labs}
        for lid in extra:
            card = self.catalog.card(lid)
            card.update(evidence=[], matched_topics=[], connection='feedback',
                        reason='같은 관심으로 찾아본 학생들이 도움이 됐다고 한 연구실이에요.')
            cards[lid] = card
            base[lid] = 1 / (10 + len(ids) + 1)
        final = {lid: b + 0.08 * scores.get(lid, 0.0) for lid, b in base.items()}
        order = sorted(final, key=lambda lid: -final[lid])
        out = []
        for lid in order[:len(labs)]:
            card = dict(cards[lid])
            if scores.get(lid, 0) > 0.4 and card.get('connection') != 'feedback':
                card['social'] = '같은 관심의 학생들이 도움이 됐다고 했어요'
            out.append(card)
        return out, True

    # ---- use: evaluation set ----
    def judgments(self, min_positive=1):
        """{query_key: {'text': example query, 'labs': {lab_id: gain}}} from explicit votes and strong implicit signals."""
        with self.store.db() as db:
            rows = db.execute('SELECT query_key, lab_id, kind, COUNT(*) n FROM signals GROUP BY query_key, lab_id, kind').fetchall()
            texts = {r['query_key']: r['query_text'] for r in db.execute(
                "SELECT query_key, query_text FROM feedback WHERE query_text IS NOT NULL AND query_key IS NOT NULL GROUP BY query_key")}
        gains = {}
        for r in rows:
            g = {'up': 2, 'contact': 2, 'save': 1, 'down': -2, 'open': 0}[r['kind']] * r['n']
            gains.setdefault(r['query_key'], {}).setdefault(r['lab_id'], 0)
            gains[r['query_key']][r['lab_id']] += g
        out = {}
        for key, labs in gains.items():
            positive = {lid: min(3, g) for lid, g in labs.items() if g > 0}
            if len(positive) >= min_positive:
                out[key] = {'text': texts.get(key) or key.replace(' | ', ', '), 'labs': positive}
        return out

    @staticmethod
    def _ndcg(ranked, gains, k=10):
        dcg = sum(gains.get(lid, 0) / math.log2(i + 2) for i, lid in enumerate(ranked[:k]))
        ideal = sum(g / math.log2(i + 2) for i, g in enumerate(sorted(gains.values(), reverse=True)[:k]))
        return dcg / ideal if ideal else 0.0

    def evaluate(self, search):
        """Run `search(text) -> [lab ids]` over the evaluation set; nDCG@10, MRR, Recall@10, with and without feedback."""
        items = self.judgments()
        rows = []
        for key, item in items.items():
            ranked = search(item['text'])
            fed, _ = self.rerank(key, [{'id': lid} for lid in ranked]) if ranked else ([], False)
            fed_ids = [c['id'] for c in fed]
            rr = next((1 / (i + 1) for i, lid in enumerate(ranked[:10]) if lid in item['labs']), 0.0)
            rows.append({'query': item['text'][:80], 'relevant': len(item['labs']), 'ndcg': round(self._ndcg(ranked, item['labs']), 3),
                         'ndcg_feedback': round(self._ndcg(fed_ids, item['labs']), 3), 'mrr': round(rr, 3),
                         'recall10': round(len(set(ranked[:10]) & set(item['labs'])) / len(item['labs']), 3)})
        mean = lambda k: round(sum(r[k] for r in rows) / len(rows), 3) if rows else None
        return {'queries': len(rows), 'ndcg10': mean('ndcg'), 'ndcg10_feedback': mean('ndcg_feedback'), 'mrr': mean('mrr'),
                'recall10': mean('recall10'), 'rows': sorted(rows, key=lambda r: r['ndcg'])[:50],
                'note': '평가셋은 학생의 👍·저장·연락에서 만들어져요. 피드백 재정렬 수치는 같은 피드백으로 평가하므로 낙관적이에요.'}

    # ---- use: dictionary candidates ----
    def expansion_candidates(self, zero_queries):
        with self.store.db() as db:
            down = db.execute('''SELECT query_key, COUNT(*) n FROM feedback WHERE (kind='result' AND helpful=0) OR (kind='search' AND rating<=2)
                                 GROUP BY query_key ORDER BY n DESC LIMIT 30''').fetchall()
        known = set(EXPANSIONS)
        out = {}
        for text, n, source in [(z['text'], z['n'], '결과 0건') for z in zero_queries] + [(r['query_key'] or '', r['n'], '불만족') for r in down]:
            # the engine's own tokenizer: particles stripped, stopwords dropped, known compounds joined
            for word in search_terms(text.replace('|', ' ')):
                if word not in known and word not in SEARCH_STOPWORDS and 2 <= len(word) <= 20 and word not in GENERIC_WORDS:
                    entry = out.setdefault(word.lower(), {'word': word.lower(), 'count': 0, 'sources': set(), 'examples': []})
                    entry['count'] += n
                    entry['sources'].add(source)
                    if len(entry['examples']) < 3 and text not in entry['examples']:
                        entry['examples'].append(text[:80])
        rows = sorted(out.values(), key=lambda e: -e['count'])[:40]
        return [{**e, 'sources': sorted(e['sources'])} for e in rows]

    # ---- admin summary ----
    def summary(self, days=30):
        since = time.time() - days * 86400
        with self.store.db() as db:
            rows = db.execute('SELECT * FROM feedback WHERE ts>=? ORDER BY id DESC', (since,)).fetchall()
            sig = {r['kind']: r['n'] for r in db.execute('SELECT kind, COUNT(*) n FROM signals WHERE ts>=? GROUP BY kind', (since,))}
        by_kind = {}
        reasons = {}
        labs = {}
        for r in rows:
            k = by_kind.setdefault(r['kind'], {'n': 0, 'up': 0, 'down': 0, 'ratings': [0, 0, 0, 0, 0]})
            k['n'] += 1
            if r['helpful'] is not None:
                k['up' if r['helpful'] else 'down'] += 1
            if r['rating']:
                k['ratings'][r['rating'] - 1] += 1
            for reason in json.loads(r['reasons']):
                reasons.setdefault(r['kind'], {}).setdefault(reason, 0)
                reasons[r['kind']][reason] += 1
            if r['lab_id'] and r['helpful'] is not None:
                lab = labs.setdefault(r['lab_id'], {'up': 0, 'down': 0})
                lab['up' if r['helpful'] else 'down'] += 1
        def lab_name(lid):
            try:
                card = self.catalog.card(lid)
                return f"{', '.join(card['professors'])} · {card['department']}"
            except KeyError:
                return lid
        worst = sorted(labs.items(), key=lambda kv: (-kv[1]['down'], kv[1]['up']))[:10]
        comments = [{'id': r['id'], 'ts': r['ts'], 'kind': r['kind'], 'rating': r['rating'], 'helpful': r['helpful'],
                     'comment': r['comment'], 'lab': lab_name(r['lab_id']) if r['lab_id'] else '', 'query': r['query_text'] or '',
                     'status': r['status']} for r in rows if r['comment']][:100]
        labels = {'result': RESULT_REASONS, 'guide': GUIDE_REASONS}
        return {'days': days, 'by_kind': by_kind, 'signals': sig,
                'reasons': {k: sorted(({'reason': labels.get(k, {}).get(x, x), 'n': n} for x, n in v.items()), key=lambda e: -e['n'])
                            for k, v in reasons.items()},
                'labs_down': [{'lab': lab_name(lid), **v} for lid, v in worst if v['down']], 'comments': comments}

    def set_status(self, feedback_id, status):
        if status not in ('new', 'read', 'done'):
            raise ValueError('상태를 확인해 주세요.')
        with self.store.db() as db:
            db.execute('UPDATE feedback SET status=? WHERE id=?', (status, feedback_id))
        return {'ok': True}
