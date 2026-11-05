import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curri.research_papers import ResearchPapers


class ResearchPapersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'papers.jsonl'
        path.write_text(json.dumps({'id': 'lab', 'papers': [
            {'openalex_id': 'W1', 'title': 'Neural sensors', 'year': 2025, 'abstract': 'Sensor abstract'},
            {'openalex_id': 'W2', 'title': 'Neural devices', 'year': 2024},
        ]}) + '\n')
        self.papers = ResearchPapers(path)

    def test_recent_and_selected_are_scoped_to_lab(self):
        self.assertEqual(self.papers.recent('lab')[0]['id'], 'W1')
        self.assertEqual(self.papers.recent('other'), [])
        for ids in [['W999'], ['W1'] * 4, 'W1']:
            with self.assertRaises(ValueError):
                self.papers.get_selected('lab', ids)

    def test_reference_lookup_is_direct_bounded_and_cached(self):
        calls = [{'results': [{'id': 'https://openalex.org/W1', 'referenced_works': ['https://openalex.org/W7']}]},
                 {'results': [{'id': 'https://openalex.org/W7', 'title': 'Prior work', 'cited_by_count': 9}]}]
        with patch.object(self.papers, '_get', side_effect=calls) as get:
            result = self.papers.guide('lab', ['W1'])
            self.assertEqual(result['references'][0]['id'], 'W7')
            self.assertEqual(result['related'][0]['id'], 'W2')
            self.assertFalse(result['unavailable'])
            self.papers.guide('lab', ['W1'])
            self.assertEqual(get.call_count, 2)

    def test_reference_failure_is_visible(self):
        with patch.object(self.papers, '_get', side_effect=OSError('offline')):
            result = self.papers.guide('lab', ['W1'])
            self.assertTrue(result['unavailable'])
            self.assertEqual(result['references'], [])
