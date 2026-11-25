"""Review which papers really belong to each lab's professor, and keep every reviewed decision applied downstream.

OpenAlex groups works into author profiles by name, so a common name ends up with other people's papers (casebook
D-10, D-16 to D-23). A profile is therefore not evidence for a paper: each professor-paper pair needs its own. The
flow is the one used for the 박성우 and 최영준 records (docs/analysis/PAPER_ATTRIBUTION_REVIEW.md):

  audit     offline. Rank labs by how many of the papers the service shows have no paper-level identity evidence.
  evidence  online.  For one lab, print what each paper's own record says about the author (affiliation, ORCID),
                     what the author profile is made of, and school-list titles that are missing from the selection.
  apply     Write the reviewed decisions of one lab (curation/lab_overrides.json: paper_exclusions, paper_allowlist,
                     openalex_author_ids) into labs.jsonl, papers.jsonl, app_profiles.jsonl and the course links.
  check     offline. Fail when a recorded decision is missing anywhere the service reads it.
  stamp     Refresh the file hashes in IMPORT_MANIFEST.json after a reviewed edit.

    python3 tools/paper_attribution.py audit [--write]
    python3 tools/paper_attribution.py evidence LAB_ID
    python3 tools/paper_attribution.py apply LAB_ID [--offline]
    python3 tools/paper_attribution.py check

The tool never decides that a paper is someone else's. A person (or an agent with sources) writes the decision with
its evidence into lab_overrides.json; `apply` and `check` only carry it through. OpenAlex and Crossref are read without
a key; responses are cached in .local/paper_attribution/ (not committed). Standard library only.
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'sunwoo'
CACHE = ROOT / '.local' / 'paper_attribution'
POSTECH_ROR = '04xysgw12'
OPENALEX = 'https://api.openalex.org/'
SELECT = ('id,doi,title,publication_year,publication_date,type,authorships,abstract_inverted_index,primary_topic,'
          'fwci,cited_by_count,primary_location,is_retracted')
KEEP_TYPES = {'article', 'conference-paper', 'review', 'preprint', 'letter', 'book-chapter'}
SINCE, RECENT, MIN_LAB_LED, CITE_KEY = 2018, 2024, 5, 30
STOP = set('and the for with from into of in on to a an by its their via based using toward towards study studies '
           'research lab laboratory group system systems application applications approach approaches new novel '
           'advanced design analysis development method methods technology technologies'.split())
AUDIT_FILE = 'curation/paper_attribution_audit.json'
TIERS = {1: '먼저 확인: 보여 주는 논문 중 본인 확인된 것이 없음', 2: '확인 필요: 절반 이상이 미확인',
         3: '일부 미확인', 0: '미확인 없음'}

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_curated_profiles  # noqa: E402


# ---- small helpers ----
def key(title):
    """A title as lowercase letters and digits only: the school list drops hyphens and symbols (casebook D-11)."""
    return re.sub(r'[^a-z0-9]', '', re.sub(r'<[^>]+>', '', title or '').lower())


def person(name):
    return re.sub(r'[^a-z]', '', (name or '').lower())


def short(value):
    return str(value or '').rsplit('/', 1)[-1]


def norm_doi(value):
    return re.sub(r'^https?://doi\.org/', '', value or '', flags=re.I).lower()


def stems(text):
    return {w[:6] for w in re.findall(r'[a-z]{4,}', (text or '').lower()) if w not in STOP}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dumps_line(obj):
    return json.dumps(obj, ensure_ascii=False) + '\n'


def write_atomic(path, text):
    """Replace a file in one step so a failed run leaves the old content."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def fetch_json(url, tries=3):
    """Public bibliographic lookups only; no key and no contact address is sent."""
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'curri-paper-attribution/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == tries - 1:
                raise
        except (OSError, ValueError):
            if attempt == tries - 1:
                raise
        time.sleep(1 + attempt)
    return None


class Data:
    """The curated files of one data folder, read on demand. JSONL files keep their lines so that a single record can
    be replaced without touching the bytes of the others."""

    def __init__(self, root=DATA):
        self.root = Path(root)
        self._cache = {}

    def _load(self, name, loader):
        if name not in self._cache:
            self._cache[name] = loader(self.root / name)
        return self._cache[name]

    @staticmethod
    def _lines(path):
        return [(line, json.loads(line)) for line in path.read_text(encoding='utf-8').splitlines(keepends=True) if line.strip()]

    @staticmethod
    def _json(path):
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    @property
    def lab_lines(self):
        return self._load('labs.jsonl', self._lines)

    @property
    def paper_lines(self):
        return self._load('papers.jsonl', self._lines)

    @property
    def profile_lines(self):
        return self._load('app_profiles.jsonl', self._lines)

    @property
    def labs(self):
        return {row['id']: row for _, row in self.lab_lines}

    @property
    def bundles(self):
        return {row['id']: row for _, row in self.paper_lines}

    @property
    def profiles(self):
        return {row['lab_id']: row for _, row in self.profile_lines}

    @property
    def overrides(self):
        return self._load('curation/lab_overrides.json', self._json)

    @property
    def suspect(self):
        return self._load('suspect_papers.json', self._json).get('labs', {})

    @property
    def mapping(self):
        return self._load('lab_course_bge_m3.json', self._json)

    @property
    def manifest(self):
        return self._load('IMPORT_MANIFEST.json', self._json)

    @property
    def identity(self):
        """{lab_id: {work_id: status}} from the pair-by-pair check of 2026-10-27 (rules identity-v1). `confirmed` needs
        the school's own publication list or the paper's own ORCID; a profile or an affiliation alone stays `held`."""
        def load(path):
            out = {}
            if path.exists():
                with path.open(encoding='utf-8') as stream:
                    for line in stream:
                        row = json.loads(line)
                        if 'work_id' in row:
                            out.setdefault(row['lab_id'], {})[row['work_id']] = row['status']
            return out
        return self._load('curation/paper_identity.jsonl', load)

    @property
    def school_list(self):
        """{lab_id: [list entry]}: the publication list the school keeps per professor (independent of OpenAlex)."""
        def load(path):
            out = {}
            if path.exists():
                with path.open(encoding='utf-8') as stream:
                    for line in stream:
                        row = json.loads(line)
                        out[row.get('advisor_id')] = row.get('professor_papers') or []
            return out
        return self._load('final_labs.jsonl', load)


# ---- decisions: what a reviewer may record, and how strictly ----
def decision_errors(lab_id, override):
    """Problems in one lab's recorded paper decisions. An exclusion without its reason and sources is refused: it must
    stay checkable by the next reviewer."""
    errors = []
    seen_ids, seen_dois = set(), set()
    for e in override.get('paper_exclusions') or []:
        label = f"{lab_id} exclusion {e.get('openalex_id')}"
        if e.get('severity') != 'P0' or not all(isinstance(e.get(k), str) and e[k] for k in ('openalex_id', 'doi', 'title', 'reason', 'checked_at')):
            errors.append(f'{label}: needs openalex_id, doi, title, reason, checked_at and severity P0')
            continue
        if not re.fullmatch(r'W\d+', e['openalex_id']) or not re.fullmatch(r'10\.\d{4,9}/\S+', e['doi']):
            errors.append(f'{label}: invalid work id or DOI')
        sources = e.get('sources')
        if not isinstance(sources, list) or not sources or not all(isinstance(u, str) and u.startswith('https://') for u in sources):
            errors.append(f'{label}: needs https sources')
        aliases = e.get('aliases', [])
        if not isinstance(aliases, list) or any(not isinstance(a, dict) or not re.fullmatch(r'W\d+', str(a.get('openalex_id'))) or
                                                not re.fullmatch(r'10\.\d{4,9}/\S+', str(a.get('doi'))) for a in aliases):
            errors.append(f'{label}: invalid aliases')
            aliases = []
        ids = {e['openalex_id']} | {a['openalex_id'] for a in aliases}
        dois = {norm_doi(e['doi'])} | {norm_doi(a['doi']) for a in aliases}
        if ids & seen_ids or dois & seen_dois:
            errors.append(f'{label}: listed twice')
        seen_ids |= ids
        seen_dois |= dois
    policy = override.get('paper_allowlist')
    if policy is not None:
        works = policy.get('works') or []
        if not works or len({w.get('openalex_id') for w in works}) != len(works):
            errors.append(f'{lab_id} allowlist: empty or repeated works')
        if 'orcid' not in policy or not policy.get('checked_at') or not policy.get('scope'):
            errors.append(f'{lab_id} allowlist: needs orcid (may be null), checked_at and scope')
        for w in works:
            label = f"{lab_id} allowlist {w.get('openalex_id')}"
            if not all(isinstance(w.get(k), str) and w[k] for k in ('openalex_id', 'doi', 'title', 'author_name', 'source')):
                errors.append(f'{label}: needs openalex_id, doi, title, author_name and source')
                continue
            if not w['source'].startswith('https://'):
                errors.append(f'{label}: source must be an https address')
            if w['openalex_id'] in seen_ids or norm_doi(w['doi']) in seen_dois:
                errors.append(f'{label}: also excluded')
    return errors


def excluded_keys(override):
    ids, dois, titles = set(), set(), set()
    for e in override.get('paper_exclusions') or []:
        ids.add(e['openalex_id'])
        dois.add(norm_doi(e['doi']))
        titles.add(key(e['title']))
        for a in e.get('aliases') or []:
            ids.add(a['openalex_id'])
            dois.add(norm_doi(a['doi']))
    return ids, dois, titles


def is_excluded(paper, ids, dois):
    return bool(ids & {paper.get('openalex_id'), *(paper.get('versions') or [])}) or norm_doi(paper.get('doi')) in dois


# ---- audit: where to look first ----
def evidence_class(paper, statuses, have_identity):
    """reviewed: a person checked this pair against an official source. confirmed: the 2026-10-27 pair check found the
    school list or the paper's own ORCID. unverified: only the author profile, an affiliation or a title mention ties
    the paper to the professor, which is exactly how namesake papers got in."""
    if paper.get('ownership_verification'):
        return 'reviewed'
    if 'confirmed' in {statuses.get(i) for i in (paper.get('openalex_id'), *(paper.get('versions') or []))}:
        return 'confirmed'
    if not have_identity and paper.get('in_list'):
        return 'confirmed'  # without the pair check file, the school-list title match is the closest evidence
    return 'unverified'


def audit(data):
    have_identity = bool(data.identity)
    rows = []
    for lab_id, lab in data.labs.items():
        if not lab.get('recommendable'):
            continue
        bundle = data.bundles.get(lab_id) or {}
        papers = bundle.get('papers') or []
        classes = [evidence_class(p, data.identity.get(lab_id, {}), have_identity) for p in papers]
        unverified = [p for p, c in zip(papers, classes) if c == 'unverified']
        verified = [p for p, c in zip(papers, classes) if c != 'unverified']
        fields = {p.get('subfield') for p in verified}
        off_field = [p for p in unverified if p.get('subfield') not in fields] if verified else []
        profiles = (lab.get('openalex') or {}).get('profiles') or []
        hints = []
        if any(p.get('flag') in ('strong', 'weak') for p in profiles):
            hints.append('profile_flagged')        # the affiliation check saw a merged-looking profile (D-10)
        if any(p.get('verdict') != 'confirmed' for p in profiles):
            hints.append('no_list_match')          # the school list could not confirm the profile (D-11, D-15)
        if data.suspect.get(lab_id):
            hints.append('suspect_papers')         # tools/build_suspect_papers.py flagged far-off papers
        if bundle.get('basis') == 'unverified_after_exclusions':
            hints.append('after_exclusions')       # some papers were removed; the rest was never confirmed (D-18)
        if bundle.get('author_ids') and unverified and 2 * len(unverified) >= len(papers):
            hints.append('feed_follows_profile')   # the weekly new-paper check follows this profile (D-21)
        if not verified and len(unverified) >= 3:
            tier = 1
        elif len(unverified) >= 3 and 2 * len(unverified) >= len(papers):
            tier = 2
        else:
            tier = 3 if unverified else 0
        rows.append({'lab_id': lab_id, 'professor': bundle.get('professor') or lab['professor'].get('name_ko'),
                     'department': ' · '.join(lab['professor'].get('departments') or []), 'tier': tier,
                     'papers': len(papers), 'reviewed': classes.count('reviewed'), 'confirmed': classes.count('confirmed'),
                     'unverified': len(unverified), 'off_field': len(off_field), 'hints': hints,
                     'unverified_ids': [p['openalex_id'] for p in unverified]})
    rows.sort(key=lambda r: (r['tier'] or 9, -len(r['hints']), -r['unverified'], r['lab_id']))
    return rows


def audit_report(data):
    rows = audit(data)
    totals = Counter()
    for r in rows:
        totals.update(reviewed=r['reviewed'], confirmed=r['confirmed'], unverified=r['unverified'], papers=r['papers'])
    return {'_about': 'Review queue of tools/paper_attribution.py audit. A tier is where to look first, not a verdict.',
            'rules': 'paper-attribution-v1', 'tiers': {str(k): v for k, v in TIERS.items()},
            'labs': len(rows), 'papers': dict(totals), 'by_tier': {str(t): sum(r['tier'] == t for r in rows) for t in (1, 2, 3, 0)},
            'queue': [r for r in rows if r['tier'] in (1, 2)]}


def print_audit(report):
    p = report['papers']
    print(f"연구실 {report['labs']}곳 · 보여 주는 논문 {p.get('papers', 0)}편: 사람 검토 {p.get('reviewed', 0)}, "
          f"목록·ORCID 확인 {p.get('confirmed', 0)}, 미확인 {p.get('unverified', 0)}")
    for tier in ('1', '2', '3', '0'):
        print(f"  {tier}단계 {report['by_tier'][tier]:>3}곳  {report['tiers'][tier]}")
    print('\n단계 교수(학과)                      논문 검토 확인 미확인 분야밖  신호')
    for r in report['queue']:
        name = f"{r['professor']}({r['department']})"
        print(f"  {r['tier']}  {name:<28.28} {r['papers']:>3} {r['reviewed']:>4} {r['confirmed']:>4} {r['unverified']:>5} {r['off_field']:>5}  "
              f"{', '.join(r['hints'])}  {r['lab_id']}")


# ---- evidence: what the paper's own record says ----
def get_works(ids, fetch, cache, offline=False):
    """OpenAlex works by id, from the local cache first."""
    cache = Path(cache) / 'works'
    cache.mkdir(parents=True, exist_ok=True)
    out, missing = {}, []
    for wid in ids:
        path = cache / f'{wid}.json'
        if path.exists():
            out[wid] = json.loads(path.read_text(encoding='utf-8'))
        else:
            missing.append(wid)
    if missing and offline:
        raise ValueError(f'캐시에 없는 논문: {missing} (네트워크 없이 실행할 수 없음)')
    for i in range(0, len(missing), 40):
        part = missing[i:i + 40]
        url = OPENALEX + 'works?' + urllib.parse.urlencode({'filter': 'openalex:' + '|'.join(part), 'per_page': 50, 'select': SELECT + ',locations_count'})
        for w in (fetch(url) or {}).get('results') or []:
            wid = short(w['id'])
            (cache / f'{wid}.json').write_text(json.dumps(w, ensure_ascii=False), encoding='utf-8')
            out[wid] = w
    return out


def find_author(work, author_ids=(), names=()):
    """The authorships that could be the professor: by profile id, else by the name written on the paper."""
    authorships = work.get('authorships') or []
    by_id = [a for a in authorships if short((a.get('author') or {}).get('id')) in set(author_ids)]
    if by_id:
        return by_id
    wanted = {person(n) for n in names if n}
    return [a for a in authorships if person(a.get('raw_author_name') or (a.get('author') or {}).get('display_name')) in wanted]


def stated(authorship):
    institutions = authorship.get('institutions') or []
    return {'name': authorship.get('raw_author_name') or (authorship.get('author') or {}).get('display_name'),
            'author_id': short((authorship.get('author') or {}).get('id')) or None,
            'profile_orcid': short((authorship.get('author') or {}).get('orcid')) or None,
            'institutions': [i.get('display_name') for i in institutions],
            'raw_affiliations': (authorship.get('raw_affiliation_strings') or [])[:2],
            'postech': any((i.get('ror') or '').endswith(POSTECH_ROR) for i in institutions)}


def crossref_author(doi, names, fetch):
    """What the publisher registered for this author: the paper's own ORCID and affiliation, when deposited."""
    if not doi:
        return None
    try:
        message = (fetch('https://api.crossref.org/works/' + urllib.parse.quote(doi)) or {}).get('message') or {}
    except (OSError, ValueError):
        return None
    wanted = {person(n) for n in names if n}
    for a in message.get('author') or []:
        if person(f"{a.get('given', '')}{a.get('family', '')}") in wanted or person(f"{a.get('family', '')}{a.get('given', '')}") in wanted:
            return {'orcid': short(a.get('ORCID')) or None, 'affiliations': [x.get('name') for x in a.get('affiliation') or []]}
    return None


def evidence(data, lab_id, fetch=fetch_json, cache=CACHE, with_crossref=True, title_searches=8):
    lab, bundle = data.labs[lab_id], data.bundles.get(lab_id) or {}
    oa = lab.get('openalex') or {}
    reviewed = (oa.get('paper_allowlist') or {}).get('works') or []
    profile_ids = list(dict.fromkeys([*(bundle.get('author_ids') or []), *(oa.get('author_ids') or []), *(oa.get('raw_author_ids') or [])]))
    # A reviewed paper may sit under a different profile or none (D-16, D-20), so its recorded author is looked for too.
    author_ids = list(dict.fromkeys([*profile_ids, *(w['author_id'] for w in reviewed if w.get('author_id'))]))
    names = list(dict.fromkeys([lab['professor'].get('name_en'), *(w.get('author_name') for w in reviewed)]))
    papers = bundle.get('papers') or []
    works = get_works([p['openalex_id'] for p in papers], fetch, cache)
    statuses, rows = data.identity.get(lab_id, {}), []
    for p in papers:
        w = works.get(p['openalex_id'])
        mine = find_author(w, author_ids, names) if w else []
        rows.append({'openalex_id': p['openalex_id'], 'year': p.get('year'), 'title': p['title'], 'subfield': p.get('subfield'),
                     'evidence': evidence_class(p, statuses, bool(data.identity)),
                     'stated': [stated(a) for a in mine],
                     'crossref': crossref_author(p.get('doi'), [*names, *(a.get('raw_author_name') for a in mine)], fetch) if with_crossref else None})
    profiles = []
    for aid in profile_ids:
        url = OPENALEX + 'works?' + urllib.parse.urlencode({'filter': f'author.id:{aid},from_publication_date:{SINCE}-01-01', 'per_page': 200,
                                                           'select': 'id,authorships,primary_topic'})
        result = fetch(url) or {}
        institutions, fields = Counter(), Counter()
        for w in result.get('results') or []:
            fields[((w.get('primary_topic') or {}).get('field') or {}).get('display_name') or '(없음)'] += 1
            for a in w.get('authorships') or []:
                if short((a.get('author') or {}).get('id')) == aid:
                    for i in a.get('institutions') or [{'display_name': '(소속 없음)'}]:
                        institutions[i.get('display_name')] += 1
        profiles.append({'author_id': aid, 'works_since_2018': (result.get('meta') or {}).get('count'),
                         'institutions': len(institutions), 'top_institutions': institutions.most_common(8), 'fields': fields.most_common(6)})
    # School-list titles that the selection does not have: the professor's papers may sit outside every profile (D-20).
    selected = {key(p['title']) for p in papers}
    listed = sorted((e for e in data.school_list.get(lab_id) or [] if (e.get('year') or 0) >= SINCE and key(e.get('title')) not in selected
                     and len(re.findall(r'[A-Za-z]{2,}', e.get('title') or '')) >= 4), key=lambda e: -(e.get('year') or 0))
    candidates, seen = [], set()
    for entry in listed:
        k = key(entry['title'])
        if k in seen or len(seen) >= title_searches:
            continue
        seen.add(k)
        url = OPENALEX + 'works?' + urllib.parse.urlencode({'filter': 'title.search:' + re.sub(r'[^\w\s]', ' ', entry['title']), 'per_page': 5, 'select': SELECT})
        for w in (fetch(url) or {}).get('results') or []:
            if key(w.get('title')) == k:
                mine = find_author(w, author_ids, names)
                candidates.append({'openalex_id': short(w['id']), 'doi': norm_doi(w.get('doi')) or None, 'year': w.get('publication_year'),
                                   'title': w['title'], 'type': w.get('type'), 'stated': [stated(a) for a in mine]})
    report = {'lab_id': lab_id, 'professor': lab['professor'], 'author_ids': profile_ids, 'papers': rows, 'profiles': profiles,
              'school_list_candidates': candidates, 'fetched': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    Path(cache).mkdir(parents=True, exist_ok=True)
    (Path(cache) / f'{re.sub(r"[^A-Za-z0-9_.-]", "_", lab_id)}.evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    return report


def print_evidence(report):
    prof = report['professor']
    print(f"{prof.get('name_ko')} ({prof.get('name_en')}) · {' · '.join(prof.get('departments') or [])} · 저자 프로필 {report['author_ids']}")
    for p in report['profiles']:
        print(f"  프로필 {p['author_id']}: 2018년 이후 {p['works_since_2018']}편, 소속 기관 {p['institutions']}곳 "
              f"{[f'{n} {c}' for n, c in p['top_institutions'][:5]]} · 분야 {[f'{n} {c}' for n, c in p['fields'][:4]]}")
    print('\n지금 보여 주는 논문: 논문에 적힌 저자 소속')
    for r in report['papers']:
        where = '; '.join(', '.join(s['institutions']) or (s['raw_affiliations'] or ['(소속 없음)'])[0] for s in r['stated']) or '(저자를 찾지 못함)'
        cross = r.get('crossref') or {}
        extra = f" | Crossref ORCID {cross.get('orcid')} 소속 {cross.get('affiliations')}" if cross else ''
        mark = 'POSTECH' if any(s['postech'] for s in r['stated']) else '다른 곳' if r['stated'] else '확인 못 함'
        print(f"  [{r['evidence']:<10}] {r['year']} {r['openalex_id']} {r['title'][:60]}\n               {mark}: {where}{extra}")
    if report['school_list_candidates']:
        print('\n학교 목록에 있지만 선정에 없는 논문 (OpenAlex 제목 검색)')
        for c in report['school_list_candidates']:
            where = '; '.join(f"{s['name']} · {', '.join(s['institutions'])} · 프로필 {s['author_id']}" for s in c['stated']) or '(이름이 맞는 저자 없음)'
            print(f"  {c['year']} {c['openalex_id']} {c['doi']} {c['title'][:60]}\n               {where}")


# ---- apply: carry one lab's decisions through every file ----
def abstract_text(inverted):
    if not inverted:
        return None
    return ' '.join(word for _, word in sorted((p, word) for word, places in inverted.items() for p in places)) or None


def describe(work, mine, listed, intro_key):
    """One OpenAlex work as a paper record, in the field order papers.jsonl already uses."""
    topic = work.get('primary_topic') or {}
    source = (work.get('primary_location') or {}).get('source') or {}
    k = key(work['title'])
    abstract = abstract_text(work.get('abstract_inverted_index'))
    me = mine[0]
    corresponding = any(a.get('is_corresponding') for a in mine)
    return {'openalex_id': short(work['id']), 'doi': norm_doi(work.get('doi')) or None,
            'title': html.unescape(re.sub(r'<[^>]+>', '', work['title'])).strip(),
            'year': work.get('publication_year'), 'date': work.get('publication_date'),
            'venue': source.get('display_name'), 'source_type': source.get('type'),
            'publisher': (source.get('host_organization_lineage_names') or [None])[-1], 'type': work.get('type'),
            'topic': topic.get('display_name'), 'subfield': (topic.get('subfield') or {}).get('display_name'),
            'fwci': work.get('fwci'), 'cited_by_count': work.get('cited_by_count') or 0,
            'authors_count': len(work.get('authorships') or []), 'author_position': me.get('author_position'),
            'is_corresponding': corresponding, 'lab_led': me.get('author_position') == 'last' or corresponding,
            'in_list': k in listed,
            'postech_affiliation': any((i.get('ror') or '').endswith(POSTECH_ROR) for a in mine for i in a.get('institutions') or []),
            'cited_on_site': len(k) >= CITE_KEY and k in intro_key,
            'abstract': abstract, 'abstract_source': 'openalex' if abstract else None, 'versions': [], 'reasons': []}


def allowlisted_bundle(lab, old_bundle, policy, works, school_entries):
    """The paper bundle of a lab whose papers a person listed one by one (D-16). Each work must still be the record
    that was reviewed: a changed DOI, title or author stops the run before anything is written."""
    listed = {key(e.get('title')) for e in school_entries or []}
    intro_key = key(((lab.get('intro') or {}).get('text')) or '')
    papers = []
    for entry in policy['works']:
        wid = entry['openalex_id']
        work = works.get(wid)
        if not work:
            raise ValueError(f'{wid}: OpenAlex에서 논문을 받지 못함')
        if norm_doi(work.get('doi')) != norm_doi(entry['doi']):
            raise ValueError(f'{wid}: DOI가 검토 때와 다름')
        if key(work.get('title')) != key(entry['title']):
            raise ValueError(f'{wid}: 제목이 검토 때와 다름')
        if work.get('is_retracted') or work.get('type') not in KEEP_TYPES:
            raise ValueError(f'{wid}: 더 이상 쓸 수 있는 논문 유형이 아님')
        mine = find_author(work, [entry['author_id']] if entry.get('author_id') else [], [entry['author_name']])
        if len(mine) != 1 or person(mine[0].get('raw_author_name') or mine[0]['author'].get('display_name')) != person(entry['author_name']):
            raise ValueError(f'{wid}: 검토한 저자({entry["author_name"]})를 논문에서 하나로 찾지 못함')
        observed = short(mine[0]['author'].get('orcid')) or None
        if 'observed_orcid' in entry and observed != entry['observed_orcid']:
            raise ValueError(f'{wid}: 저자에 붙은 ORCID가 검토 때와 다름')
        paper = describe(work, mine, listed, intro_key)
        paper['versions'] = list(entry.get('versions') or [])
        if not paper['abstract']:
            for other in paper['versions']:
                text = abstract_text((works.get(other) or {}).get('abstract_inverted_index'))
                if text:
                    paper['abstract'], paper['abstract_source'] = text, 'openalex_other_version'
                    break
        paper['reasons'] = ['verified'] + (['recent'] if (paper['year'] or 0) >= RECENT else [])
        paper['ownership_verification'] = {
            'basis': entry.get('basis') or 'official_publication_list', 'source': entry['source'], 'checked_at': policy['checked_at'],
            'author_id': entry.get('author_id'), 'orcid': policy.get('orcid'), 'observed_orcid': observed,
            'orcid_status': 'missing' if not observed or not policy.get('orcid') else 'match' if observed == policy['orcid'] else 'conflict'}
        papers.append(paper)
    papers.sort(key=lambda p: (-(p['year'] or 0), p['openalex_id']))
    window = [p for p in papers if (p['year'] or 0) >= SINCE]
    led = [p for p in window if p['lab_led']]
    pool = led if len(led) >= MIN_LAB_LED else window
    core = [t for t, n in Counter(p['topic'] for p in pool if p['topic']).most_common(4) if n >= 3 or (n >= 2 and n >= 0.1 * len(pool))]
    matched = []
    for area in lab.get('research_areas') or []:
        name = area.get('name_en') or area.get('name') or ''
        words = stems(name) if area.get('kind') == 'area' and not re.search(r'[가-힣]', name) else set()
        texts = [(p['title'] + ' ' + (p['abstract'] or '')).lower() for p in papers]
        if len(words) == 1:  # one word must appear whole: the 6-letter stem of "Differentiation" also meets "different"
            hit = any(re.search(rf'\b{re.escape(name.lower())}\b', t) for t in texts)
        else:
            hit = bool(words) and any(len(words & stems(t)) >= 2 for t in texts)
        if hit:
            matched.append(name)
    return {**old_bundle, 'id': lab['id'], 'professor': lab['professor'].get('name_ko'), 'basis': 'official_allowlist',
            'core_topics': core, 'areas_matched': matched,
            'counts': {'works_since_2018': len(window), 'own': len(papers), 'own_by': {'official_allowlist': len(papers)},
                       'window': len(window), 'lab_led': len(led)},
            'papers': papers}


def subtract(bundle, override):
    """Remove confirmed misattributions and nothing else: no ranking, no refill (D-18)."""
    ids, dois, _ = excluded_keys(override)
    kept = []
    for p in bundle.get('papers') or []:
        if ids & {p.get('openalex_id'), *(p.get('versions') or [])} and norm_doi(p.get('doi')) not in dois:
            raise ValueError(f"{p.get('openalex_id')}: 제외한 논문의 DOI가 달라짐. 다시 검토해야 함")
        if not is_excluded(p, ids, dois):
            kept.append(p)
    out = {**bundle, 'papers': kept}
    if (ids or dois) and any(not p.get('ownership_verification') for p in kept):
        out['basis'] = 'unverified_after_exclusions'  # what is left was never confirmed paper by paper
    return out


def replace_line(lines, match, new_obj):
    done, out = False, []
    for line, row in lines:
        if match(row):
            out.append(dumps_line(new_obj))
            done = True
        else:
            out.append(line)
    if not done:
        raise ValueError('바꿀 기록을 찾지 못함')
    return ''.join(out)


def apply(data, lab_id, fetch=fetch_json, cache=CACHE, offline=False, today=None):
    override = data.overrides.get(lab_id)
    lab = data.labs.get(lab_id)
    if not lab or not lab.get('recommendable') or lab_id not in data.bundles:
        raise ValueError('추천 가능한 연구실의 기록이 아님')
    if not override or not any(k in override for k in ('paper_exclusions', 'paper_allowlist', 'openalex_author_ids')):
        raise ValueError('lab_overrides.json에 이 연구실의 논문 판정이 없음')
    errors = decision_errors(lab_id, override)
    if errors:
        raise ValueError('판정 기록 오류: ' + '; '.join(errors))
    # 1. labs.jsonl carries the decisions next to the profile check they correct
    lab = json.loads(json.dumps(lab))
    oa = lab.setdefault('openalex', {})
    if 'openalex_author_ids' in override:
        new_ids = list(override['openalex_author_ids'])
        dropped = [i for i in oa.get('author_ids') or [] if i not in new_ids]
        # raw_author_ids is every profile ever picked for this record; a dropped one stays there as history (D-16)
        oa['raw_author_ids'] = list(dict.fromkeys([*(oa.get('raw_author_ids') or []), *dropped]))
        known = {p['id']: p for p in oa.get('profiles') or []}
        oa['profiles'] = [known.get(i) or {'id': i, 'works_count': None, 'postech_works': None, 'flag': None, 'reasons': [],
                                           'listed_hits': None, 'verdict': None} for i in new_ids]
        oa['author_ids'] = new_ids
        oa['status'] = 'corrected'
    for name in ('paper_exclusions', 'paper_allowlist'):
        if name in override:
            oa[name] = override[name]
    # 2. papers.jsonl
    bundle = dict(data.bundles[lab_id])
    bundle['author_ids'] = sorted(oa.get('author_ids') or [])
    policy = override.get('paper_allowlist')
    if policy is not None:
        ids = [w['openalex_id'] for w in policy['works']] + [v for w in policy['works'] for v in w.get('versions') or []]
        bundle = allowlisted_bundle(lab, bundle, policy, get_works(ids, fetch, cache, offline), data.school_list.get(lab_id))
    bundle = subtract(bundle, override)
    # 3. the app profile of this lab only; every other line keeps its bytes
    profile = build_curated_profiles.profile(lab, bundle)
    new_labs = replace_line(data.lab_lines, lambda r: r['id'] == lab_id, lab)
    new_papers = replace_line(data.paper_lines, lambda r: r['id'] == lab_id, bundle)
    new_profiles = replace_line(data.profile_lines, lambda r: r['lab_id'] == lab_id, profile)
    profile_changed = dumps_line(profile) != next(line for line, row in data.profile_lines if row['lab_id'] == lab_id)
    # 4. course links were computed from the old profile text: drop this lab's and say so, keep the others (their input is unchanged)
    mapping = json.loads(json.dumps(data.mapping)) if data.mapping else None
    if mapping is not None:
        migration = mapping.setdefault('migration', {})
        if profile_changed:
            mapping.get('labs', {}).pop(lab_id, None)
            migration['requires_recompute'] = sorted(set(migration.get('requires_recompute') or []) | {lab_id})
            (migration.get('retained_profile_sha256') or {}).pop(lab_id, None)
        mapping.setdefault('sources', {})['app_profiles.jsonl'] = hashlib.sha256(new_profiles.encode('utf-8')).hexdigest()
    write_atomic(data.root / 'labs.jsonl', new_labs)
    write_atomic(data.root / 'papers.jsonl', new_papers)
    write_atomic(data.root / 'app_profiles.jsonl', new_profiles)
    if mapping is not None:
        write_atomic(data.root / 'lab_course_bge_m3.json', json.dumps(mapping, ensure_ascii=False) + '\n')
    fresh = Data(data.root)
    stamp(fresh, [lab_id], today)
    return {'lab_id': lab_id, 'papers': len(bundle['papers']), 'basis': bundle.get('basis'), 'profile_changed': profile_changed}


def stamp(data, lab_ids=(), today=None):
    """Record the current hashes of files that no longer equal the imported snapshot, and of the derived files."""
    manifest = data.manifest
    if not manifest:
        return None
    manifest = json.loads(json.dumps(manifest))
    corrected = []
    for entry in manifest.get('files') or []:
        path = data.root / entry['path']
        if sha(path) != entry['sha256']:
            corrected.append({'path': entry['path'], 'bytes': path.stat().st_size, 'sha256': sha(path)})
    manifest['corrected_files'] = corrected
    for entry in manifest.get('derived_files') or []:
        entry['sha256'] = sha(data.root / entry['path'])
    if lab_ids:
        manifest['changed_lab_ids'] = sorted(set(manifest.get('changed_lab_ids') or []) | set(lab_ids))
        log = manifest.setdefault('corrections', [])
        day = today or time.strftime('%Y-%m-%d')
        entry = next((c for c in log if c['date'] == day and c.get('tool') == 'tools/paper_attribution.py apply'), None)
        if entry is None:
            entry = {'date': day, 'tool': 'tools/paper_attribution.py apply', 'lab_ids': []}
            log.append(entry)
        entry['lab_ids'] = sorted(set(entry['lab_ids']) | set(lab_ids))
    write_atomic(data.root / 'IMPORT_MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


# ---- check: is every decision still in force? ----
def check(data):
    problems = []
    labs, bundles, profiles = data.labs, data.bundles, data.profiles
    for lab_id, override in data.overrides.items():
        if not any(k in override for k in ('paper_exclusions', 'paper_allowlist')):
            continue
        problems += decision_errors(lab_id, override)
        lab, bundle = labs.get(lab_id), bundles.get(lab_id) or {}
        if not lab:
            problems.append(f'{lab_id}: 판정은 있는데 labs.jsonl에 기록이 없음')
            continue
        name = lab['professor'].get('name_ko') or lab_id
        oa = lab.get('openalex') or {}
        for field in ('paper_exclusions', 'paper_allowlist'):
            if override.get(field) != oa.get(field):
                problems.append(f'{name}: labs.jsonl의 {field}가 lab_overrides.json과 다름 (apply 필요)')
        if 'openalex_author_ids' in override and sorted(override['openalex_author_ids']) != sorted(oa.get('author_ids') or []):
            problems.append(f'{name}: labs.jsonl의 author_ids가 판정과 다름 (apply 필요)')
        if sorted(bundle.get('author_ids') or []) != sorted(oa.get('author_ids') or []):
            problems.append(f'{name}: papers.jsonl의 author_ids가 labs.jsonl과 다름. 새 논문 알림이 이 프로필을 따라간다')
        try:
            ids, dois, titles = excluded_keys(override)
        except (KeyError, TypeError):
            continue  # already reported by decision_errors
        papers = bundle.get('papers') or []
        for p in papers:
            if is_excluded(p, ids, dois):
                problems.append(f"{name}: 제외한 논문 {p.get('openalex_id')}이 papers.jsonl에 남아 있음")
        policy = override.get('paper_allowlist')
        if policy is not None:
            allowed = {w['openalex_id'] for w in policy.get('works') or []}
            for p in papers:
                if p.get('openalex_id') not in allowed or not p.get('ownership_verification'):
                    problems.append(f"{name}: 허용 목록 밖이거나 검토 기록이 없는 논문 {p.get('openalex_id')}")
            missing = allowed - {p.get('openalex_id') for p in papers}
            if missing:
                problems.append(f'{name}: 허용 목록 논문이 papers.jsonl에 없음 {sorted(missing)}')
        elif ids and papers and bundle.get('basis') != 'unverified_after_exclusions':
            problems.append(f'{name}: 제외 뒤 남은 논문이 미확인 상태로 표시되지 않음')
        for t in (profiles.get(lab_id) or {}).get('topics') or []:
            if t.get('section') == 'representative_paper' and key(t.get('label_ko')) and any(k.startswith(key(t['label_ko'])) for k in titles):
                problems.append(f"{name}: 제외한 논문이 app_profiles.jsonl에 남아 있음 ({t['label_ko'][:40]})")
        if lab_id in (data.mapping.get('labs') or {}) and lab_id in ((data.mapping.get('migration') or {}).get('requires_recompute') or []):
            problems.append(f'{name}: 재계산 대상인데 예전 과목 유사도가 남아 있음')
    # Every lab: the profile must be built from the current papers, or search and the AI guide use stale papers.
    for lab_id, profile in profiles.items():
        bundle = bundles.get(lab_id) or {}
        expected = [p['title'].strip()[:100] for p in (bundle.get('papers') or [])[:5] if (p.get('title') or '').strip()]
        actual = [t['label_ko'] for t in profile.get('topics') or [] if t.get('section') == 'representative_paper']
        if expected != actual or profile.get('paper_basis') != bundle.get('basis'):
            problems.append(f"{(profile.get('professors') or [lab_id])[0]}: app_profiles.jsonl의 대표 논문이 papers.jsonl과 다름")
    mapping = data.mapping
    for fname, digest in (mapping.get('sources') or {}).items():
        if sha(data.root / fname) != digest:
            problems.append(f'lab_course_bge_m3.json의 {fname} 해시가 현재 파일과 다름: 서버가 과목 유사도 전체를 읽지 않는다')
    retained = (mapping.get('migration') or {}).get('retained_profile_sha256') or {}
    if retained:
        for line, row in data.profile_lines:
            if row['lab_id'] in retained and hashlib.sha256(line.encode('utf-8')).hexdigest() != retained[row['lab_id']]:
                problems.append(f"{row['lab_id']}: 프로필이 바뀌었는데 예전 과목 유사도를 그대로 씀")
    manifest = data.manifest
    if manifest:
        corrected = {e['path']: e['sha256'] for e in manifest.get('corrected_files') or []}
        for entry in [*(manifest.get('files') or []), *(manifest.get('derived_files') or [])]:
            path = data.root / entry['path']
            if not path.exists() or sha(path) != corrected.get(entry['path'], entry['sha256']):
                problems.append(f"IMPORT_MANIFEST.json의 {entry['path']} 해시가 현재 파일과 다름 (검토한 수정이면 stamp)")
    report_path = data.root / AUDIT_FILE
    if report_path.exists() and json.loads(report_path.read_text(encoding='utf-8')) != audit_report(data):
        problems.append(f'{AUDIT_FILE}가 현재 데이터와 다름 (audit --write)')
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data', type=Path, default=DATA)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('audit')
    a.add_argument('--write', action='store_true', help=f'대기열을 {AUDIT_FILE}에 저장')
    e = sub.add_parser('evidence')
    e.add_argument('lab_id')
    e.add_argument('--no-crossref', action='store_true')
    p = sub.add_parser('apply')
    p.add_argument('lab_id')
    p.add_argument('--offline', action='store_true', help='캐시에 있는 응답만 사용')
    sub.add_parser('check')
    sub.add_parser('stamp')
    args = parser.parse_args(argv)
    data = Data(args.data)
    if args.command == 'audit':
        report = audit_report(data)
        print_audit(report)
        if args.write:
            write_atomic(data.root / AUDIT_FILE, json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    elif args.command == 'evidence':
        print_evidence(evidence(data, args.lab_id, with_crossref=not args.no_crossref))
    elif args.command == 'apply':
        try:
            print(json.dumps(apply(data, args.lab_id, offline=args.offline), ensure_ascii=False))
        except ValueError as exc:
            sys.exit(f'반영하지 않음: {exc}')
    elif args.command == 'stamp':
        stamp(data)
        print('IMPORT_MANIFEST.json 해시를 현재 파일로 갱신함')
    else:
        problems = check(data)
        for line in problems:
            print('문제:', line)
        print(f'판정 {sum(1 for o in data.overrides.values() if any(k in o for k in ("paper_exclusions", "paper_allowlist")))}곳 · 문제 {len(problems)}건')
        if problems:
            sys.exit(1)


if __name__ == '__main__':
    main()
