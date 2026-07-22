"""Core data structures used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

# Reliability tiers, ordered best-first. Used for ranking and display badges.
TIER_ORDER = {"official": 0, "wire": 1, "analysis": 2}


@dataclass
class Article:
    """A single normalized news item from any source."""

    title: str
    url: str
    source: str
    tier: str = "wire"
    published: Optional[datetime] = None
    summary: str = ""
    category_hint: str = ""
    # Populated by classify.py:
    categories: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)

    @property
    def tier_rank(self) -> int:
        return TIER_ORDER.get(self.tier, 99)


@dataclass
class Cluster:
    """A group of articles reporting the same underlying story."""

    articles: List[Article] = field(default_factory=list)
    # Populated by summarize.py (empty in links-only mode):
    ai_summary: str = ""

    @property
    def lead(self) -> Article:
        """The most authoritative / most recent article in the cluster."""
        return sorted(
            self.articles,
            key=lambda a: (a.tier_rank, -(a.published.timestamp() if a.published else 0)),
        )[0]

    @property
    def title(self) -> str:
        return self.lead.title

    @property
    def sources(self) -> List[Article]:
        """De-duplicated source links, best tier first."""
        seen = set()
        out = []
        for a in sorted(self.articles, key=lambda a: a.tier_rank):
            if a.source not in seen:
                seen.add(a.source)
                out.append(a)
        return out

    @property
    def excerpt(self) -> str:
        return self.lead.summary


@dataclass
class Section:
    """A themed section of the brief: a category or a country."""

    key: str
    label: str
    clusters: List[Cluster] = field(default_factory=list)
    # Populated by summarize.py (empty in links-only mode):
    ai_brief: str = ""
    group: str = ""  # only used for country sections


@dataclass
class Brief:
    """The full assembled briefing for one run."""

    generated_at: datetime
    category_sections: List[Section] = field(default_factory=list)
    country_sections: List[Section] = field(default_factory=list)
    executive_summary: str = ""
    ir_framing: str = ""
    ai_enabled: bool = False
    ai_note: str = ""  # shown in the links-only banner (why AI text is absent)
    total_articles: int = 0
    total_clusters: int = 0

    @property
    def date_str(self) -> str:
        return self.generated_at.strftime("%Y-%m-%d")

    @property
    def display_date(self) -> str:
        return self.generated_at.strftime("%A, %d %B %Y")
