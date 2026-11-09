"""Shared pieces: rule parsing with the tail fix under test, and the LLM parse output."""
import json
import re
from pathlib import Path

from curri.curated_query_engine import classify_curated_query

OUT = Path(__file__).resolve().parent
TAIL = re.compile(r'\s*(?:(?:같은|비슷한)\s*(?:거|것|걸)\s*(?:하는|다루는)?|(?:을|를|에|로|으로|은|는|이|가)?\s*(?:추천\s*해?\s*(?:주세|줘|주)?\S*|찾고\s*있\S*|찾아\S*|찾\S*|있을까\S*|있나\S*|있어\S*|있\S*|어디가?\s*맞을까\S*|어디\S*|뭐가?\s*\S*|해볼\s*수\s*\S*|해\s*보고\S*|궁금\S*|좋겠\S*)|(?:연구하는|다루는|하는)?\s*(?:곳|데|연구실|랩|쪽)|연구하는|다루는|하는)$')


def clean_like(phrase):
    """Remove request wording from the end of a phrase ('방사선 연구하는 곳 있' -> '방사선')."""
    text = phrase.strip()
    for _ in range(6):
        new = TAIL.sub('', text).strip()
        if new == text or len(new) < 2:
            break
        text = new
    return text if len(text) >= 2 else phrase.strip()


def rule_parse(text, clean):
    parsed = classify_curated_query(text)
    if clean:
        parsed['likes'] = list(dict.fromkeys(clean_like(p) for p in parsed['likes']))
    return parsed
