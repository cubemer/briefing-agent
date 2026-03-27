"""Tests for the FastAPI endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_run_endpoint_success():
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

    with patch("app.main.briefing_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "delivered"
    assert data["bullets"] == 1


@pytest.mark.asyncio
async def test_run_endpoint_empty_brief():
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

    with patch("app.main.briefing_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value=mock_result)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/run")

    assert resp.status_code == 200
    assert resp.json()["status"] == "empty"


@pytest.mark.asyncio
async def test_run_endpoint_pipeline_failure():
    with (
        patch("app.main.briefing_graph") as mock_graph,
        patch("app.main.send_failure_alert", new_callable=AsyncMock) as mock_alert,
    ):
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("Pipeline exploded"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/run")

    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert "Pipeline exploded" in resp.json()["error"]
    mock_alert.assert_called_once()
