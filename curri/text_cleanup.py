"""Remove scraping and paper-metadata leftovers from text shown to students. The source files stay as they are."""
import html
import re

INLINE_TAG = re.compile(r'</?(?:span|sup|sub|i|b|em|strong|u|a|font|jats:(?:italic|bold|sup|sub)|mml:[\w-]+)(?:\s[^<>]*)?/?>', re.I)
BLOCK_TAG = re.compile(r'</?(?:p|br|div|li|ul|ol|h[1-6]|jats:[\w-]+)(?:\s[^<>]*)?/?>', re.I)
MATH = re.compile(r'\$([^$\n]{1,300})\$')
WRAPPER = re.compile(r'\\(?:boldsymbol|mathrm|mathbf|mathit|mathsf|mathcal|text|textbf|textit|operatorname)\s*\{([^{}]*)\}')
ACCENT = {'bar': '\u0304', 'hat': '\u0302', 'tilde': '\u0303'}
SYMBOLS = {'cdot': '·', 'times': '×', 'to': '→', 'rightarrow': '→', 'leftarrow': '←', 'pm': '±', 'sim': '~', 'approx': '≈', 'leq': '≤', 'le': '≤',
           'geq': '≥', 'ge': '≥', 'neq': '≠', 'infty': '∞', 'ast': '*', 'ell': 'ℓ', 'degree': '°', 'circ': '°', 'partial': '∂', 'nabla': '∇',
           'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε', 'varepsilon': 'ε', 'zeta': 'ζ', 'eta': 'η', 'theta': 'θ',
           'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ', 'pi': 'π', 'rho': 'ρ', 'sigma': 'σ', 'tau': 'τ', 'phi': 'φ', 'varphi': 'φ',
           'chi': 'χ', 'psi': 'ψ', 'omega': 'ω', 'Gamma': 'Γ', 'Delta': 'Δ', 'Theta': 'Θ', 'Lambda': 'Λ', 'Sigma': 'Σ', 'Phi': 'Φ', 'Omega': 'Ω'}
CITATION = re.compile(r'\\cite[tp]?\s*\{[^{}]*\}')
TEXT_COMMAND = re.compile(r'\\(?:emph|textit|textbf|texttt|mathrm|text)\s*\{([^{}]*)\}')
BOLD = re.compile(r'\*\*(.+?)\*\*')
MD_HEADING = re.compile(r'^\s*#{1,6}\s*', re.M)
BREADCRUMB = re.compile(r'^\s*Home\s*>.*$', re.M)
MENU_SENTENCE = re.compile(r'[^.\n]*메뉴에서 선택[^.\n]*\.?')
CSS_LINE = re.compile(r'^\s*(?:[a-z-]+:\s*[^;\n]{1,60};\s*(?:/\*.*\*/)?|/\*.*\*/)\s*$', re.M)
NAV_LINE = re.compile(r'^\s*(?:[^|\n]{1,20}\|\s*){3,}[^|\n]{0,20}$', re.M)
BULLET_BOLD = re.compile(r'^\s*\*\*\s*', re.M)
OPEN_MATH_END = re.compile(r'\s*\$[^$\n]*[\\_^{][^$\n]*$')  # the source itself stops inside a formula
REPEATED = re.compile(r'(?<!\S)(\S.{4,70}?)\s*\1(?=\s|$)', re.M)


def _math(match):
    body = match.group(1)
    glued = match.start() and match.string[match.start() - 1].isalpha()  # 'achieves$102.4 Gb / s$throughput' is a formula, not money
    if not glued and not re.search(r'[\\_^=+()\[\]<>|]', body) and not re.fullmatch(r'[A-Za-zα-ωΑ-Ω]{1,3}', body) or ('\\' not in body and re.match(r'\d[\d,.]*\s*(?:to|[-–~]|million|billion|$)', body)):
        return match.group(0)  # an amount such as $5 to $10
    while WRAPPER.search(body):
        body = WRAPPER.sub(r'\1', body)
    body = re.sub(r'\\(bar|hat|tilde)\s*\{([^{}]*)\}', lambda m: re.sub(r'\\(\w+)', lambda s: SYMBOLS.get(s.group(1), ''), m.group(2)) + ACCENT[m.group(1)], body)
    body = re.sub(r'\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}', r'\1/\2', body)
    body = re.sub(r'\\sqrt\s*\{([^{}]*)\}', r'√\1', body)
    body = re.sub(r'\\[;,!: ]', ' ', body)
    body = re.sub(r'\\([A-Za-z]+)', lambda m: SYMBOLS.get(m.group(1), ''), body)
    body = re.sub(r'([_^])\{([^{}]*)\}', r'\1\2', body).replace('{', '').replace('}', '').replace('\\', '')
    body = re.sub(r'\s+', ' ', body).strip()
    text, start, end = match.string, match.start(), match.end()
    if body and body[0].isalnum() and start and text[start - 1].isalnum():
        body = ' ' + body
    if body and body[-1].isalnum() and end < len(text) and text[end].isalnum():
        body += ' '
    return body


def tidy(text):
    """HTML, LaTeX and markdown markup, site navigation and headings scraped twice."""
    if not text:
        return text or ''
    text = INLINE_TAG.sub('', html.unescape(text).replace('\xa0', ' '))
    text = BLOCK_TAG.sub(' ', text)
    text = TEXT_COMMAND.sub(r'\1', CITATION.sub('', text.replace('$$', '$')))
    text = OPEN_MATH_END.sub('', MATH.sub(_math, text))
    text = BULLET_BOLD.sub('', MD_HEADING.sub('', BOLD.sub(r'\1', text)))
    text = NAV_LINE.sub('', CSS_LINE.sub('', MENU_SENTENCE.sub('', BREADCRUMB.sub('', text))))
    text = REPEATED.sub(r'\1', text)
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]{2,}', ' ', text)).strip()
