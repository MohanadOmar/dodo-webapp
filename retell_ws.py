"""Retell AI WebSocket endpoint — Voice Dodo.

Same brain as SMS Dodo, but optimized for spoken conversation.
Retell sends transcribed speech, we run the agent, return text for TTS.
"""
import json
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agent import run_agent
from system_prompts import get_voice_system_prompt

router = APIRouter()


@router.websocket("/llm-websocket/{call_id}")
async def retell_websocket(ws: WebSocket, call_id: str):
    await ws.accept()
    print(f"[Retell] Connected: call_id={call_id}")

    # Use call_id as the session key (like phone_number for SMS)
    session_key = f"retell:{call_id}"

    try:
        # Send the greeting as soon as the connection opens
        greeting = {
            "response_id": 0,
            "content": "Hey, it's Dodo. How can I help?",
            "content_complete": True,
            "end_call": False,
        }
        await ws.send_text(json.dumps(greeting))

        while True:
            raw = await ws.receive_text()
            request = json.loads(raw)

            interaction_type = request.get("interaction_type", "")

            # "update_only" = partial transcript update, no response needed
            if interaction_type == "update_only":
                continue

            # "response_required" or "reminder_required" = caller finished speaking
            transcript = request.get("transcript", [])
            if not transcript:
                continue

            # Get the latest user utterance
            user_utterances = [u for u in transcript if u.get("role") == "user"]
            if not user_utterances:
                continue

            latest = user_utterances[-1].get("content", "").strip()
            if not latest:
                continue

            print(f"[Retell] User said: {latest}")

            # Check for end-call phrases
            end_phrases = ["goodbye", "bye", "hang up", "end call", "that's all", "thanks bye"]
            if latest.lower().strip().rstrip(".!") in end_phrases:
                farewell = {
                    "response_id": request.get("response_id", 0),
                    "content": "Alright, talk later. Bye!",
                    "content_complete": True,
                    "end_call": True,
                }
                await ws.send_text(json.dumps(farewell))
                break

            # Run the same agent as SMS — same tools, same brain
            try:
                reply = run_agent(
                    user_message=latest,
                    system_prompt=get_voice_system_prompt(),
                    phone_number=session_key,
                )
                print(f"[Retell] Dodo says: {reply}")
            except Exception as e:
                print(f"[Retell] Agent error: {e}")
                reply = "Sorry, I hit an error on that one. Try asking again."

            response = {
                "response_id": request.get("response_id", 0),
                "content": reply,
                "content_complete": True,
                "end_call": False,
            }
            await ws.send_text(json.dumps(response))

    except WebSocketDisconnect:
        print(f"[Retell] Disconnected: call_id={call_id}")
    except Exception as e:
        print(f"[Retell] Error: {e}")
