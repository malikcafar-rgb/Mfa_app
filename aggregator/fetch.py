"""Fetch and normalize articles from RSS feeds and official (scraped) sites."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import feedparser
from dateutil import parser as dateparser

from . import config
from .models import Article

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Keywords used to filter a generic wire feed (AzerTAC/Trend) down to
# MFA / presidential coverage when official sites can't be scraped.
AZ_OFFICIAL_KEYWORDS = [
    "president", "aliyev", "foreign ministry", "mfa", "foreign minister",
    "bayramov", "diplomat", "meeting", "official visit", "statement",
]


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_date(entry) -> Optional[datetime]:
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = dateparser.parse(val)
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, OverflowError, TypeError):
                continue
    # Fall back to the struct_time feedparser provides.
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return datetime(*st[:6], tzinfo=timezone.utc)
    return None


# Date patterns commonly embedded in scraped official-site headlines, e.g.
# "... Berlin 21 july 2026, 14:18" or "PRESS RELEASE 27 June 2026 18:51".
_DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b"),   # 21 July 2026
    re.compile(r"\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b"),  # July 21, 2026
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),                  # 2026-07-21
]


def _extract_date_from_text(text: str) -> Optional[datetime]:
    """Best-effort publish date parsed from a scraped headline; None if absent."""
    for rx in _DATE_PATTERNS:
        m = rx.search(text or "")
        if not m:
            continue
        try:
            dt = dateparser.parse(m.group(1))
        except (ValueError, OverflowError, TypeError):
            continue
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    return None


def _fetch_rss(src: dict) -> List[Article]:
    parsed = feedparser.parse(src["url"], agent=USER_AGENT)
    articles: List[Article] = []
    for entry in parsed.entries:
        title = _clean_html(entry.get("title", ""))
        link = entry.get("link", "")
        if not title or not link:
            continue
        published = _parse_date(entry)
        # Require a real date so the recency window is strict — an undated feed
        # item can't be verified as "today's news", so skip it.
        if published is None:
            continue
        summary = _clean_html(entry.get("summary", entry.get("description", "")))
        articles.append(
            Article(
                title=title,
                url=link,
                source=src["name"],
                tier=src.get("tier", "wire"),
                published=published,
                summary=summary[:600],
                category_hint=src.get("category", ""),
            )
        )
    return articles


def _fetch_scrape(src: dict) -> List[Article]:
    """Scrape an official site with Playwright/Chromium (realistic headers)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"  [scrape] Playwright not installed; skipping {src['name']}")
        return []

    # In CI, `playwright install chromium` provides the matching browser and no
    # override is needed. Elsewhere (e.g. a pre-provisioned Chromium), set
    # AGG_CHROMIUM_PATH to that binary.
    launch_kwargs = {"headless": True}
    chromium_path = os.environ.get("AGG_CHROMIUM_PATH")
    if chromium_path and os.path.exists(chromium_path):
        launch_kwargs["executable_path"] = chromium_path

    articles: List[Article] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch_kwargs)
            context = browser.new_context(user_agent=USER_AGENT, locale="en-US")
            page = context.new_page()
            page.goto(src["url"], timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)  # let client-side render settle

            # Generic extraction: collect anchors that look like news items.
            anchors = page.eval_on_selector_all(
                "a",
                """els => els.map(a => ({
                    text: (a.innerText || '').trim(),
                    href: a.href
                }))""",
            )
            browser.close()

        base_ok = _domain(src["url"])
        seen = set()
        for a in anchors:
            text = _clean_html(a.get("text", ""))
            href = a.get("href", "")
            # Heuristics: reasonable headline length, same-domain, not nav.
            if not href or len(text) < 30 or len(text) > 220:
                continue
            if _domain(href) != base_ok:
                continue
            if href in seen:
                continue
            seen.add(href)
            # Use the real date if the headline carries one; otherwise leave it
            # unknown (None) rather than faking "now" — the page is newest-first,
            # so the top items below are the most recent regardless.
            articles.append(
                Article(
                    title=text,
                    url=href,
                    source=src["name"],
                    tier=src.get("tier", "official"),
                    published=_extract_date_from_text(text),
                    summary="",
                    category_hint=src.get("category", "azerbaijan"),
                )
            )
            # Keep only the newest items on the page (it lists newest-first).
            if len(articles) >= 12:
                break
    except Exception as exc:  # noqa: BLE001 — robustness: never let one site break the run
        print(f"  [scrape] {src['name']} failed ({exc}); will rely on wire fallback")
        return []

    return articles


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url)
    return (m.group(1) if m else "").replace("www.", "").lower()


def fetch_all(lookback_hours: int = 30) -> List[Article]:
    """Fetch every enabled source, de-dupe by URL, and window by recency."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    all_articles: List[Article] = []
    az_official_ok = False

    for src in config.sources():
        name = src["name"]
        try:
            if src["type"] == "rss":
                items = _fetch_rss(src)
            elif src["type"] == "scrape":
                items = _fetch_scrape(src)
                if items and src.get("category") == "azerbaijan":
                    az_official_ok = True
            else:
                items = []
        except Exception as exc:  # noqa: BLE001
            print(f"  [fetch] {name} error: {exc}")
            items = []

        print(f"  [fetch] {name}: {len(items)} items")
        all_articles.extend(items)
        time.sleep(0.3)  # be polite

    # If official Azerbaijani sites yielded nothing, promote relevant wire items.
    if not az_official_ok:
        for a in all_articles:
            if a.category_hint == "azerbaijan" and a.tier == "wire":
                text = f"{a.title} {a.summary}".lower()
                if any(k in text for k in AZ_OFFICIAL_KEYWORDS):
                    a.tier = "official"  # surface it in the priority section

    # De-dupe by URL.
    seen = set()
    deduped: List[Article] = []
    for a in all_articles:
        if a.url in seen:
            continue
        seen.add(a.url)
        deduped.append(a)

    # Recency window (keep undated items — official scrapes often lack dates).
    windowed = [a for a in deduped if a.published is None or a.published >= cutoff]
    print(f"  [fetch] total {len(all_articles)} -> {len(deduped)} unique -> {len(windowed)} within {lookback_hours}h")
    return windowed
