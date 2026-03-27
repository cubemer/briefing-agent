# briefing-agent

A personal agentic briefing system. Fires at 5am MT, ingests news from multiple sources, filters for relevance, deduplicates against memory, and delivers a tight bullet-point brief to Telegram — before Muay Thai.

Replacement for doomscrolling. Signal over noise.

---

## What it does

Every morning at 5am the agent:

1. Pulls from NewsAPI, GDELT, and curated RSS feeds
2. Drops stories you already read (vector similarity against 7-day memory in Pinecone)
3. Scores remaining stories against priority topics via Claude Haiku
4. Checks if there's enough signal — loops back with expanded queries if not
5. Summarizes each story to one bullet with a source link
6. Synthesizes a 2-3 sentence TL;DR with Claude Sonnet
7. Fires the brief to Telegram

Total runtime: under 10 minutes. Brief readable in under 2.

---

## Output format

```
🌅 BRIEF — [date]

[2-3 sentence synthesis of what actually matters today]

---

• [headline] — [one sentence context] → [link]
• [headline] — [one sentence context] → [link]
...
```

5–8 bullets max.

---

## Topics

Scored and filtered in priority order:

- Geopolitics / macro (high)
- AI / ML / LLM research and tooling (high)
- Embedded systems / IoT / low-level — C, Zig, RISC-V (high)
- SIGGRAPH / graphics / compute research (medium)
- Space research and contractors (medium)
- Crypto / DeFi — only if macro-relevant (low, threshold gated)

---

## Stack

| Layer | Tool |
|---|---|
| Language | Python 3.12 |
| Agent framework | LangChain + LangGraph |
| LLM | Claude Haiku (scoring/summaries) + Sonnet (synthesis) |
| News sources | NewsAPI, GDELT, RSS |
| Memory / dedup | Pinecone (7-day TTL, 0.85 similarity threshold) |
| Delivery | Telegram Bot API |
| Hosting | fly.io |
| Scheduler | supercronic (in-container cron) |
| API layer | FastAPI |

---

## Project structure

```
briefing-agent/
├── app/
│   ├── main.py              # FastAPI entrypoint — POST /run, GET /status
│   ├── agent/
│   │   ├── graph.py         # LangGraph pipeline definition
│   │   ├── nodes.py         # 7-node pipeline implementation
│   │   └── prompts.py       # all Claude prompts
│   ├── sources/
│   │   ├── newsapi.py
│   │   ├── gdelt.py
│   │   └── rss.py
│   ├── memory/
│   │   └── pinecone.py      # embed, store, similarity filter
│   └── delivery/
│       └── telegram.py
├── config/
│   └── feeds.yaml           # RSS feed list
├── tests/                   # 80+ unit tests
├── crontab                  # fires POST /run at 5am MT
├── start.sh                 # launches supercronic + uvicorn
├── Dockerfile
├── fly.toml
└── requirements.txt
```

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

Set these as fly.io secrets: `fly secrets set KEY=value`

---

## Deploy

```bash
fly deploy
```

The machine runs 24/7 (`auto_stop_machines = off`). Supercronic inside the container handles the 5am trigger. If the pipeline fails, you get a Telegram message saying so.

---

## Run manually

```bash
curl -X POST https://morning-brief-agent.fly.dev/run
```

Check status:

```bash
curl https://morning-brief-agent.fly.dev/status
```
