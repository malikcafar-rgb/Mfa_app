# Diplomat Daily Briefing

An automated daily intelligence-style briefing for diplomats. It aggregates news
from **reliable sources** — The New York Times, Foreign Affairs, the Financial
Times, and official government sites — then classifies, clusters, and (optionally)
summarizes the day's developments with Claude, and publishes a **static web
dashboard** plus a dated **"Today's Brief."**

## What it covers

- **Azerbaijan focus** — Ministry of Foreign Affairs and the President of Azerbaijan
  (official sites, with state-agency wire fallback).
- **Global developments** — conflicts, intelligence, military, technology, economy,
  and politics.
- **International relations theory** — analysis from Foreign Affairs, War on the
  Rocks, and E-International Relations, plus an AI-written IR-theory framing of the day.
- **Country watch** — a configurable watchlist (regional neighbors, great powers,
  Middle East, Central Asia, plus Spain, Switzerland, UK, US).

## How it works

```
fetch  ->  classify  ->  cluster  ->  summarize (Claude)  ->  render (static HTML)
```

- **fetch** (`aggregator/fetch.py`) — RSS via `feedparser`; official Azerbaijani
  sites (which block plain requests) via headless **Chromium/Playwright** with a
  realistic User-Agent; falls back to AzerTAC/Trend wire feeds if a site blocks.
- **classify** (`aggregator/classify.py`) — deterministic keyword tagging into
  categories and countries (config-driven; works with no API key).
- **cluster** (`aggregator/cluster.py`) — merges the same story across sources via
  fuzzy title matching (`rapidfuzz`).
- **summarize** (`aggregator/summarize.py`) — Claude writes per-story summaries,
  per-section briefs, an executive summary, and an IR-theory framing. **Degrades
  gracefully to links-only** if `ANTHROPIC_API_KEY` is missing.
- **render** (`aggregator/render.py`) — Jinja2 → self-contained, theme-aware,
  responsive HTML in `docs/` (served by GitHub Pages).

## Configuration (no code required)

All sources and topics live in `config/`:

- `config/sources.yaml` — feeds and scrape targets, each with a reliability tier
  (`official` / `wire` / `analysis`). Toggle `enabled:` to add/remove sources.
- `config/topics.yaml` — categories and their keyword sets.
- `config/countries.yaml` — the country/region watchlist and keywords.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium      # for official-site scraping

# Links-only (no API key needed):
python -m aggregator.build --no-ai --lookback-hours 48

# With AI summaries + analysis:
export ANTHROPIC_API_KEY=sk-ant-...
python -m aggregator.build --lookback-hours 30
```

Then open `docs/index.html` in your browser. Flags:

- `--lookback-hours N` — recency window (default 30).
- `--no-ai` — skip Claude (links-only).
- `--output-dir PATH` — output location (default `docs/`).
- `AGG_MODEL` env var — override the model (e.g. `claude-haiku-4-5-20251001` for
  lower cost; default `claude-opus-4-8`).

## Automated daily run (GitHub Actions + Pages)

The workflow `.github/workflows/daily-brief.yml` runs every weekday morning
(05:30 UTC; edit the `cron` for your timezone), rebuilds the site, and commits
`docs/`.

**One-time setup:**

1. **Add the API key** — repo **Settings → Secrets and variables → Actions →
   New repository secret**: `ANTHROPIC_API_KEY`. (Optional variable `AGG_MODEL`.)
2. **Enable Pages** — repo **Settings → Pages → Build and deployment → Deploy from
   a branch**, and pick this branch with the **`/docs`** folder.
3. **Run once manually** — **Actions → Daily Briefing → Run workflow** to verify,
   then read the dashboard at your GitHub Pages URL.

Without the secret the workflow still runs and produces a links-only briefing.

## Notes

- Free RSS provides **headlines and excerpts**, not paywalled full text. The app
  summarizes those and links to the originals — it does not reproduce or bypass
  paywalled content.
- Source coverage is entirely config-driven; some official government feeds are
  shipped disabled as stubs (Spain MAEC, Switzerland FDFA, France) — verify the
  feed URL and flip `enabled: true` to add them.
