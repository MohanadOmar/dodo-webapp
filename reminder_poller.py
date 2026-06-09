"""Reminder poller + Nightly to-do prompt.

- Checks Supabase every 60s for due reminders
- If reminder has a user_id → sends to that client's phone (from client_profiles)
- If reminder has no user_id → sends to Mohanad (personal SMS Dodo)
- At 10pm Chicago time, sends Mohanad's nightly to-do prompt
"""
import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tools import get_supabase, send_sms, send_sms_to_mohanad, get_client_phone, MOHANAD_PHONE
from agent import run_agent
from system_prompts import get_sms_system_prompt

TIMEZONE = ZoneInfo("America/Chicago")
BEDTIME_HOUR = int(os.environ.get("BEDTIME_HOUR", "22"))


async def start_reminder_poller():
    print("[Reminder Poller] Started — checking every 60 seconds")
    nightly_sent_today = False

    while True:
        try:
            now = datetime.now(TIMEZONE)
            now_iso = now.isoformat()

            # ─── Check due reminders ───────────────────────────────
            supabase = get_supabase()
            result = (
                supabase.table("reminders")
                .select("*")
                .eq("sent", False)
                .lte("remind_at", now_iso)
                .execute()
            )

            for reminder in (result.data or []):
                msg = reminder.get("message", "You have a reminder")
                rid = reminder.get("id")
                user_id = reminder.get("user_id")

                print(f"[Reminder] Sending: {msg} (user={user_id or 'mohanad'})")

                try:
                    if user_id:
                        # Client reminder — look up their phone
                        phone = get_client_phone(user_id)
                        if phone:
                            send_sms(to=phone, message=f"Reminder: {msg}")
                        else:
                            print(f"[Reminder] No phone for user {user_id}, skipping")
                    else:
                        # Personal — Mohanad
                        send_sms_to_mohanad(f"Reminder: {msg}")

                    supabase.table("reminders").update({"sent": True}).eq("id", rid).execute()
                    print(f"[Reminder] Sent and marked: {rid}")
                except Exception as e:
                    print(f"[Reminder] Failed to send {rid}: {e}")

            # ─── Nightly to-do prompt (10pm, Mohanad only) ────────
            is_bedtime = now.hour == BEDTIME_HOUR and now.minute < 2

            if is_bedtime and not nightly_sent_today:
                nightly_sent_today = True
                print("[Nightly] Triggering bedtime to-do prompt")
                try:
                    tomorrow = (now + timedelta(days=1)).strftime("%A, %B %d")
                    nightly_instruction = (
                        "[AUTOMATED — no confirmation needed] "
                        f"It's bedtime. Check my calendar for tomorrow ({tomorrow}) "
                        "and my pending Notion tasks. Then text me a short, natural summary: "
                        "1) What's on the calendar tomorrow, "
                        "2) What tasks are still pending, "
                        "3) Suggest 2-3 things I should prioritize or add for tomorrow based on what you see. "
                        "Keep it warm and brief — like a good assistant wrapping up the day. "
                        "Send the message via SMS to me."
                    )
                    reply = run_agent(
                        user_message=nightly_instruction,
                        system_prompt=get_sms_system_prompt(),
                        phone_number=MOHANAD_PHONE,
                        user_id=None,  # always Mohanad's personal Dodo
                    )
                    print(f"[Nightly] Reply: {reply}")
                    if reply and "send_sms" not in str(reply).lower():
                        send_sms_to_mohanad(reply)
                except Exception as e:
                    print(f"[Nightly] Error: {e}")

            if now.hour != BEDTIME_HOUR:
                nightly_sent_today = False

        except Exception as e:
            print(f"[Reminder Poller] Error: {e}")

        await asyncio.sleep(60)
