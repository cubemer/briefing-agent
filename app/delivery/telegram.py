from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4096


async def send_brief(text: str, bot_token: str, chat_id: str) -> bool:
    if not bot_token or not chat_id:
        logger.error("Telegram credentials not configured")
        return False

    url = TELEGRAM_API.format(token=bot_token)
    chunks = _split_message(text)

    async with httpx.AsyncClient(timeout=15.0) as client:
        for chunk in chunks:
            try:
                resp = await client.post(
                    url,
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                logger.error("Telegram send failed: %s", e)
                return False

    return True


async def send_failure_alert(
    error: str, bot_token: str, chat_id: str
) -> bool:
    text = f"⚠️ Brief failed. Check logs.\n\n`{error[:500]}`"
    return await send_brief(text, bot_token, chat_id)


def _split_message(text: str) -> list[str]:
    if len(text) <= MAX_MESSAGE_LEN:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= MAX_MESSAGE_LEN:
            chunks.append(text)
            break
        # Split at last newline before limit
        split_at = text.rfind("\n", 0, MAX_MESSAGE_LEN)
        if split_at == -1:
            split_at = MAX_MESSAGE_LEN
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
