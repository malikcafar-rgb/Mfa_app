"""Keyword-based classification of articles into categories and countries.

Deterministic and cheap — keeps the app fully functional with no API key.
"""

from __future__ import annotations

from typing import List

from . import config
from .models import Article

ORG_CATEGORY = "international_orgs"


def _haystack(article: Article) -> str:
    # Pad with spaces so " ai " / " uk " style boundary keywords match at edges.
    return f" {article.title} {article.summary} ".lower()


def _matches(text: str, keywords) -> bool:
    return any(kw.lower() in text for kw in keywords)


def classify(articles: List[Article]) -> List[Article]:
    cats = config.categories()
    countries = config.countries()

    org_spec = cats.get(ORG_CATEGORY, {})
    org_keywords = org_spec.get("keywords", [])
    az_relevance = org_spec.get("az_relevance", [])

    for a in articles:
        text = _haystack(a)

        is_org_source = a.category_hint == ORG_CATEGORY
        az_relevant = _matches(text, az_relevance)

        if is_org_source:
            # Items from official international-organization feeds contribute ONLY
            # to the org section, and only when they reference Azerbaijan/its
            # region — so a global org feed never floods the topical sections.
            matched_cats = [ORG_CATEGORY] if az_relevant else []
        else:
            # Standard topical keyword tagging (org section handled separately).
            matched_cats = [
                key
                for key, spec in cats.items()
                if key != ORG_CATEGORY and _matches(text, spec.get("keywords", []))
            ]

            # Force official Azerbaijani sources into the priority category.
            if a.category_hint == "azerbaijan" and a.tier == "official":
                if "azerbaijan" not in matched_cats:
                    matched_cats.insert(0, "azerbaijan")

            # Analysis-tier sources (Foreign Affairs, War on the Rocks, E-IR) are
            # the backbone of the IR-theory section — always make them eligible.
            if a.tier == "analysis" and "ir_theory" not in matched_cats:
                matched_cats.append("ir_theory")

            # A general-wire story about an international organization joins the
            # org section only when it also references Azerbaijan / its region.
            if az_relevant and _matches(text, org_keywords):
                matched_cats.append(ORG_CATEGORY)

            # Fall back to the source's default category hint if nothing matched.
            if not matched_cats and a.category_hint:
                matched_cats.append(a.category_hint)

        a.categories = matched_cats

        a.countries = [
            key
            for key, spec in countries.items()
            if _matches(text, spec.get("keywords", []))
        ]

    return articles
