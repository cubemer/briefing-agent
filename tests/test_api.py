"""Tests for the FastAPI endpoints."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main_module
from app.main import RunStatus, app


@pytest.fixture(autouse=True)
def reset_run_state():
    """Reset global run state before and after each test."""
    main_module._run_state.update({
        "status": RunStatus.IDLE,
        "started_at": None,
        "finished_at": None,
        "bullets": 0,
        "errors": [],
    })
    yield
    main_module._run_state.update({
        "status": RunStatus.IDLE,
        "started_at": None,
        "finished_at": None,
        "bullets": 0,
        "errors": [],
    })


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_run_returns_accepted():
    mock_result = {
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

    with patch.object(main_module, "briefing_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/run")

        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # Let the background task complete
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_run_rejects_duplicate():
    main_module._run_state["status"] = RunStatus.RUNNING
    main_module._run_state["started_at"] = 1000.0

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/run")

    assert resp.status_code == 200
    assert resp.json()["status"] == "already_running"


@pytest.mark.asyncio
async def test_status_while_idle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


@pytest.mark.asyncio
async def test_status_after_completion():
    mock_result = {
        "stories": [],
        "filtered_stories": [],
        "summaries": [{"headline": "News", "context": "ctx", "url": "https://x.com", "topic": "ai_ml"}],
        "synthesis": "Summary",
        "final_brief": "formatted brief",
        "retry_count": 0,
        "expanded_queries": [],
        "errors": [],
        "route": "continue",
    }

    with patch.object(main_module, "briefing_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/run")
            await asyncio.sleep(0.2)
            resp = await client.get("/status")

    data = resp.json()
    assert data["status"] == "delivered"
    assert data["bullets"] == 1
    assert "duration_seconds" in data


@pytest.mark.asyncio
async def test_status_after_failure():
    with (
        patch.object(main_module, "briefing_graph") as mock_graph,
        patch.object(main_module, "send_failure_alert", new_callable=AsyncMock),
    ):
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Pipeline exploded"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/run")
            await asyncio.sleep(0.2)
            resp = await client.get("/status")

    data = resp.json()
    assert data["status"] == "failed"
    assert "Pipeline exploded" in data["errors"][0]
