import unittest

from curri.curated_catalog import clip, not_about_research, sentences, snippet
from curri.text_cleanup import tidy


class TidyTests(unittest.TestCase):
    def test_removes_markup_left_by_scraping_and_paper_metadata(self):
        cases = {'invitation&nbsp;<span>from</span> a club': 'invitation from a club',
                 'measured$\\boldsymbol{V_{T}}$shift': 'measured V_T shift',
                 '$\\bar{B} \\to D^\\ast$ decay': 'B̄ → D^* decay',
                 'the $[0,1]$-valued case': 'the [0,1]-valued case',
                 '**type theory** in languages': 'type theory in languages',
                 '## For more information': 'For more information',
                 'Home > Research Area\nWe study robots': 'We study robots',
                 'word-break: keep-all; /* 줄바꿈 */\nWe study robots': 'We study robots',
                 'Home | Projects | People | Publications | News\nWe study robots': 'We study robots',
                 'as in \\citet{foster21} we call \\emph{sign-betting}': 'as in we call sign-betting',
                 'was$52.5~\\mu \\Omega \\cdot $cm': 'was 52.5~μ Ω ·cm',
                 'achieves$102.4 Gb / s$throughput': 'achieves 102.4 Gb / s throughput',
                 'order $$s+1$$ here': 'order s+1 here',
                 'ensemble ($a = 0.12\;\\text{fm}$)': 'ensemble (a = 0.12 fm)',
                 'Artificial IntelligenceArtificial Intelligence': 'Artificial Intelligence'}
        for raw, expected in cases.items():
            self.assertEqual(tidy(raw), expected)

    def test_keeps_money_and_empty_values(self):
        self.assertEqual(tidy('costs $5 to $10 each'), 'costs $5 to $10 each')
        self.assertEqual(tidy(None), '')


class SentenceTests(unittest.TestCase):
    def test_a_title_abbreviation_or_line_break_does_not_end_a_sentence(self):
        self.assertEqual(sentences('The lab (CAOS Lab.) is led by Prof. Sungjin Lee and Prof. Jisung Park.'),
                         ['The lab (CAOS Lab.) is led by Prof. Sungjin Lee and Prof. Jisung Park.'])
        self.assertEqual(sentences('We use a technique called stable isotopes to\nTrack pollutants from emissions to people.'),
                         ['We use a technique called stable isotopes to Track pollutants from emissions to people.'])

    def test_snippet_skips_headings_and_page_furniture(self):
        text = 'Research Interests\nTel : 054-279-2295\n2019.09 ~ 2023.08 Univ. of Miami 연구조교수\nWe develop soft sensors that interface with the human body.'
        self.assertEqual(snippet(text)[0], 'We develop soft sensors that interface with the human body.')

    def test_nothing_quotable_gives_no_snippet(self):
        self.assertEqual(snippet('Tel : 054-279-2295\nprofessor@postech.ac.kr please write')[0], '')

    def test_recognises_non_research_lines(self):
        for line in ('We are looking for graduate students.', 'Pohang University of Science and Technology', '2022: Ph.D., California Institute of Technology'):
            self.assertTrue(not_about_research(line), line)
        self.assertFalse(not_about_research('Our research at POSTECH focuses on quantum computing.'))

    def test_clip_prefers_a_sentence_end(self):
        text = 'First sentence is here and it is fairly long. ' + 'word ' * 40
        self.assertEqual(clip(text, 60), 'First sentence is here and it is fairly long.')
