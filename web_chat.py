"""Web chat endpoint — multi-tenant, per-user credentials."""
import os
import uuid
from fastapi import APIRouter, Request, HTTPException

from agent import run_agent
from system_prompts import get_web_system_prompt, get_client_web_system_prompt
from tools import get_supabase

router = APIRouter()


def _check_auth(request: Request):
    expected = os.environ.get("CHAT_API_KEY", "")
    if not expected:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != expected:
        raise HTTPException(401, "Unauthorized")


def _get_client_name(user_id: str) -> str:
    """Look up client's display name from Supabase auth.users."""
    try:
        supabase = get_supabase()
        result = supabase.auth.admin.get_user_by_id(user_id)
        if result and result.user:
            meta = result.user.user_metadata or {}
            return meta.get("full_name") or meta.get("name") or result.user.email or "there"
    except Exception:
        pass
    return "there"


@router.post("/message")
async def chat_message(request: Request):
    _check_auth(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "Empty message")

    # user_id comes from the frontend (Supabase auth session)
    user_id = body.get("user_id") or None
    session_id = body.get("session_id") or (f"web:{user_id}" if user_id else str(uuid.uuid4()))

    print(f"[Chat] user={user_id or 'anonymous'} session={session_id[:12]} msg={message[:100]}")

    # Build system prompt — personalised if we have a user_id
    if user_id:
        client_name = _get_client_name(user_id)
        system_prompt = get_client_web_system_prompt(client_name)
    else:
        system_prompt = get_web_system_prompt()

    try:
        reply = run_agent(
            user_message=message,
            system_prompt=system_prompt,
            phone_number=session_id,
            user_id=user_id,
        )
        print(f"[Chat] reply={reply[:100]}")
    except Exception as e:
        print(f"[Chat Error] {e}")
        raise HTTPException(500, f"Agent error: {str(e)}")

    return {"reply": reply, "session_id": session_id}
