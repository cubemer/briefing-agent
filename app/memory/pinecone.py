from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from pinecone import Pinecone

from app.config import settings
from app.models import Story

logger = logging.getLogger(__name__)

EMBED_MODEL = "multilingual-e5-large"


class BriefMemory:
    def __init__(self, pc: Pinecone | None = None):
        self._pc = pc or Pinecone(api_key=settings.pinecone_api_key)
        self._index = self._pc.Index(settings.pinecone_index_name)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        result = self._pc.inference.embed(
            model=EMBED_MODEL,
            inputs=texts,
            parameters={"input_type": "passage"},
        )
        return [item.values for item in result.data]

    def _embed_query(self, text: str) -> list[float]:
        result = self._pc.inference.embed(
            model=EMBED_MODEL,
            inputs=[text],
            parameters={"input_type": "query"},
        )
        return result.data[0].values

    async def filter_seen(self, stories: list[Story]) -> list[Story]:
        if not stories:
            return []

        novel: list[Story] = []
        for story in stories:
            try:
                text = f"{story.title} {story.description}"
                query_vec = self._embed_query(text)
                results = self._index.query(
                    vector=query_vec,
                    top_k=1,
                    include_metadata=False,
                )
                top_score = (
                    results.matches[0].score if results.matches else 0.0
                )
                if top_score < settings.similarity_threshold:
                    novel.append(story)
                else:
                    logger.debug("Skipping seen story: %s (%.2f)", story.title, top_score)
            except Exception as e:
                logger.error("Pinecone query failed for '%s': %s", story.title, e)
                novel.append(story)  # err on the side of inclusion

        return novel

    async def store_brief(self, brief_text: str, story_urls: list[str]) -> None:
        try:
            vectors = self._embed([brief_text])
            ts = int(time.time())
            self._index.upsert(
                vectors=[
                    {
                        "id": f"brief-{ts}",
                        "values": vectors[0],
                        "metadata": {
                            "type": "brief",
                            "timestamp": ts,
                            "urls": story_urls[:20],
                        },
                    }
                ]
            )
        except Exception as e:
            logger.error("Failed to store brief in Pinecone: %s", e)

    async def store_stories(self, stories: list[Story]) -> None:
        if not stories:
            return
        try:
            texts = [f"{s.title} {s.description}" for s in stories]
            vectors = self._embed(texts)
            ts = int(time.time())
            records = [
                {
                    "id": f"story-{s.content_hash[:16]}-{ts}",
                    "values": vec,
                    "metadata": {
                        "type": "story",
                        "url": s.url,
                        "title": s.title,
                        "timestamp": ts,
                    },
                }
                for s, vec in zip(stories, vectors)
            ]
            self._index.upsert(vectors=records)
        except Exception as e:
            logger.error("Failed to store stories in Pinecone: %s", e)

    async def cleanup_old(self, days: int | None = None) -> None:
        ttl = days or settings.memory_ttl_days
        cutoff = int(time.time()) - (ttl * 86400)
        try:
            # Delete vectors older than TTL using metadata filter
            self._index.delete(
                filter={"timestamp": {"$lt": cutoff}}
            )
            logger.info("Cleaned up vectors older than %d days", ttl)
        except Exception as e:
            logger.error("Pinecone cleanup failed: %s", e)
