"""The text forms each query is searched with (shared by the Kaggle packet and the strategies)."""
from common import rule_parse


def forms(text):
    """Rule parse, plus `positive`: the likes when a dislike must stay out of the search text, else the raw input."""
    parsed = rule_parse(text, True)
    likes = parsed['likes']
    positive = ' '.join(likes) if parsed['dislikes'] and likes else text
    return parsed, positive
