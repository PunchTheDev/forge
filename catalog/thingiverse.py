"""Thingiverse API client — fetch functional 3D-printable parts for the catalog.

Pulls "things" matching structural/mechanical queries, extracts metadata,
and returns normalized records suitable for driving spec generation.

Requires a Thingiverse API key (https://www.thingiverse.com/developers).
Set via THINGIVERSE_KEY env var or pass explicitly.

Usage:
    from catalog.thingiverse import ThingiverseClient

    client = ThingiverseClient(api_key="...")
    things = client.search("wall bracket mount", per_page=50)
    for thing in things:
        print(thing["id"], thing["name"], thing["dims_mm"])
"""

from __future__ import annotations

import os
import time
from typing import Iterator

import httpx


# Queries that consistently surface structural/functional parts
DEFAULT_QUERIES = [
    "wall mount bracket",
    "equipment mounting bracket",
    "pipe clamp bracket",
    "shelf support bracket",
    "industrial mount hardware",
    "structural bracket holder",
]

BASE_URL = "https://api.thingiverse.com"


class ThingiverseClient:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("THINGIVERSE_KEY")
        if not key:
            raise ValueError(
                "Thingiverse API key required. "
                "Set THINGIVERSE_KEY env var or pass api_key=..."
            )
        self.headers = {"Authorization": f"Bearer {key}"}
        self.client = httpx.Client(headers=self.headers, timeout=30.0)

    def search(
        self,
        query: str,
        per_page: int = 30,
        sort: str = "popular",
    ) -> list[dict]:
        """Search for things matching a query. Returns normalized records."""
        resp = self.client.get(
            f"{BASE_URL}/search/{httpx.utils.quote(query)}",
            params={"per_page": per_page, "sort": sort, "type": "things"},
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
        return [self._normalize(t) for t in hits if t.get("is_published")]

    def fetch_thing(self, thing_id: int) -> dict:
        """Fetch full metadata for a single thing."""
        resp = self.client.get(f"{BASE_URL}/things/{thing_id}")
        resp.raise_for_status()
        return self._normalize(resp.json())

    def bulk_fetch(
        self,
        queries: list[str] | None = None,
        per_query: int = 50,
        delay_s: float = 0.5,
    ) -> Iterator[dict]:
        """Yield unique things across multiple queries. Deduplicates by thing ID."""
        seen: set[int] = set()
        for q in (queries or DEFAULT_QUERIES):
            try:
                results = self.search(q, per_page=per_query)
            except httpx.HTTPError as exc:
                print(f"[thingiverse] search '{q}' failed: {exc}")
                continue
            for thing in results:
                tid = thing["id"]
                if tid not in seen:
                    seen.add(tid)
                    yield thing
            time.sleep(delay_s)

    def _normalize(self, raw: dict) -> dict:
        """Strip Thingiverse thing to the fields we care about."""
        # Thumbnail and full image URLs
        thumbnail = raw.get("thumbnail") or raw.get("default_image", {}).get("url", "")

        # Tags → flat list of lowercase strings
        tags = [t["name"].lower() for t in raw.get("tags", []) if isinstance(t, dict)]

        return {
            "id": raw["id"],
            "name": raw.get("name", ""),
            "description": _strip_html(raw.get("description", "")),
            "url": raw.get("public_url", f"https://www.thingiverse.com/thing:{raw['id']}"),
            "thumbnail": thumbnail,
            "tags": tags,
            "like_count": raw.get("like_count", 0),
            "collect_count": raw.get("collect_count", 0),
            "category": raw.get("categories", [{}])[0].get("name", "") if raw.get("categories") else "",
        }

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "ThingiverseClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()
