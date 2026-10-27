"""Explainable small-corpus search. No embedding model or external search service."""
import re
import unicodedata
from difflib import SequenceMatcher


def normalize(text):
    return unicodedata.normalize('NFKC', text).casefold()


def terms(text):
    return re.findall(r'[a-z0-9_]+|[\u3400-\u9fff]+', normalize(text))


def rank(post, query):
    needles = terms(query)[:12]
    if not needles:
        return 0, []
    fields = [('标题', post['title'], 8), ('话题', post['topic'], 6),
              ('作者', post['name'], 5), ('正文', post['body'], 2)]
    score, reasons = 0, []
    for needle in needles:
        best, reason = 0, ''
        for label, value, weight in fields:
            value = normalize(value)
            if needle in value:
                points = weight * (3 if value == needle else 2)
                if points > best:
                    best, reason = points, label + '匹配'
            elif len(needle) >= 4:
                # One-edit-like near match only for sufficiently long tokens.
                for word in terms(value):
                    candidates = [word] if len(word) <= len(needle)+1 else [word[i:i+len(needle)] for i in range(len(word)-len(needle)+1)]
                    if any(abs(len(c)-len(needle)) <= 1 and SequenceMatcher(None,needle,c).ratio() >= 1-1/len(needle) for c in candidates):
                        if weight * .5 > best:
                            best, reason = weight * .5, label + '近似匹配'
        if not best:
            return 0, []  # All query terms must match somewhere.
        score += best
        if reason not in reasons:
            reasons.append(reason)
    return score, reasons
