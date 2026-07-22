"""Cluster near-duplicate articles reporting the same story.

Two signals are combined so both syndicated duplicates (near-identical headlines)
and cross-outlet paraphrases (different wording, same event) are caught, without
recklessly merging unrelated stories:

  1. Fuzzy title similarity (rapidfuzz token_set_ratio) above a strict threshold.
  2. Overlap of significant content words (proper nouns / topic words), which
     rescues paraphrased headlines the fuzzy ratio alone misses.
"""

from __future__ import annotations

import re
from typing import List, Set

from rapidfuzz import fuzz

from .models import Article, Cluster

FUZZY_THRESHOLD = 80          # 0-100; strict, for near-identical headlines
MIN_SHARED_CONTENT_WORDS = 4  # fallback: this many shared significant words merges

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "as", "of", "to", "in", "on", "for",
    "with", "amid", "over", "after", "before", "at", "by", "from", "into", "up",
    "new", "says", "say", "said", "will", "amid", "its", "his", "her", "their",
    "is", "are", "was", "were", "be", "has", "have", "not", "no", "off",
}


def _normalize(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]+", " ", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def _content_words(norm_title: str) -> Set[str]:
    return {w for w in norm_title.split() if len(w) >= 4 and w not in _STOPWORDS}


def _is_match(norm_a: str, words_a: Set[str], norm_b: str, words_b: Set[str]) -> bool:
    if fuzz.token_set_ratio(norm_a, norm_b) >= FUZZY_THRESHOLD:
        return True
    if len(words_a & words_b) >= MIN_SHARED_CONTENT_WORDS:
        return True
    return False


def cluster_articles(articles: List[Article]) -> List[Cluster]:
    """Greedy single-pass clustering by title similarity + content-word overlap."""
    clusters: List[Cluster] = []
    norms: List[str] = []
    words: List[Set[str]] = []

    for a in articles:
        norm = _normalize(a.title)
        cwords = _content_words(norm)
        placed = False
        for idx in range(len(clusters)):
            if _is_match(norm, cwords, norms[idx], words[idx]):
                clusters[idx].articles.append(a)
                placed = True
                break
        if not placed:
            clusters.append(Cluster(articles=[a]))
            norms.append(norm)
            words.append(cwords)

    return clusters
