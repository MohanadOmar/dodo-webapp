"""Whapi inbound webhook handler — routes WhatsApp messages to the agent."""
import os
import requests
from fastapi import APIRouter, Request

from agent import run_agent
from system_prompts import get_client_web_system_prompt
from tools import get_supabase

router = APIRouter()

WHAPI_SEND_URL = "https://gate.whapi.cloud/messages/text"


def _send_whatsapp_reply(to: str, message: str) -> None:
    api_key = os.environ.get("WHAPI_API_KEY", "")
    phone = to.replace("@s.whatsapp.net", "").replace("@c.us", "").lstrip("+")
    try:
        requests.post(
            WHAPI_SEND_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"to": f"{phone}@s.whatsapp.net", "body": message},
            timeout=15,
        )
    except Exception as e:
        print(f"[WhatsApp] Failed to send reply to {phone}: {e}")


def _lookup_user_by_whatsapp(phone: str):
    """Try to match the inbound phone against whatsapp_number in client_profiles.
    Tries exact match, then with '+' prefix, then without '+' prefix."""
    supabase = get_supabase()
    candidates = [phone, f"+{phone}", phone.lstrip("+")]
    for candidate in candidates:
        result = (
            supabase.table("client_profiles")
            .select("user_id, full_name, nickname, brief_about, messaging_channel")
            .eq("whatsapp_number", candidate)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
    return None


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return {"status": "ok"}

    messages = body.get("messages", [])
    if not messages:
        return {"status": "ok"}

    for msg in messages:
        # Skip non-text or outbound messages
        if msg.get("type") not in ("text",):
            continue
        if msg.get("from_me"):
            continue

        from_field = msg.get("from", "")
        phone = from_field.replace("@s.whatsapp.net", "").replace("@c.us", "")

        text_obj = msg.get("text", {})
        text = (text_obj.get("body", "") if isinstance(text_obj, dict) else "") or msg.get("body", "")
        if not text.strip():
            continue

        profile = _lookup_user_by_whatsapp(phone)
        if not profile:
            print(f"[WhatsApp] Unknown number {phone}, ignoring")
            continue

        user_id = profile["user_id"]
        client_name = profile.get("nickname") or profile.get("full_name") or "there"
        brief_about = profile.get("brief_about") or ""
        messaging_channel = profile.get("messaging_channel") or "whatsapp"

        print(f"[WhatsApp] {phone} → user={user_id[:8]} msg={text[:80]}")

        system_prompt = get_client_web_system_prompt(client_name, brief_about, messaging_channel)

        try:
            reply = run_agent(
                user_message=text,
                system_prompt=system_prompt,
                phone_number=f"wa:{phone}",
                user_id=user_id,
            )
        except Exception as e:
            print(f"[WhatsApp] Agent error for {phone}: {e}")
            continue

        if reply:
            _send_whatsapp_reply(phone, reply)
            print(f"[WhatsApp] Replied to {phone}: {reply[:80]}")

    return {"status": "ok"}
