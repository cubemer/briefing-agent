from __future__ import annotations

import asyncio
import json
import logging
import operator
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.prompts import (
    COMPLETENESS_PROMPT,
    SCORE_PROMPT,
    SUMMARIZE_PROMPT,
    SYNTHESIZE_PROMPT,
)
from app.config import settings
from app.delivery.telegram import send_brief, send_failure_alert
from app.memory.pinecone import BriefMemory
from app.models import BriefOutput, Story, StoryBullet, TOPIC_WEIGHTS
from app.sources.gdelt import fetch_gdelt
from app.sources.newsapi import fetch_newsapi
from app.sources.rss import fetch_rss

logger = logging.getLogger(__name__)


class BriefingState(TypedDict):
    stories: Annotated[list[Story], operator.add]
    filtered_stories: list[Story]
    summaries: list[StoryBullet]
    synthesis: str
    final_brief: str
    retry_count: int
    expanded_queries: list[str]
    errors: Annotated[list[str], operator.add]
    route: str


def _get_haiku() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.scoring_model,
        api_key=settings.anthropic_api_key,
        max_tokens=1024,
    )


def _get_sonnet() -> ChatAnthropic:
    return ChatAnthropic(
        model=settings.synthesis_model,
        api_key=settings.anthropic_api_key,
        max_tokens=1024,
    )


async def ingest_node(state: BriefingState) -> dict:
    """Node 1: Ingest stories from all sources."""
    queries = state.get("expanded_queries") or None

    try:
        newsapi_stories, gdelt_stories, rss_stories = await asyncio.gather(
            fetch_newsapi(queries=queries, api_key=settings.newsapi_key),
            fetch_gdelt(queries=queries),
            fetch_rss(),
        )
    except Exception as e:
        logger.error("Ingest failed: %s", e)
        return {"stories": [], "errors": [f"Ingest error: {e}"]}

    all_stories = newsapi_stories + gdelt_stories + rss_stories

    # Deduplicate by content_hash
    seen_hashes: set[str] = set()
    # Include hashes from previously ingested stories (retry case)
    for s in state.get("stories", []):
        seen_hashes.add(s.content_hash)

    unique: list[Story] = []
    for story in all_stories:
        if story.content_hash not in seen_hashes and story.url:
            seen_hashes.add(story.content_hash)
            unique.append(story)

    logger.info("Ingested %d unique stories (%d total raw)", len(unique), len(all_stories))
    return {"stories": unique}


async def memory_filter_node(state: BriefingState) -> dict:
    """Node 2: Filter out stories we've already briefed on."""
    stories = state.get("stories", [])
    if not stories:
        return {"filtered_stories": []}

    try:
        memory = BriefMemory()
        novel = await memory.filter_seen(stories)
        logger.info("Memory filter: %d/%d stories are novel", len(novel), len(stories))
        return {"filtered_stories": novel}
    except Exception as e:
        logger.error("Memory filter failed, passing all stories through: %s", e)
        return {
            "filtered_stories": stories,
            "errors": [f"Memory filter error: {e}"],
        }


async def score_filter_node(state: BriefingState) -> dict:
    """Node 3: Score each story against topic weights and filter."""
    stories = state.get("filtered_stories", [])
    if not stories:
        return {"filtered_stories": []}

    llm = _get_haiku()
    scored: list[Story] = []

    for story in stories:
        try:
            prompt = SCORE_PROMPT.format(
                title=story.title, description=story.description
            )
            response = await llm.ainvoke(
                [SystemMessage(content="Return only valid JSON."), HumanMessage(content=prompt)]
            )
            data = json.loads(response.content)
            story.topic_scores = data.get("topic_scores", {})
            story.relevance_score = float(data.get("relevance_score", 0.0))

            if story.relevance_score >= settings.relevance_threshold:
                scored.append(story)
        except Exception as e:
            logger.error("Scoring failed for '%s': %s", story.title, e)

    # Sort by relevance descending
    scored.sort(key=lambda s: s.relevance_score, reverse=True)
    logger.info("Score filter: %d/%d stories pass threshold", len(scored), len(stories))
    return {"filtered_stories": scored}


async def completeness_check_node(state: BriefingState) -> dict:
    """Node 4: Check if we have enough signal to produce a brief."""
    stories = state.get("filtered_stories", [])
    retry_count = state.get("retry_count", 0)

    # If we've maxed out retries, proceed with what we have
    if retry_count >= settings.max_retries:
        logger.info("Max retries reached, proceeding with %d stories", len(stories))
        return {"route": "continue"}

    # Check coverage
    high_topics = {"geopolitics", "ai_ml", "embedded"}
    covered = set()
    for story in stories:
        for topic, score in story.topic_scores.items():
            if topic in high_topics and score > 0.3:
                covered.add(topic)

    has_enough_stories = len(stories) >= 3
    has_enough_coverage = len(covered) >= 2

    if has_enough_stories and has_enough_coverage:
        logger.info("Completeness check passed: %d stories, topics: %s", len(stories), covered)
        return {"route": "continue"}

    # Need more signal — generate expanded queries
    try:
        llm = _get_haiku()
        stories_desc = "\n".join(
            f"- {s.title} (topics: {s.topic_scores})" for s in stories
        )
        prompt = COMPLETENESS_PROMPT.format(stories=stories_desc)
        response = await llm.ainvoke(
            [SystemMessage(content="Return only valid JSON."), HumanMessage(content=prompt)]
        )
        data = json.loads(response.content)
        queries = data.get("suggested_queries", [])
    except Exception as e:
        logger.error("Completeness LLM call failed: %s", e)
        queries = list(high_topics - covered)

    logger.info("Completeness check: retrying with expanded queries: %s", queries)
    return {
        "route": "retry",
        "retry_count": retry_count + 1,
        "expanded_queries": queries,
    }


def route_completeness(state: BriefingState) -> str:
    """Router function for the completeness check conditional edge."""
    return state.get("route", "continue")


async def summarize_node(state: BriefingState) -> dict:
    """Node 5: Summarize each story into a bullet."""
    stories = state.get("filtered_stories", [])
    stories = stories[: settings.max_brief_bullets]  # Cap at max bullets

    llm = _get_haiku()
    summaries: list[StoryBullet] = []

    for story in stories:
        try:
            prompt = SUMMARIZE_PROMPT.format(
                title=story.title,
                description=story.description,
                url=story.url,
            )
            response = await llm.ainvoke(
                [SystemMessage(content="Return only valid JSON."), HumanMessage(content=prompt)]
            )
            data = json.loads(response.content)
            # Find the primary topic for this story
            primary_topic = max(
                story.topic_scores, key=story.topic_scores.get, default=""
            ) if story.topic_scores else ""

            summaries.append(
                StoryBullet(
                    headline=data.get("headline", story.title),
                    context=data.get("context", ""),
                    url=story.url,
                    topic=primary_topic,
                )
            )
        except Exception as e:
            logger.error("Summarize failed for '%s': %s", story.title, e)
            # Fallback: use raw title
            summaries.append(
                StoryBullet(
                    headline=story.title,
                    context=story.description[:100],
                    url=story.url,
                )
            )

    return {"summaries": summaries}


async def synthesize_node(state: BriefingState) -> dict:
    """Node 6: Generate TL;DR synthesis."""
    summaries = state.get("summaries", [])
    if not summaries:
        return {"synthesis": "No significant stories today."}

    llm = _get_sonnet()
    bullets_text = "\n".join(
        f"• {b.headline} — {b.context}" for b in summaries
    )
    prompt = SYNTHESIZE_PROMPT.format(bullets=bullets_text)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"synthesis": response.content}
    except Exception as e:
        logger.error("Synthesis failed: %s", e)
        return {
            "synthesis": "Brief synthesis unavailable.",
            "errors": [f"Synthesis error: {e}"],
        }


async def store_deliver_node(state: BriefingState) -> dict:
    """Node 7: Store in Pinecone and deliver via Telegram."""
    summaries = state.get("summaries", [])
    synthesis = state.get("synthesis", "")
    errors = state.get("errors", [])

    # If no summaries and we have errors, send failure alert
    if not summaries:
        error_msg = "; ".join(errors) if errors else "No stories passed filters"
        await send_failure_alert(
            error_msg, settings.telegram_bot_token, settings.telegram_chat_id
        )
        return {"final_brief": "", "errors": [error_msg]}

    # Format the brief
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    brief = BriefOutput(date=today, synthesis=synthesis, bullets=summaries)
    formatted = brief.format()

    # Store in Pinecone
    try:
        memory = BriefMemory()
        urls = [b.url for b in summaries]
        await memory.store_brief(formatted, urls)
        await memory.store_stories(state.get("filtered_stories", []))
        await memory.cleanup_old()
    except Exception as e:
        logger.error("Memory storage failed: %s", e)

    # Send to Telegram
    success = await send_brief(
        formatted, settings.telegram_bot_token, settings.telegram_chat_id
    )
    if not success:
        logger.error("Telegram delivery failed")

    return {"final_brief": formatted}
