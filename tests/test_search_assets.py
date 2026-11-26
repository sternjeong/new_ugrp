"""The worker's search chunks must not keep a paper its lab no longer shows."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'embed_worker'))
import build_search_assets  # noqa: E402


class RemovedPaperTests(unittest.TestCase):
    def test_a_paper_removed_by_review_leaves_the_search_chunks(self):
        chunk = lambda owner, kind, wid=None: {'owner': owner, 'kind': kind, 'text': 't', 'meta': {'openalex_id': wid} if wid else {}}
        chunks = [chunk('lab', 'intro'), chunk('lab', 'paper', 'W1'), chunk('lab', 'paper', 'https://openalex.org/W2'),
                  chunk('lab', 'paper', 'W20'), chunk('other', 'paper', 'W1'), chunk('unlisted', 'paper', 'W9'), chunk('lab', 'paper')]
        current = {'lab': {'W2', 'W20'}, 'other': {'W1'}}  # W20 is a version id of a paper the lab still shows
        self.assertEqual(build_search_assets.removed_papers(chunks, current), [1])

    def test_current_papers_include_version_ids(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'papers.jsonl'
            path.write_text(json.dumps({'id': 'lab', 'papers': [{'openalex_id': 'W2', 'versions': ['W20']}]}) + '\n')
            self.assertEqual(build_search_assets.current_papers(path), {'lab': {'W2', 'W20'}})


if __name__ == '__main__':
    unittest.main()


class SummaryRowTests(unittest.TestCase):
    def test_one_summary_per_listed_lab(self):
        chunks = [{'owner': 'a', 'kind': 'summary'}, {'owner': 'gone', 'kind': 'summary'}, {'owner': 'b', 'kind': 'intro'},
                  {'owner': 'a', 'kind': 'summary'}, {'owner': 'b', 'kind': 'summary'}]
        self.assertEqual(build_search_assets.summary_rows(chunks, {'a', 'b'}), [3, 4])
