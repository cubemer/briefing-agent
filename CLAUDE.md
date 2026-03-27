# CLAUDE.md — Good Morning Brief Agent

## What this is

A personal agentic briefing system that wakes up at 5am, ingests news from multiple sources, filters for relevance, deduplicates against memory, and fires a tight bullet-point brief with links to a Telegram bot — before Juan hits Muay Thai.

This is not a toy. It is a portfolio-grade production agent built on the exact stack AI engineering roles hire for.

---

## Stack

| Layer | Tool |
|---|---|
| Language | Python |
| Agent framework | LangChain + LangGraph |
| LLM | Claude API (Haiku for summaries, Sonnet for synthesis) |
| News sources | NewsAPI, GDELT, curated RSS feeds |
| Memory | Pinecone (skip already-read stories) |
| Delivery | Telegram Bot API |
| Scheduler | fly.io cron |
| Hosting | fly.io |
| API layer | FastAPI |

---

## Topics to prioritize

The agent scores and filters all content against this list. Irrelevant noise gets dropped before synthesis.

1. Geopolitics / macro (high weight)
2. AI / ML / LLM research and tooling (high weight)
3. Embedded systems / IoT / low-level (C, Zig, RISC-V) (high weight)
4. SIGGRAPH / graphics / compute research (medium weight)
5. Space research and space contractors (medium weight)
6. Crypto / DeFi — only if macro-relevant (low weight, threshold gated)

---

## Agent pipeline (LangGraph nodes)

```
[ cron: 5:00am MT ]
        ↓
[ node 1: ingest ]
  - hit NewsAPI for topic queries
  - hit GDELT for geopolitical signals
  - parse curated RSS feeds
  - deduplicate raw stories by URL + title hash

        ↓
[ node 2: memory filter ]
  - embed each story
  - query Pinecone for similarity to past briefs
  - drop stories above similarity threshold (already read)
  - pass novel stories forward

        ↓
[ node 3: score + filter ]
  - claude haiku scores each story against topic weights
  - drop anything below relevance threshold
  - rank remaining stories

        ↓
[ node 4: completeness check ] ← LangGraph decision node
  - "is there enough signal across priority topics?"
  - if no → loop back to node 1 with expanded queries
  - if yes → continue

        ↓
[ node 5: summarize ]
  - claude haiku: one tight bullet per story + source link
  - no fluff, no filler

        ↓
[ node 6: synthesize ]
  - claude sonnet: brief TL;DR header (2-3 sentences max)
  - what matters today, why it matters

        ↓
[ node 7: store + deliver ]
  - embed final brief → store in Pinecone (prevents future repeats)
  - fire to Telegram bot
  - done before 5:10am
```

---

## Output format

```
🌅 BRIEF — [date]

[2-3 sentence synthesis of what's actually important today]

---

• [headline] — [one sentence context] → [link]
• [headline] — [one sentence context] → [link]
• [headline] — [one sentence context] → [link]
...

[5-8 bullets max. no more.]
```

---

## Delivery

- **Channel:** Telegram bot
- **Time:** 5:00am Mountain Time
- **Trigger:** fly.io cron job → hits FastAPI endpoint → kicks LangGraph pipeline
- **Fallback:** if pipeline fails, send a single Telegram message: "Brief failed. Check logs."

---

## Memory (Pinecone)

- Each delivered story is embedded and stored with timestamp
- TTL: 7 days (stories older than a week are fair game again)
- Similarity threshold: 0.85 (aggressive dedup — if it's close, skip it)
- Index name: `morning-brief`

---

## RSS feeds to configure

Populate in `config/feeds.yaml`. Starting suggestions:

```yaml
feeds:
  - name: Ars Technica (tech/space)
    url: https://feeds.arstechnica.com/arstechnica/index
  - name: IEEE Spectrum (embedded/systems)
    url: https://spectrum.ieee.org/feeds/feed.rss
  - name: The Planetary Society
    url: https://www.planetary.org/articles/rss
  - name: Hacker News (top)
    url: https://hnrss.org/frontpage
  - name: Embedded.fm blog
    url: https://embedded.fm/blog/rss
```

Add more in `config/feeds.yaml` as you find good ones.

---

## Environment variables

```
ANTHROPIC_API_KEY=
NEWSAPI_KEY=
PINECONE_API_KEY=
PINECONE_ENV=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Project structure

```
briefing-agent/
├── CLAUDE.md
├── fly.toml
├── Dockerfile
├── requirements.txt
├── config/
│   └── feeds.yaml
├── app/
│   ├── main.py          # FastAPI entrypoint
│   ├── agent/
│   │   ├── graph.py     # LangGraph pipeline definition
│   │   ├── nodes.py     # each node as a function
│   │   └── prompts.py   # all claude prompts live here
│   ├── sources/
│   │   ├── newsapi.py
│   │   ├── gdelt.py
│   │   └── rss.py
│   ├── memory/
│   │   └── pinecone.py
│   └── delivery/
│       └── telegram.py
└── tests/
    └── test_nodes.py
```

---

## Success criteria

- Fires at 5:00am MT every day without babysitting
- Brief is read in under 2 minutes
- Zero stories Juan already read yesterday
- No hallucinated summaries — every bullet links to the real source
- If it fails, Juan knows immediately via Telegram

---

## Why this exists

Replacement for doomscrolling. Signal over noise. Ships as a portfolio piece demonstrating: agentic LangGraph pipelines, multi-source ingestion, vector memory, scheduled production deployment. Exact stack that $150k+ AI engineering roles are hiring for.

---

*"before enlightenment, carry water, chop wood. after enlightenment, carry water, chop wood."*
