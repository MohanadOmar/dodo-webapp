"""Whapi inbound webhook handler — routes WhatsApp messages to the agent."""
from fastapi import APIRouter, Request

from agent import run_agent
from messaging import send_message_via_wp
from system_prompts import get_client_web_system_prompt
from tools import get_supabase

router = APIRouter()


def _lookup_user_by_whatsapp(phone: str):
    """Try to match the inbound phone against phone_number in client_profiles.
    Tries exact match, then with '+' prefix, then without '+' prefix."""
    supabase = get_supabase()
    candidates = [phone, f"+{phone}", phone.lstrip("+")]
    for candidate in candidates:
        result = (
            supabase.table("client_profiles")
            .select("user_id, full_name, nickname, brief_about, communication_method")
            .eq("phone_number", candidate)
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
        communication_method = profile.get("communication_method") or "wp"

        print(f"[WhatsApp] {phone} → user={user_id[:8]} msg={text[:80]}")

        system_prompt = get_client_web_system_prompt(client_name, brief_about, communication_method)

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
            send_message_via_wp(phone, reply)
            print(f"[WhatsApp] Replied to {phone}: {reply[:80]}")

    return {"status": "ok"}
