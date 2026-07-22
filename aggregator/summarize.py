"""AI summarization via Claude, with graceful fallback to links-only mode.

If ANTHROPIC_API_KEY is unset or the API errors, every method degrades to a
no-op and the rest of the pipeline renders source excerpts + links instead.
"""

from __future__ import annotations

import json
import os
import re
from typing import List, Tuple

from .models import Brief, Cluster, Section

DEFAULT_MODEL = os.environ.get("AGG_MODEL", "claude-opus-4-8")
MAX_CLUSTERS_PER_SECTION = 6
MAX_OVERVIEW_HEADLINES = 18


class AISummarizer:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.client = None
        self.enabled = False
        self.error = ""

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            self.error = "ANTHROPIC_API_KEY not set — running in links-only mode."
            return
        try:
            import anthropic

            self.client = anthropic.Anthropic(api_key=api_key)
            self.enabled = True
        except ImportError:
            self.error = "anthropic SDK not installed — running in links-only mode."

    # -- low-level call -------------------------------------------------------
    def _complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "".join(parts).strip()

    @staticmethod
    def _extract_json(text: str):
        """Pull the first JSON object/array out of a model response."""
        text = text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=-1)
        if start == -1:
            return None
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            return None

    # -- per-section briefs + per-cluster summaries ---------------------------
    def summarize_section(self, section: Section) -> None:
        if not self.enabled or not section.clusters:
            return
        top = section.clusters[:MAX_CLUSTERS_PER_SECTION]
        listed = []
        for i, c in enumerate(top):
            src = c.lead.source
            excerpt = (c.excerpt or "")[:300]
            listed.append(f"[{i}] ({src}) {c.title}\n    {excerpt}")
        payload = "\n".join(listed)

        system = (
            "You are a senior intelligence analyst writing a concise, neutral "
            "daily brief for a diplomat. Be factual, non-sensational, and terse. "
            "Return ONLY valid JSON."
        )
        user = (
            f"Section: {section.label}\n\n"
            f"Stories:\n{payload}\n\n"
            "Return JSON of the form:\n"
            '{"brief": "<2-3 sentence what-matters synthesis for this section>", '
            '"clusters": [{"i": <index>, "summary": "<=25 word neutral summary"}]}\n'
            "Cover every listed index in clusters."
        )
        try:
            data = self._extract_json(self._complete(system, user, max_tokens=900))
        except Exception as exc:  # noqa: BLE001
            print(f"  [ai] section '{section.key}' failed: {exc}")
            return
        if not isinstance(data, dict):
            return
        section.ai_brief = str(data.get("brief", "")).strip()
        for item in data.get("clusters", []):
            try:
                idx = int(item.get("i"))
                if 0 <= idx < len(top):
                    top[idx].ai_summary = str(item.get("summary", "")).strip()
            except (TypeError, ValueError):
                continue

    # -- executive summary + IR-theory framing --------------------------------
    def summarize_overview(self, brief: Brief) -> Tuple[str, str]:
        if not self.enabled:
            return "", ""

        # Gather the strongest headlines across all category sections.
        headlines: List[str] = []
        for section in brief.category_sections:
            for c in section.clusters[:3]:
                headlines.append(f"- ({section.label}) {c.title}")
            if len(headlines) >= MAX_OVERVIEW_HEADLINES:
                break
        headlines = headlines[:MAX_OVERVIEW_HEADLINES]
        if not headlines:
            return "", ""

        system = (
            "You are the lead analyst compiling a diplomat's morning brief. "
            "Write with precision and restraint; no filler."
        )
        user = (
            "Top developments today:\n" + "\n".join(headlines) + "\n\n"
            "Write two things, separated by the exact line '---':\n"
            "1) EXECUTIVE SUMMARY: 4-6 sentences on the day's most consequential "
            "developments, prioritizing anything touching Azerbaijan and its region.\n"
            "2) IR-THEORY FRAMING: one paragraph analyzing the top developments "
            "through international-relations theory (realism, liberalism, "
            "constructivism, balance-of-power), naming the lens you apply."
        )
        try:
            out = self._complete(system, user, max_tokens=900)
        except Exception as exc:  # noqa: BLE001
            print(f"  [ai] overview failed: {exc}")
            return "", ""
        if "---" in out:
            exec_sum, framing = out.split("---", 1)
            return exec_sum.strip(), framing.strip()
        return out.strip(), ""


def run(brief: Brief, summarizer: AISummarizer) -> None:
    """Populate AI fields on the brief in place."""
    brief.ai_enabled = summarizer.enabled
    if not summarizer.enabled:
        print(f"  [ai] {summarizer.error}")
        return
    for section in brief.category_sections:
        summarizer.summarize_section(section)
    brief.executive_summary, brief.ir_framing = summarizer.summarize_overview(brief)
