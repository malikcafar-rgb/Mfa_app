"""Render the assembled Brief into a self-contained static HTML site."""

from __future__ import annotations

import os
import re
from collections import OrderedDict
from datetime import datetime
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import Brief, Section

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["domain"] = _domain
    return env


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url or "")
    return (m.group(1) if m else "").replace("www.", "")


def _grouped_countries(sections: List[Section]) -> "OrderedDict[str, List[Section]]":
    groups: "OrderedDict[str, List[Section]]" = OrderedDict()
    for s in sections:
        groups.setdefault(s.group or "Other", []).append(s)
    return groups


def _list_archive(briefs_dir: str) -> List[dict]:
    if not os.path.isdir(briefs_dir):
        return []
    entries = []
    for fn in os.listdir(briefs_dir):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.html$", fn)
        if m:
            date = m.group(1)
            try:
                display = datetime.strptime(date, "%Y-%m-%d").strftime("%A, %d %B %Y")
            except ValueError:
                display = date
            entries.append({"date": date, "display": display, "file": f"briefs/{fn}"})
    return sorted(entries, key=lambda e: e["date"], reverse=True)


def render_site(brief: Brief, output_dir: str) -> None:
    env = _env()
    briefs_dir = os.path.join(output_dir, "briefs")
    os.makedirs(briefs_dir, exist_ok=True)

    # Featured countries render as rich blocks (in config order); the rest stay
    # in the compact grouped grid.
    featured_countries = [s for s in brief.country_sections if s.featured]
    grouped = _grouped_countries([s for s in brief.country_sections if not s.featured])

    # Dashboard (index.html) — "in_page" links to same-page archive.
    dashboard_html = env.get_template("dashboard.html").render(
        brief=brief,
        featured_countries=featured_countries,
        grouped_countries=grouped,
        archive_link="archive.html",
        brief_link=f"briefs/{brief.date_str}.html",
    )
    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(dashboard_html)

    # Dated brief (briefs/YYYY-MM-DD.html) — relative paths go up one level.
    brief_html = env.get_template("brief.html").render(
        brief=brief,
        featured_countries=featured_countries,
        grouped_countries=grouped,
        home_link="../index.html",
        archive_link="../archive.html",
    )
    with open(os.path.join(briefs_dir, f"{brief.date_str}.html"), "w", encoding="utf-8") as fh:
        fh.write(brief_html)

    # Archive index (built from whatever dated briefs now exist on disk).
    archive_html = env.get_template("archive.html").render(
        entries=_list_archive(briefs_dir),
        home_link="index.html",
        brief=brief,
    )
    with open(os.path.join(output_dir, "archive.html"), "w", encoding="utf-8") as fh:
        fh.write(archive_html)

    # .nojekyll so GitHub Pages serves files verbatim.
    open(os.path.join(output_dir, ".nojekyll"), "w").close()
