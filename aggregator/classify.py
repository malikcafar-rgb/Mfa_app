"""Keyword-based classification of articles into categories and countries.

Deterministic and cheap — keeps the app fully functional with no API key.
"""

from __future__ import annotations

from typing import List

from . import config
from .models import Article


def _haystack(article: Article) -> str:
    # Pad with spaces so " ai " / " uk " style boundary keywords match at edges.
    return f" {article.title} {article.summary} ".lower()


def classify(articles: List[Article]) -> List[Article]:
    cats = config.categories()
    countries = config.countries()

    for a in articles:
        text = _haystack(a)

        matched_cats: List[str] = []
        for key, spec in cats.items():
            if any(kw.lower() in text for kw in spec.get("keywords", [])):
                matched_cats.append(key)

        # Force official Azerbaijani sources into the priority category.
        if a.category_hint == "azerbaijan" and a.tier == "official":
            if "azerbaijan" not in matched_cats:
                matched_cats.insert(0, "azerbaijan")

        # Fall back to the source's default category hint if nothing matched.
        if not matched_cats and a.category_hint:
            matched_cats.append(a.category_hint)

        a.categories = matched_cats

        matched_countries: List[str] = []
        for key, spec in countries.items():
            if any(kw.lower() in text for kw in spec.get("keywords", [])):
                matched_countries.append(key)
        a.countries = matched_countries

    return articles
