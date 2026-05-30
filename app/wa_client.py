"""Thin WhatsApp Cloud API client."""
import logging

import httpx

from app.config import WA_ACCESS_TOKEN, WA_API_VERSION, WA_PHONE_NUMBER_ID
from app.formatting import to_whatsapp

log = logging.getLogger(__name__)

BASE_URL = f"https://graph.facebook.com/{WA_API_VERSION}/{WA_PHONE_NUMBER_ID}"
HEADERS = {
    "Authorization": f"Bearer {WA_ACCESS_TOKEN}",
    "Content-Type": "application/json",
}


async def send_text(to: str, body: str) -> dict:
    body = to_whatsapp(body)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.post(f"{BASE_URL}/messages", headers=HEADERS, json=payload)
        if r.status_code >= 400:
            log.error("WA send_text failed status=%s body=%s", r.status_code, r.text)
        r.raise_for_status()
        return r.json()


async def download_media(media_id: str) -> tuple[bytes, str]:
    """Resolve a WhatsApp media id to (bytes, mime_type).

    Two hops: GET the media metadata for a short-lived URL, then GET that URL.
    Both require the access token.
    """
    auth = {"Authorization": f"Bearer {WA_ACCESS_TOKEN}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        meta = await client.get(
            f"https://graph.facebook.com/{WA_API_VERSION}/{media_id}", headers=auth)
        meta.raise_for_status()
        info = meta.json()
        media = await client.get(info["url"], headers=auth)
        media.raise_for_status()
        return media.content, info.get("mime_type", "audio/ogg")


async def mark_read(message_id: str) -> None:
    """Mark the inbound message read AND show a typing indicator.

    The typing bubble stays until we send our reply (or ~25s), so the user sees
    activity while the agent thinks instead of dead air.
    """
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(f"{BASE_URL}/messages", headers=HEADERS, json=payload)
            if r.status_code >= 400:
                log.warning("mark_read/typing failed status=%s body=%s", r.status_code, r.text)
        except httpx.HTTPError as e:
            log.warning("mark_read failed: %s", e)
