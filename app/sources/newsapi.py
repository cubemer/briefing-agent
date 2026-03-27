from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.models import Story

logger = logging.getLogger(__name__)

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

DEFAULT_QUERIES = [
    "geopolitics OR macroeconomics OR sanctions",
    "artificial intelligence OR LLM OR machine learning",
    "embedded systems OR RISC-V OR IoT",
    "SIGGRAPH OR GPU compute OR graphics research",
    "space launch OR NASA OR SpaceX",
]


async def fetch_newsapi(
    queries: list[str] | None = None,
    api_key: str = "",
) -> list[Story]:
    if not api_key:
        logger.warning("No NewsAPI key provided, skipping")
        return []

    queries = queries or DEFAULT_QUERIES
    stories: list[Story] = []

    async with httpx.AsyncClient(timeout=15.0) as client:
        for query in queries:
            try:
                resp = await client.get(
                    NEWSAPI_BASE,
                    params={
                        "q": query,
                        "sortBy": "publishedAt",
                        "pageSize": 10,
                        "apiKey": api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                for article in data.get("articles", []):
                    published = None
                    if article.get("publishedAt"):
                        try:
                            published = datetime.fromisoformat(
                                article["publishedAt"].replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

                    stories.append(
                        Story(
                            url=article.get("url", ""),
                            title=article.get("title", ""),
                            source="newsapi",
                            published_at=published,
                            description=article.get("description", "") or "",
                        )
                    )
            except httpx.HTTPError as e:
                logger.error("NewsAPI request failed for query '%s': %s", query, e)
            except Exception as e:
                logger.error("Unexpected error fetching NewsAPI: %s", e)

    return stories
