"""Watching labs: a weekly OpenAlex check for papers by the lab's professors that the catalog has not seen,
then one digest mail per watcher. OpenAlex needs no key; an optional contact address can be configured."""
import json
import threading

from . import errors
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

INTERVAL = 7 * 86400
MAX_WATCHES = 30


class LabWatch:
    def __init__(self, store, catalog, lab_papers, mailer, mailto=None, fetch=None):
        self.store, self.catalog, self.papers, self.mailer = store, catalog, lab_papers, mailer
        self.mailto = mailto
        self.fetch = fetch or self._fetch
        with store.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS watches (
                user_id INTEGER NOT NULL REFERENCES users(id), lab_id TEXT NOT NULL, created REAL NOT NULL,
                PRIMARY KEY(user_id, lab_id));
            CREATE TABLE IF NOT EXISTS watch_papers (
                lab_id TEXT NOT NULL, work_id TEXT NOT NULL, title TEXT NOT NULL, year INTEGER, url TEXT NOT NULL,
                found REAL NOT NULL, PRIMARY KEY(lab_id, work_id));
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')

    def toggle(self, token, body):
        user = self.store.current_user(token)
        lab_id = self.catalog.resolve(body.get('lab_id') if isinstance(body.get('lab_id'), str) else '')
        on = body.get('on')
        if not isinstance(on, bool):
            raise ValueError('지켜보기 여부를 확인해 주세요.')
        with self.store.db() as db:
            if on:
                if db.execute('SELECT COUNT(*) FROM watches WHERE user_id=?', (user['id'],)).fetchone()[0] >= MAX_WATCHES:
                    raise ValueError(f'지켜보기는 {MAX_WATCHES}곳까지 할 수 있어요.')
                db.execute('INSERT OR IGNORE INTO watches(user_id,lab_id,created) VALUES (?,?,?)', (user['id'], lab_id, time.time()))
            else:
                db.execute('DELETE FROM watches WHERE user_id=? AND lab_id=?', (user['id'], lab_id))
        return {'watching': on}

    def state(self, token, lab_id):
        session = self.store.get_session(token)
        with self.store.db() as db:
            watching = bool(session and session['user_id'] and db.execute(
                'SELECT 1 FROM watches WHERE user_id=? AND lab_id=?', (session['user_id'], lab_id)).fetchone())
            recent = [dict(r) for r in db.execute('SELECT title, year, url, found FROM watch_papers WHERE lab_id=? ORDER BY found DESC LIMIT 5', (lab_id,))]
            count = db.execute('SELECT COUNT(*) FROM watches WHERE lab_id=?', (lab_id,)).fetchone()[0]
        return {'watching': watching, 'new_papers': recent, 'watchers': count}

    def _fetch(self, author_ids, since):
        params = {'filter': f'author.id:{"|".join(author_ids)},from_publication_date:{since}', 'sort': 'publication_date:desc',
                  'per-page': 10, 'select': 'id,title,publication_year,doi'}
        if self.mailto:
            params['mailto'] = self.mailto
        with urlopen(Request('https://api.openalex.org/works?' + urlencode(params), headers={'User-Agent': '3mincurri-watch'}), timeout=20) as r:
            return json.load(r).get('results', [])

    def run(self, now=None):
        """Check every watched lab once; returns {lab_id: [new titles]}."""
        now = now or time.time()
        since = time.strftime('%Y-%m-%d', time.gmtime(now - 120 * 86400))
        with self.store.db() as db:
            labs = [r['lab_id'] for r in db.execute('SELECT DISTINCT lab_id FROM watches')]
        found = {}
        for lab_id in labs:
            authors = self.papers.author_ids(lab_id)
            if not authors:
                continue
            try:
                works = self.fetch(authors, since)
            except (OSError, ValueError) as exc:
                print(f'watch fetch failed: {type(exc).__name__}', flush=True)
                errors.record('watch fetch', exc)
                continue
            known = self.papers.known_ids(lab_id)
            with self.store.db() as db:
                for w in works:
                    wid = str(w.get('id', '')).rsplit('/', 1)[-1]
                    if not wid or wid in known or not w.get('title'):
                        continue
                    url = w['doi'] if w.get('doi') else f'https://openalex.org/{wid}'
                    if db.execute('INSERT OR IGNORE INTO watch_papers(lab_id,work_id,title,year,url,found) VALUES (?,?,?,?,?,?)',
                                  (lab_id, wid, w['title'][:300], w.get('publication_year'), url, now)).rowcount:
                        found.setdefault(lab_id, []).append((w['title'], url))
            time.sleep(0.2)
        self._notify(found)
        with self.store.db() as db:
            db.execute("INSERT INTO meta(key,value) VALUES ('watch_last_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(now),))
        return {lab: [t for t, _ in items] for lab, items in found.items()}

    def _notify(self, found):
        if not found:
            return
        with self.store.db() as db:
            rows = db.execute(f'''SELECT u.id, u.email, u.notify, w.lab_id FROM watches w JOIN users u ON u.id=w.user_id
                                  WHERE u.deleted=0 AND u.dummy=0 AND u.email_verified=1 AND w.lab_id IN ({",".join("?" * len(found))})''',
                              list(found)).fetchall()
        per_user = {}
        for r in rows:
            if json.loads(r['notify'] or '{}').get('watch', True):
                per_user.setdefault((r['id'], r['email']), []).append(r['lab_id'])
        for (uid, email), labs in per_user.items():
            lines = []
            for lab_id in labs:
                card = self.catalog.card(lab_id)
                lines.append(f"■ {', '.join(card['professors'])} 연구실 ({card['department']})")
                lines += [f'  - {title}\n    {url}' for title, url in found[lab_id][:5]]
                lines.append(f'  연구실 보기: {self.mailer.link("/lab/" + lab_id)}')
            self.mailer.send(email, '[3분커리] 지켜보는 연구실의 새 논문', '\n'.join(lines), 'watch', uid)

    def start(self):
        def loop():
            while True:
                try:
                    with self.store.db() as db:
                        row = db.execute("SELECT value FROM meta WHERE key='watch_last_run'").fetchone()
                    if not row or time.time() - float(row['value']) >= INTERVAL:
                        self.run()
                except Exception as exc:
                    print(f'watch loop error: {type(exc).__name__}', flush=True)
                    errors.record('lab-watch', exc)
                time.sleep(3600)
        threading.Thread(target=loop, daemon=True, name='lab-watch').start()
