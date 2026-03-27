import asyncio
import logging
import time
from enum import Enum

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


class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    DELIVERED = "delivered"
    EMPTY = "empty"
    FAILED = "failed"


_run_state: dict = {
    "status": RunStatus.IDLE,
    "started_at": None,
    "finished_at": None,
    "bullets": 0,
    "errors": [],
}


async def _run_pipeline():
    global _run_state
    _run_state = {
        "status": RunStatus.RUNNING,
        "started_at": time.time(),
        "finished_at": None,
        "bullets": 0,
        "errors": [],
    }

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
        _run_state.update({
            "status": RunStatus.DELIVERED if result.get("final_brief") else RunStatus.EMPTY,
            "finished_at": time.time(),
            "bullets": len(result.get("summaries", [])),
            "errors": result.get("errors", []),
        })
    except Exception as e:
        logger.exception("Pipeline failed")
        await send_failure_alert(
            str(e), settings.telegram_bot_token, settings.telegram_chat_id
        )
        _run_state.update({
            "status": RunStatus.FAILED,
            "finished_at": time.time(),
            "errors": [str(e)],
        })


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/run")
async def run_brief():
    if _run_state["status"] == RunStatus.RUNNING:
        elapsed = time.time() - (_run_state["started_at"] or time.time())
        return {"status": "already_running", "elapsed_seconds": round(elapsed)}

    asyncio.create_task(_run_pipeline())
    return {"status": "accepted", "message": "Pipeline started. GET /status to check progress."}


@app.get("/status")
async def get_status():
    result = {**_run_state, "status": _run_state["status"].value}
    if _run_state["started_at"] and _run_state["finished_at"]:
        result["duration_seconds"] = round(_run_state["finished_at"] - _run_state["started_at"], 1)
    elif _run_state["started_at"]:
        result["elapsed_seconds"] = round(time.time() - _run_state["started_at"], 1)
    return result
