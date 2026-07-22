"""Pipeline orchestrator: fetch -> classify -> cluster -> summarize -> render."""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from . import config
from .classify import classify
from .cluster import cluster_articles
from .fetch import fetch_all
from .models import Brief, Cluster, Section
from .summarize import AISummarizer, run as run_summaries
from .render import render_site

MAX_CLUSTERS_PER_CATEGORY = 12
MAX_CLUSTERS_PER_COUNTRY = 6


def _cluster_categories(c: Cluster) -> set:
    out = set()
    for a in c.articles:
        out.update(a.categories)
    return out


def _cluster_countries(c: Cluster) -> set:
    out = set()
    for a in c.articles:
        out.update(a.countries)
    return out


def _cluster_recency(c: Cluster) -> float:
    dts = [a.published.timestamp() for a in c.articles if a.published]
    return max(dts) if dts else 0.0


def _rank_key(c: Cluster):
    # Best tier first, then more corroborating sources, then most recent.
    return (c.lead.tier_rank, -len(c.sources), -_cluster_recency(c))


def assemble_brief(clusters: List[Cluster]) -> Brief:
    cats = config.categories()
    countries = config.countries()

    cat_map: Dict[str, List[Cluster]] = defaultdict(list)
    country_map: Dict[str, List[Cluster]] = defaultdict(list)

    for c in clusters:
        for cat in _cluster_categories(c):
            if cat in cats:
                cat_map[cat].append(c)
        for country in _cluster_countries(c):
            if country in countries:
                country_map[country].append(c)

    # Category sections, ordered by config 'order'.
    category_sections: List[Section] = []
    for key in sorted(cats, key=lambda k: cats[k].get("order", 99)):
        cl = sorted(cat_map.get(key, []), key=_rank_key)[:MAX_CLUSTERS_PER_CATEGORY]
        if cl:
            category_sections.append(Section(key=key, label=cats[key]["label"], clusters=cl))

    # Country sections, ordered by config 'order'.
    country_sections: List[Section] = []
    for key in sorted(countries, key=lambda k: countries[k].get("order", 99)):
        cl = sorted(country_map.get(key, []), key=_rank_key)[:MAX_CLUSTERS_PER_COUNTRY]
        if cl:
            spec = countries[key]
            country_sections.append(
                Section(key=key, label=spec["label"], clusters=cl, group=spec.get("group", ""))
            )

    return Brief(
        generated_at=datetime.now(timezone.utc),
        category_sections=category_sections,
        country_sections=country_sections,
    )


def build(lookback_hours: int, output_dir: str, no_ai: bool = False) -> Brief:
    print("==> Fetching sources")
    articles = fetch_all(lookback_hours=lookback_hours)

    print("==> Classifying")
    articles = classify(articles)

    print("==> Clustering")
    clusters = cluster_articles(articles)
    print(f"  {len(articles)} articles -> {len(clusters)} clusters")

    print("==> Assembling brief")
    brief = assemble_brief(clusters)
    brief.total_articles = len(articles)
    brief.total_clusters = len(clusters)

    print("==> Summarizing")
    summarizer = AISummarizer()
    if no_ai:
        summarizer.enabled = False
        summarizer.error = "AI disabled via --no-ai flag."
    run_summaries(brief, summarizer)

    print("==> Rendering")
    render_site(brief, output_dir)
    print(f"==> Done. Output written to {output_dir}/")
    return brief


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Diplomat Daily Briefing site.")
    parser.add_argument("--lookback-hours", type=int, default=30, help="Recency window (hours).")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs"),
        help="Output directory (served by GitHub Pages).",
    )
    parser.add_argument("--no-ai", action="store_true", help="Skip Claude summaries (links-only).")
    args = parser.parse_args()
    build(args.lookback_hours, args.output_dir, no_ai=args.no_ai)


if __name__ == "__main__":
    main()
