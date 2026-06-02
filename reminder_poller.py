"""Reminder poller + Nightly to-do prompt.

- Checks Supabase every 60s for due reminders → texts Mohanad
- At 10pm Chicago time, sends a nightly to-do prompt
"""
import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from tools import get_supabase, send_sms_to_mohanad, MOHANAD_PHONE
from agent import run_agent
from system_prompts import get_sms_system_prompt

TIMEZONE = ZoneInfo("America/Chicago")
BEDTIME_HOUR = int(os.environ.get("BEDTIME_HOUR", "22"))  # 10pm default


async def start_reminder_poller():
    """Check for due reminders every 60 seconds."""
    print(f"[Reminder Poller] Started — checking every 60 seconds")
    nightly_sent_today = False

    while True:
        try:
            now = datetime.now(TIMEZONE)
            now_iso = now.isoformat()

            # ─── Check due reminders ───────────────────────────────
            supabase = get_supabase()
            result = supabase.table("reminders") \
                .select("*") \
                .eq("sent", False) \
                .lte("remind_at", now_iso) \
                .execute()

            due_reminders = result.data or []
            for reminder in due_reminders:
                msg = reminder.get("message", "You have a reminder")
                rid = reminder.get("id")
                print(f"[Reminder] Sending: {msg}")

                try:
                    send_sms_to_mohanad(f"Reminder: {msg}")
                    # Mark as sent
                    supabase.table("reminders").update({"sent": True}).eq("id", rid).execute()
                    print(f"[Reminder] Sent and marked: {rid}")
                except Exception as e:
                    print(f"[Reminder] Failed to send {rid}: {e}")

            # ─── Nightly to-do prompt (10pm) ───────────────────────
            is_bedtime = now.hour == BEDTIME_HOUR and now.minute < 2  # within first 2 min of the hour

            if is_bedtime and not nightly_sent_today:
                nightly_sent_today = True
                print("[Nightly] Triggering bedtime to-do prompt")

                try:
                    # Let Dodo generate the nightly summary using tools
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
                    )
                    print(f"[Nightly] Dodo's nightly reply: {reply}")

                    # The agent should have sent the SMS via send_sms tool,
                    # but if it didn't (returned text instead), send it ourselves
                    if reply and "send_sms" not in str(reply).lower():
                        send_sms_to_mohanad(reply)

                except Exception as e:
                    print(f"[Nightly] Error: {e}")

            # Reset the nightly flag after the bedtime hour passes
            if now.hour != BEDTIME_HOUR:
                nightly_sent_today = False

        except Exception as e:
            print(f"[Reminder Poller] Error: {e}")

        await asyncio.sleep(60)
