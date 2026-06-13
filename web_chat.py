"""Web chat endpoint — multi-tenant, per-session, persistent history."""
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
    """Get the client's preferred name. Prefers nickname → full_name → email."""
    try:
        supabase = get_supabase()
        profile = (
            supabase.table("client_profiles")
            .select("nickname, full_name")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if profile.data:
            row = profile.data[0]
            name = row.get("nickname") or row.get("full_name")
            if name:
                return name
        user = supabase.auth.admin.get_user_by_id(user_id)
        if user and user.user:
            return user.user.email or "there"
    except Exception:
        pass
    return "there"


def _get_client_about(user_id: str) -> str:
    """Get the brief description the client wrote about themselves."""
    try:
        result = (
            get_supabase()
            .table("client_profiles")
            .select("brief_about")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("brief_about"):
            return result.data[0]["brief_about"]
    except Exception:
        pass
    return ""


def _get_client_communication_method(user_id: str) -> str:
    """Get the client's preferred communication method. Defaults to 'sms'."""
    try:
        result = (
            get_supabase()
            .table("client_profiles")
            .select("communication_method")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if result.data and result.data[0].get("communication_method"):
            return result.data[0]["communication_method"]
    except Exception:
        pass
    return "sms"


def _ensure_session(user_id: str, session_id: str | None) -> str:
    """If session_id is given, verify it. Otherwise create a new one."""
    supabase = get_supabase()
    if session_id:
        existing = (
            supabase.table("chat_sessions")
            .select("id")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return session_id
    # Create a new session
    new = supabase.table("chat_sessions").insert({
        "user_id": user_id,
        "title": "New chat",
    }).execute()
    return new.data[0]["id"]


def _save_message(session_id: str, user_id: str, role: str, content: str):
    """Persist a message to Supabase."""
    try:
        get_supabase().table("chat_messages").insert({
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
        }).execute()
        # Touch session.updated_at
        get_supabase().table("chat_sessions").update({
            "updated_at": "now()"
        }).eq("id", session_id).execute()
    except Exception as e:
        print(f"[Chat] Failed to save message: {e}")


def _update_session_title(session_id: str, first_user_message: str):
    """Auto-name the session from the first user message (truncated)."""
    title = first_user_message.strip().replace("\n", " ")
    if len(title) > 50:
        title = title[:47] + "..."
    try:
        get_supabase().table("chat_sessions").update({
            "title": title
        }).eq("id", session_id).execute()
    except Exception:
        pass


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

    user_id = body.get("user_id") or None
    session_id_in = body.get("session_id") or None

    if not user_id:
        raise HTTPException(400, "user_id is required")

    # Ensure session exists
    session_id = _ensure_session(user_id, session_id_in)

    # If this is the first message in the session, set its title
    supabase = get_supabase()
    msg_count = (
        supabase.table("chat_messages")
        .select("id", count="exact")
        .eq("session_id", session_id)
        .execute()
    )
    is_first_message = (msg_count.count or 0) == 0

    print(f"[Chat] user={user_id[:8]} session={session_id[:8]} msg={message[:80]}")

    # Save the user message first
    _save_message(session_id, user_id, "user", message)
    if is_first_message:
        _update_session_title(session_id, message)

    # Build system prompt with client context
    client_name = _get_client_name(user_id)
    client_about = _get_client_about(user_id)
    communication_method = _get_client_communication_method(user_id)
    system_prompt = get_client_web_system_prompt(client_name, client_about, communication_method)

    # Run the agent with this session as the conversation key
    try:
        reply = run_agent(
            user_message=message,
            system_prompt=system_prompt,
            phone_number=session_id,  # session_id is used as the memory key
            user_id=user_id,
            session_id=session_id,
        )
        print(f"[Chat] reply={reply[:100]}")
    except Exception as e:
        print(f"[Chat Error] {e}")
        raise HTTPException(500, f"Agent error: {str(e)}")

    # Save the assistant reply
    _save_message(session_id, user_id, "assistant", reply)

    return {"reply": reply, "session_id": session_id}


@router.get("/sessions")
async def list_sessions(request: Request, user_id: str):
    """List chat sessions for the sidebar."""
    _check_auth(request)
    if not user_id:
        raise HTTPException(400, "user_id is required")

    result = (
        get_supabase()
        .table("chat_sessions")
        .select("id, title, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"sessions": result.data or []}


@router.get("/messages")
async def get_messages(request: Request, user_id: str, session_id: str):
    """Get all messages for a session — used when client opens a past chat."""
    _check_auth(request)
    if not user_id or not session_id:
        raise HTTPException(400, "user_id and session_id are required")

    result = (
        get_supabase()
        .table("chat_messages")
        .select("role, content, created_at")
        .eq("session_id", session_id)
        .eq("user_id", user_id)
        .order("created_at", desc=False)
        .execute()
    )
    return {"messages": result.data or []}


@router.delete("/session")
async def delete_session(request: Request, user_id: str, session_id: str):
    """Delete a chat session and its messages."""
    _check_auth(request)
    if not user_id or not session_id:
        raise HTTPException(400, "user_id and session_id are required")

    get_supabase().table("chat_sessions").delete().eq(
        "id", session_id
    ).eq("user_id", user_id).execute()
    return {"success": True, "deleted": session_id}


@router.post("/connection-update")
async def connection_update(request: Request):
    """
    Called by the frontend after a successful integration connect/disconnect.
    Posts a system note into the user's most recent session so Dodo's
    context reflects the change immediately.
    """
    _check_auth(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    user_id = body.get("user_id")
    integration = body.get("integration")
    action = body.get("action", "connected")  # "connected" or "disconnected"

    if not user_id or not integration:
        raise HTTPException(400, "user_id and integration are required")

    labels = {
        "gmail": "Gmail",
        "google_calendar": "Google Calendar",
        "google_contacts": "Google Contacts",
        "google_docs": "Google Docs",
        "google_sheets": "Google Sheets",
        "notion": "Notion",
    }
    label = labels.get(integration, integration)

    # Find the user's most recent session (if any)
    supabase = get_supabase()
    latest = (
        supabase.table("chat_sessions")
        .select("id")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not latest.data:
        return {"success": True, "note": "no active session"}

    session_id = latest.data[0]["id"]

    if action == "connected":
        note = f"System note: {label} is now connected. Try using it right away — no need to mention past limitations."
    else:
        note = f"System note: {label} has been disconnected by the user."

    _save_message(session_id, user_id, "system", note)

    # Clear in-memory cache so the next message reloads fresh history including this note
    from agent import _sessions
    _sessions.pop(session_id, None)

    return {"success": True, "session_id": session_id}
