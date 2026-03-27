"""Tests for Telegram delivery module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.delivery.telegram import (
    MAX_MESSAGE_LEN,
    _split_message,
    send_brief,
    send_failure_alert,
)


# ============================================================
# _split_message
# ============================================================


def test_split_short_message():
    chunks = _split_message("Hello, world!")
    assert chunks == ["Hello, world!"]


def test_split_exactly_at_limit():
    text = "a" * MAX_MESSAGE_LEN
    chunks = _split_message(text)
    assert chunks == [text]


def test_split_long_message_at_newline():
    line = "x" * 100 + "\n"
    text = line * 50  # 5050 chars, over 4096 limit
    chunks = _split_message(text)

    assert len(chunks) == 2
    assert all(len(c) <= MAX_MESSAGE_LEN for c in chunks)
    # Reassembling should give back the content (minus stripped newlines)
    reassembled = "\n".join(chunks)
    assert "x" * 100 in reassembled


def test_split_long_message_no_newline():
    text = "a" * (MAX_MESSAGE_LEN + 500)
    chunks = _split_message(text)

    assert len(chunks) == 2
    assert len(chunks[0]) == MAX_MESSAGE_LEN
    assert len(chunks[1]) == 500


def test_split_preserves_all_content():
    lines = [f"Line {i}: {'x' * 80}" for i in range(60)]
    text = "\n".join(lines)
    chunks = _split_message(text)

    # Every original line should appear in exactly one chunk
    reassembled = "\n".join(chunks)
    for line in lines:
        assert line in reassembled


# ============================================================
# send_brief
# ============================================================


@pytest.mark.asyncio
async def test_send_brief_returns_false_without_credentials():
    result = await send_brief("Hello", "", "")
    assert result is False


@pytest.mark.asyncio
async def test_send_brief_returns_false_without_token():
    result = await send_brief("Hello", "", "some-chat-id")
    assert result is False


@pytest.mark.asyncio
async def test_send_brief_posts_to_telegram():
    mock_response = httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request("POST", "https://api.telegram.org"),
    )

    with patch("app.delivery.telegram.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_brief("Test brief", "fake-token", "12345")

    assert result is True
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert body["chat_id"] == "12345"
    assert body["text"] == "Test brief"
    assert body["parse_mode"] == "Markdown"
    assert body["disable_web_page_preview"] is True


@pytest.mark.asyncio
async def test_send_brief_splits_long_messages():
    long_text = "\n".join([f"Line {i}: {'x' * 100}" for i in range(60)])

    mock_response = httpx.Response(
        200,
        json={"ok": True},
        request=httpx.Request("POST", "https://api.telegram.org"),
    )

    with patch("app.delivery.telegram.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_brief(long_text, "fake-token", "12345")

    assert result is True
    assert mock_client.post.call_count >= 2


@pytest.mark.asyncio
async def test_send_brief_returns_false_on_http_error():
    with patch("app.delivery.telegram.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "403", request=httpx.Request("POST", "https://api.telegram.org"),
                response=httpx.Response(403),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_brief("Test", "fake-token", "12345")

    assert result is False


# ============================================================
# send_failure_alert
# ============================================================


@pytest.mark.asyncio
async def test_failure_alert_formats_message():
    with patch("app.delivery.telegram.send_brief", new_callable=AsyncMock, return_value=True) as mock_send:
        await send_failure_alert("Something broke", "fake-token", "12345")

    mock_send.assert_called_once()
    text = mock_send.call_args[0][0]
    assert "Brief failed" in text
    assert "Something broke" in text


@pytest.mark.asyncio
async def test_failure_alert_truncates_long_errors():
    long_error = "x" * 1000

    with patch("app.delivery.telegram.send_brief", new_callable=AsyncMock, return_value=True) as mock_send:
        await send_failure_alert(long_error, "fake-token", "12345")

    text = mock_send.call_args[0][0]
    # Error should be truncated to 500 chars
    assert len(text) < 600
