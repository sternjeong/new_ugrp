import unittest

from curri.intent_mirror import build_mirror, clean_slots

LONG = ('드론이나 로봇처럼 전력이 제한된 기기에서 추론할 때 정보를 줄이는 연구가 궁금해요. '
        'Python으로 빠르게 만들어 보고 피드백을 받는 방식이 좋아요. '
        '5개월 인턴이라 요구 사항이 너무 많은 곳은 부담돼요. 결과물은 실제로 움직이는 데모면 좋겠어요.')


class IntentMirrorTest(unittest.TestCase):
    def test_short_text_gets_no_mirror(self):
        self.assertIsNone(build_mirror('로봇 제어가 궁금해요', likes=['로봇 제어']))

    def test_long_text_naming_one_dimension_gets_no_mirror(self):
        text = '로봇 제어가 궁금해요. ' * 6
        self.assertIsNone(build_mirror(text, likes=['로봇 제어']))

    def test_every_value_and_quote_comes_from_the_text(self):
        mirror = build_mirror(LONG, likes=['전력이 제한된 기기 추론'])
        self.assertIsNotNone(mirror)
        for slot in mirror['slots']:
            if slot['key'] != 'topic':
                for value in slot['values']:
                    self.assertIn(value, LONG)
            if slot['quote']:
                self.assertIn(slot['quote'], LONG)

    def test_dimensions_and_quotes(self):
        mirror = build_mirror(LONG, likes=['정보를 줄이는 연구'])
        slots = {s['key']: s for s in mirror['slots']}
        self.assertEqual(set(slots), {'topic', 'style', 'output', 'constraint'})
        self.assertIn('Python', slots['style']['values'])
        self.assertIn('데모', slots['output']['values'])
        self.assertIn('5개월', slots['constraint']['values'])
        self.assertTrue(slots['topic']['quote'].startswith('드론이나 로봇'))
        self.assertEqual(mirror['missing'], [])

    def test_unmentioned_dimensions_are_listed_missing_not_filled(self):
        text = '신약 개발에 AI를 쓰는 연구가 궁금하고, 파이썬으로 직접 만들어 보는 걸 좋아해요. 이번 방학에 해 보고 싶어요.'
        mirror = build_mirror(text, likes=['신약 개발 AI'])
        keys = {s['key'] for s in mirror['slots']}
        self.assertNotIn('output', keys)
        self.assertEqual(mirror['missing'], ['만들고 싶은 결과'])

    def test_english_words_do_not_trigger_keywords(self):
        text = 'I want a shipping API for packaging robots, and research on grip control for several weeks now.'
        self.assertIsNone(build_mirror(text, likes=['grip control']))

    def test_dislikes_are_passed_through_without_new_claims(self):
        mirror = build_mirror(LONG, likes=['정보를 줄이는 연구'], dislikes=['C++ 개발'])
        self.assertEqual(mirror['avoid'], ['C++ 개발'])

    def test_sentence_sized_topic_from_the_interpreter_is_not_shown(self):
        tail = '로봇처럼 전력이 제한된 환경에서 추론할 때 입력 정보를 본질만 남기는 연구 Python으로 빠르게 만들어 보고'
        mirror = build_mirror(LONG, likes=['드론', tail])
        topic = next(s for s in mirror['slots'] if s['key'] == 'topic')
        self.assertEqual(topic['values'], ['드론'])
        only_tail = build_mirror(LONG, likes=[tail])
        self.assertNotIn('topic', {s['key'] for s in only_tail['slots']})

    def test_long_sentence_quote_is_a_bounded_slice(self):
        text = '로봇 ' * 60 + '데모를 만들고 싶어요. 파이썬으로 설계하는 걸 좋아해요.'
        mirror = build_mirror(text)
        for slot in mirror['slots']:
            self.assertLessEqual(len(slot['quote']), 100)
            self.assertIn(slot['quote'], text)


class CleanSlotsTest(unittest.TestCase):
    def test_keeps_student_edits_trimmed_and_deduplicated(self):
        slots = [{'key': 'style', 'values': ['  Python ', 'Python', '직접   만들기']}, {'key': 'output', 'values': []}]
        self.assertEqual(clean_slots(slots), [{'key': 'style', 'label': '하고 싶은 방식', 'values': ['Python', '직접 만들기']}])

    def test_empty_list_clears(self):
        self.assertEqual(clean_slots([]), [])

    def test_rejects_unknown_keys_duplicates_and_oversize(self):
        for bad in ('x', [{'key': 'who_you_are', 'values': ['a']}], [{'key': 'style', 'values': ['a']}, {'key': 'style', 'values': ['b']}],
                    [{'key': 'style', 'values': ['가' * 41]}], [{'key': 'style', 'values': [1]}], [{'key': 'style', 'values': ['a'] * 9}], ['style']):
            with self.assertRaises(ValueError):
                clean_slots(bad)


if __name__ == '__main__':
    unittest.main()


class MultiSentenceTopicTests(unittest.TestCase):
    def test_topic_survives_when_other_sentences_name_style_and_conditions(self):
        from curri.curated_query_engine import classify_curated_query
        text = '로봇 비전을 연구하고 싶어요. 파이썬으로 빠르게 데모를 만들어 보고 싶고, 방학 동안 2개월 인턴이면 좋겠어요.'
        read = classify_curated_query(text)
        mirror = build_mirror(text, read['likes'], read['dislikes'])
        topic = next(s for s in mirror['slots'] if s['key'] == 'topic')
        self.assertEqual(topic['values'], ['로봇 비전'])
