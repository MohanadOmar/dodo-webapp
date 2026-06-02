"""Web chat endpoint — same Dodo brain, no SMS costs."""
import os
import uuid
from fastapi import APIRouter, Request, HTTPException

from agent import run_agent
from system_prompts import get_web_system_prompt

router = APIRouter()


def _check_auth(request: Request):
    expected = os.environ.get("CHAT_API_KEY", "")
    if not expected:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != expected:
        raise HTTPException(401, "Unauthorized")


@router.post("/message")
async def chat_message(request: Request):
    _check_auth(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    message = (body.get("message") or "").strip()
    session_id = body.get("session_id") or str(uuid.uuid4())

    if not message:
        raise HTTPException(400, "Empty message")

    print(f"[Chat] session={session_id[:8]} msg={message[:100]}")

    try:
        reply = run_agent(
            user_message=message,
            system_prompt=get_web_system_prompt(),
            phone_number=f"web:{session_id}",
        )
        print(f"[Chat] reply={reply[:100]}")
    except Exception as e:
        print(f"[Chat Error] {e}")
        raise HTTPException(500, f"Agent error: {str(e)}")

    return {"reply": reply, "session_id": session_id}
