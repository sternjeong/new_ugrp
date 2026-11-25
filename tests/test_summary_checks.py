"""The shared lab brief: broken words are rejected before a brief is stored, and the venue is added when it is read."""
import unittest

from curri.research_guide import ResearchGuide, script_glitch


class FakePapers:
    rows = {'lab': {'papers': [{'title': '논문 하나', 'doi': '10.1000/x1', 'venue': 'Physical Review Letters'},
                               {'title': '논문 둘', 'openalex_id': 'W2', 'venue': None}]}}


def guide():
    g = ResearchGuide(None, FakePapers())
    g.brief_sources = lambda lab_id: [{'id': 'S1', 'kind': '연구 분야', 'text': '양자 정보'},
                                      {'id': 'P1', 'kind': '대표 논문', 'title': '논문 하나', 'year': 2026, 'text': '초록', 'url': 'https://doi.org/10.1000/x1'}]
    return g


def answer(oneliner='양자 정보를 연구하는 연구실입니다.', focus_plain='양자 오류 정정(quantum error correction)을 다룹니다.',
           plain='얽힘(entanglement)을 되살리는 방법을 보였습니다.', meaning='두 입자가 이어진 상태'):
    return {'lab_oneliner': oneliner, 'focus': [{'title': '양자 오류 정정', 'plain': focus_plain, 'source_ids': ['S1']}],
            'papers': [{'paper_id': 'P1', 'plain': plain, 'terms': [{'term': '얽힘(entanglement)', 'meaning': meaning}]}]}


class BriefChecksTest(unittest.TestCase):
    payload = {'check': {'lab_id': 'lab'}}

    def test_a_clean_brief_is_kept(self):
        result = guide().validate_summary(self.payload, answer())
        self.assertEqual(result['lab_oneliner'], '양자 정보를 연구하는 연구실입니다.')
        self.assertEqual([p['title'] for p in result['papers']], ['논문 하나'])

    def test_a_word_that_switches_script_is_rejected_wherever_the_model_wrote_it(self):
        for bad in (answer(oneliner='뉴로리gin을 연구하는 연구실입니다.'), answer(focus_plain='표준模型과 그 너머를 다룹니다.'),
                    answer(plain='플라즈monics 소자를 만들었습니다.'), answer(meaning='기계학習에 쓰는 방법'),
                    answer(plain='そして 결과를 얻었습니다. 그리고の결과입니다.')):
            with self.assertRaisesRegex(ValueError, '글자가 깨진 단어'):
                guide().validate_summary(self.payload, bad)

    def test_ordinary_mixed_writing_is_not_a_glitch(self):
        for fine in ('TGFβ1을 넣으면 DNA가 늘고 mRNA도 변합니다.', '문턱 전압(threshold voltage)이 Si-based 소자에서 10 nm보다 얇습니다.',
                     'neuroligin 3는 Wnt/β-catenin 신호와 few-shot 학습에 쓰입니다.', '한문학(漢文學)과 일본어(日本語) 자료를 읽습니다.',
                     'pH와 kHz, CO2 환원을 다룹니다.'):
            self.assertIsNone(script_glitch(fine), fine)
        self.assertEqual(script_glitch('뉴로리gin 3'), '리gin')
        self.assertEqual(script_glitch('표준模型'), '준模')

    def test_a_title_from_the_data_is_not_checked(self):
        g = guide()
        g.brief_sources = lambda lab_id: [{'id': 'P1', 'kind': '대표 논문', 'title': '표준模型의 검증', 'year': 2026, 'text': '초록', 'url': 'u'}]
        raw = {'lab_oneliner': '입자물리를 연구하는 연구실입니다.', 'focus': [], 'papers': [{'paper_id': 'P1', 'plain': '표준 모형을 검증했습니다.', 'terms': []}]}
        self.assertEqual(g.validate_summary(self.payload, raw)['papers'][0]['title'], '표준模型의 검증')

    def test_the_venue_is_added_when_a_cached_brief_is_read(self):
        cached = {'version': 'S2', 'lab_oneliner': 'x', 'focus': [],
                  'papers': [{'title': '논문 하나', 'year': 2026, 'url': 'https://doi.org/10.1000/x1', 'plain': 'p', 'terms': []},
                             {'title': '논문 둘', 'year': 2025, 'url': 'https://openalex.org/W2', 'plain': 'p', 'terms': []},
                             {'title': '목록에 없는 논문', 'year': 2020, 'url': 'https://doi.org/10.1000/gone', 'plain': 'p', 'terms': []}]}
        shown = guide().with_venues('lab', cached)
        self.assertEqual([p['venue'] for p in shown['papers']], ['Physical Review Letters', '', ''])
        self.assertNotIn('venue', cached['papers'][0])  # the stored brief is not changed
        self.assertEqual(guide().with_venues('unknown', cached)['papers'][0]['venue'], '')


if __name__ == '__main__':
    unittest.main()
