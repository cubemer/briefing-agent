SCORE_PROMPT = """\
You are a news relevance scorer. Given a news story, score it against each topic on a 0.0–1.0 scale.

Topics and their weights:
- geopolitics (weight: 1.0): macro geopolitics, sanctions, conflict, trade, diplomacy
- ai_ml (weight: 1.0): AI/ML research, LLMs, tooling, regulation
- embedded (weight: 1.0): embedded systems, IoT, low-level (C, Zig, RISC-V), hardware
- graphics (weight: 0.6): SIGGRAPH, GPU compute, graphics/rendering research
- space (weight: 0.6): space research, launches, NASA, ESA, space contractors
- crypto (weight: 0.3): crypto/DeFi — only score high if macro-relevant

Return JSON with:
- topic_scores: dict mapping each topic name to a float 0.0-1.0
- relevance_score: single float 0.0-1.0 representing overall relevance (weighted by topic weights)

Story title: {title}
Story description: {description}
"""

SUMMARIZE_PROMPT = """\
You are a concise news summarizer. Given a news story, produce:
- headline: a tight, informative headline (max 12 words)
- context: one sentence of context explaining why this matters

Rules:
- No fluff, no filler, no opinions
- Do not hallucinate — only reference information from the provided story
- Keep it factual and direct

Story title: {title}
Story description: {description}
Story URL: {url}
"""

SYNTHESIZE_PROMPT = """\
You are a morning briefing synthesizer. Given today's top stories, write a 2-3 sentence TL;DR.

Rules:
- What matters today and why it matters
- Be direct — no "today's brief covers..." meta-talk
- Connect dots across stories if there's a meaningful thread
- No fluff

Today's stories:
{bullets}
"""

COMPLETENESS_PROMPT = """\
You are evaluating whether a news brief has enough signal. Given the current stories and their topic coverage, determine:

1. Are at least 2 of the 3 high-priority topics (geopolitics, ai_ml, embedded) represented?
2. Are there at least 3 stories total?

If both conditions are met, the brief is complete.
If not, suggest 2-3 expanded search queries that could fill the gaps.

Return JSON with:
- complete: boolean
- suggested_queries: list of strings (empty if complete)
- reasoning: one sentence explaining your decision

Current stories:
{stories}
"""
