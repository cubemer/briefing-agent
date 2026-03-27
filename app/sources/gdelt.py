from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.models import Story

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

DEFAULT_QUERIES = [
    "geopolitics sanctions conflict",
    "artificial intelligence regulation",
    "semiconductor chip export",
    "space launch satellite",
]


async def fetch_gdelt(
    queries: list[str] | None = None,
) -> list[Story]:
    queries = queries or DEFAULT_QUERIES
    stories: list[Story] = []

    async with httpx.AsyncClient(timeout=20.0) as client:
        for query in queries:
            try:
                resp = await client.get(
                    GDELT_DOC_API,
                    params={
                        "query": query,
                        "mode": "ArtList",
                        "maxrecords": 10,
                        "timespan": "24h",
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                for article in data.get("articles", []):
                    published = None
                    if article.get("seendate"):
                        try:
                            published = datetime.strptime(
                                article["seendate"], "%Y%m%dT%H%M%SZ"
                            ).replace(tzinfo=timezone.utc)
                        except ValueError:
                            pass

                    stories.append(
                        Story(
                            url=article.get("url", ""),
                            title=article.get("title", ""),
                            source="gdelt",
                            published_at=published,
                            description=article.get("title", ""),
                        )
                    )
            except httpx.HTTPError as e:
                logger.error("GDELT request failed for query '%s': %s", query, e)
            except Exception as e:
                logger.error("Unexpected error fetching GDELT: %s", e)

    return stories
