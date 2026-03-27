from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import yaml

from app.models import Story

logger = logging.getLogger(__name__)


def _parse_feed(name: str, url: str) -> list[Story]:
    stories: list[Story] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            published = None
            if hasattr(entry, "published"):
                try:
                    published = parsedate_to_datetime(entry.published)
                except Exception:
                    pass

            stories.append(
                Story(
                    url=entry.get("link", ""),
                    title=entry.get("title", ""),
                    source="rss",
                    published_at=published,
                    description=entry.get("summary", "") or "",
                )
            )
    except Exception as e:
        logger.error("RSS parse failed for '%s': %s", name, e)
    return stories


async def fetch_rss(
    feeds_path: str = "config/feeds.yaml",
) -> list[Story]:
    path = Path(feeds_path)
    if not path.exists():
        logger.warning("Feeds config not found at %s", feeds_path)
        return []

    with open(path) as f:
        config = yaml.safe_load(f)

    feeds = config.get("feeds", [])
    if not feeds:
        return []

    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, _parse_feed, feed["name"], feed["url"])
        for feed in feeds
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    stories: list[Story] = []
    for result in results:
        if isinstance(result, list):
            stories.extend(result)
        elif isinstance(result, Exception):
            logger.error("RSS feed task failed: %s", result)

    return stories
