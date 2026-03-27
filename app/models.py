from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, computed_field


TOPIC_WEIGHTS: dict[str, float] = {
    "geopolitics": 1.0,
    "ai_ml": 1.0,
    "embedded": 1.0,
    "graphics": 0.6,
    "space": 0.6,
    "crypto": 0.3,
}


class Story(BaseModel):
    url: str
    title: str
    source: str  # "newsapi" | "gdelt" | "rss"
    published_at: datetime | None = None
    description: str = ""
    topic_scores: dict[str, float] = {}
    relevance_score: float = 0.0

    @computed_field
    @property
    def content_hash(self) -> str:
        normalized = (self.url + self.title.lower().strip()).encode()
        return hashlib.sha256(normalized).hexdigest()


class StoryBullet(BaseModel):
    headline: str
    context: str
    url: str
    topic: str = ""


class BriefOutput(BaseModel):
    date: str
    synthesis: str
    bullets: list[StoryBullet]

    def format(self) -> str:
        lines = [
            f"🌅 BRIEF — {self.date}",
            "",
            self.synthesis,
            "",
            "---",
            "",
        ]
        for b in self.bullets:
            lines.append(f"• {b.headline} — {b.context} → {b.url}")
        return "\n".join(lines)
