"""Load YAML configuration (sources, topics, countries)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict

import yaml

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def _load(name: str) -> Dict[str, Any]:
    path = os.path.join(CONFIG_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def sources() -> list[dict]:
    data = _load("sources.yaml")
    return [s for s in data.get("sources", []) if s.get("enabled", True)]


@lru_cache(maxsize=1)
def categories() -> Dict[str, dict]:
    return _load("topics.yaml").get("categories", {})


@lru_cache(maxsize=1)
def countries() -> Dict[str, dict]:
    return _load("countries.yaml").get("countries", {})
