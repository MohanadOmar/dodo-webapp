"""Inbound webhook from n8n.

Treats n8n input identically to an SMS — same agent, same tools, same brain.
The only difference: replies are sent via Twilio API instead of TwiML response.
"""
import os
from fastapi import APIRouter, Request, Header, HTTPException

from agent import run_agent
from system_prompts import get_sms_system_prompt
from tools import send_sms_to_mohanad, MOHANAD_PHONE

router = APIRouter()


def _check_auth(api_key: str):
    expected = os.environ.get("N8N_INCOMING_SECRET", "")
    if not expected or api_key != expected:
        raise HTTPException(401, "Unauthorized")


@router.post("/incoming")
async def n8n_incoming(request: Request, x_api_key: str = Header(None)):
    """Acts like an inbound SMS from Mohanad.

    Body: { "message": "any natural-language instruction or data" }

    Dodo runs the same agent loop it uses for SMS, with all the same tools.
    Whatever Dodo's reply is gets sent back to Mohanad as an SMS.
    """
    _check_auth(x_api_key)
    data = await request.json()
    message = (data.get("message") or "").strip()

    if not message:
        raise HTTPException(400, "Missing 'message' field")

    print(f"[n8n→Dodo] {message[:200]}")

    # Mark this as automated so Dodo skips confirmation prompts
    automated_message = f"[AUTOMATED — no confirmation needed] {message}"

    try:
        reply = run_agent(
            user_message=automated_message,
            system_prompt=get_sms_system_prompt(),
            phone_number=MOHANAD_PHONE,
        )
        print(f"[n8n→Dodo reply] {reply}")

        # Send Dodo's reply to Mohanad as SMS (just like the SMS path does)
        if reply:
            sms_result = send_sms_to_mohanad(reply)
            return {"success": True, "reply": reply, "sid": sms_result.get("sid")}

        return {"success": True, "reply": "", "note": "Dodo had nothing to say"}

    except Exception as e:
        print(f"[n8n→Dodo error] {e}")
        return {"success": False, "error": str(e)}
