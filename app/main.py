import logging

from fastapi import FastAPI

from app.agent.graph import briefing_graph
from app.agent.nodes import BriefingState
from app.config import settings
from app.delivery.telegram import send_failure_alert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Morning Brief Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/run")
async def run_brief():
    initial_state: BriefingState = {
        "stories": [],
        "filtered_stories": [],
        "summaries": [],
        "synthesis": "",
        "final_brief": "",
        "retry_count": 0,
        "expanded_queries": [],
        "errors": [],
        "route": "",
    }

    try:
        result = await briefing_graph.ainvoke(initial_state)
        return {
            "status": "delivered" if result.get("final_brief") else "empty",
            "bullets": len(result.get("summaries", [])),
            "errors": result.get("errors", []),
        }
    except Exception as e:
        logger.exception("Pipeline failed")
        await send_failure_alert(
            str(e), settings.telegram_bot_token, settings.telegram_chat_id
        )
        return {"status": "failed", "error": str(e)}
