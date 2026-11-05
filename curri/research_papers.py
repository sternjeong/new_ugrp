"""Source-backed papers and bounded OpenAlex reference lookup for research exploration."""
import json
import re
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .curated_catalog import load_jsonl


def paper_id(value):
    match = re.fullmatch(r'(?:https://openalex.org/)?(W[0-9]+)', str(value or ''))
    return match.group(1) if match else None


class ResearchPapers:
    def __init__(self, path):
        self.labs = {}
        if path.exists():
            for row in load_jsonl(path):
                self.labs[row['id']] = {paper_id(p.get('openalex_id')): p for p in row.get('papers', [])
                                        if paper_id(p.get('openalex_id')) and p.get('title')}
        self.cache = {}
        self.lock = threading.Lock()

    def recent(self, lab_id):
        papers = self.labs.get(lab_id, {})
        return [self.public(p) for p in sorted(papers.values(),
                key=lambda p: (p.get('date') or str(p.get('year') or ''), p.get('openalex_id') or ''),
                reverse=True)[:20]]

    @staticmethod
    def public(p):
        pid = paper_id(p.get('openalex_id') or p.get('id'))
        doi = str(p.get('doi') or '').removeprefix('https://doi.org/')
        return {'id': pid, 'title': p.get('title') or '', 'year': p.get('year') or p.get('publication_year'),
                'abstract': (p.get('abstract') or '')[:1000],
                'url': f'https://doi.org/{doi}' if re.fullmatch(r'10\.\d{4,9}/\S+', doi) else f'https://openalex.org/{pid}',
                'cited_by_count': p.get('cited_by_count') or 0}

    def get_selected(self, lab_id, ids):
        papers = self.labs.get(lab_id, {})
        if not isinstance(ids, list) or len(ids) > 3 or any(not isinstance(i, str) or i not in papers for i in ids):
            raise ValueError('관심 논문은 이 연구실의 논문 중 최대 3개까지 선택할 수 있습니다.')
        return [papers[i] for i in dict.fromkeys(ids)]

    def guide(self, lab_id, ids):
        selected = self.get_selected(lab_id, ids)
        refs, unavailable = self.references(selected)
        refs.sort(key=lambda p: (-p['cited_by_count'], p['id']))
        words = lambda s: {w.lower() for w in re.findall(r'[A-Za-z]{4,}|[가-힣]{2,}', s or '')}
        terms = set().union(*(words(p['title']) for p in selected)) if selected else set()
        other = []
        for pid, paper in self.labs.get(lab_id, {}).items():
            if pid not in ids:
                overlap = len(terms & words(paper['title']))
                if overlap:
                    other.append((overlap, paper))
        other.sort(key=lambda pair: (-pair[0], -(pair[1].get('year') or 0), pair[1]['openalex_id']))
        return {'selected': [self.public(p) for p in selected], 'references': refs[:5],
                'related': [self.public(p) for _, p in other[:5]], 'unavailable': unavailable}

    def _get(self, path, params):
        url = 'https://api.openalex.org/' + path + '?' + urlencode(params)
        with urlopen(Request(url, headers={'User-Agent': '3mincurri/1.0'}), timeout=5) as response:
            return json.load(response)

    def references(self, papers):
        """Direct citations only; bounded fetch, failures are explicitly marked and not fabricated."""
        ids = tuple(sorted(paper_id(p['openalex_id']) for p in papers))
        if not ids:
            return [], False
        with self.lock:
            cached = self.cache.get(ids)
            if cached and time.monotonic() - cached[0] < 3600:
                return cached[1], False
        try:
            works = self._get('works', {'filter': 'openalex_id:' + '|'.join(ids), 'per_page': 3,
                                        'select': 'id,referenced_works'}).get('results', [])
            refs = sorted({paper_id(ref) for w in works for ref in w.get('referenced_works', []) if paper_id(ref)})[:50]
            if not refs:
                return [], False
            found = self._get('works', {'filter': 'openalex_id:' + '|'.join(refs), 'per_page': 50,
                                        'select': 'id,title,publication_year,cited_by_count,type,doi'}).get('results', [])
            result = [self.public(p) for p in found if p.get('title') and paper_id(p.get('id'))]
            with self.lock:
                self.cache[ids] = (time.monotonic(), result)
            return result, False
        except (OSError, ValueError, KeyError, TypeError):
            return [], True
