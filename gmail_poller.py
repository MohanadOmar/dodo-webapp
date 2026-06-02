import asyncio
import time
from datetime import datetime, timezone
from tools import get_emails, send_sms_to_mohanad
from agent import run_agent
from system_prompts import get_email_monitor_system_prompt

_last_checked = datetime.now(timezone.utc)


async def start_poller():
    global _last_checked
    print("[Gmail Poller] Started — checking every 60 minutes")

    # Wait 30s before first run so everything initialises
    await asyncio.sleep(30)

    while True:
        try:
            await check_new_emails()
        except Exception as e:
            print(f"[Gmail Poller Error] {e}")

        await asyncio.sleep(60 * 60)  # Every hour


async def check_new_emails():
    global _last_checked
    print(f"[Gmail Poller] Checking for emails since {_last_checked.isoformat()}")

    since_ts = int(_last_checked.timestamp())
    _last_checked = datetime.now(timezone.utc)

    emails = get_emails(max_results=20, query=f"is:unread after:{since_ts}")

    if not emails:
        print("[Gmail Poller] No new emails.")
        return

    print(f"[Gmail Poller] Found {len(emails)} new email(s).")

    for email in emails:
        summary = f"From: {email['from']}\nSubject: {email['subject']}\nSnippet: {email['snippet']}"

        # Email monitor agent — classify only, no tools needed
        decision = run_agent(
            user_message=summary,
            system_prompt=get_email_monitor_system_prompt(),
            tools=[],  # No tools for classification
        )

        print(f"[Gmail Poller] Decision for '{email['subject']}': {decision}")

        # IF node equivalent — only SMS if not SKIP
        if decision and decision.strip() != "SKIP":
            send_sms_to_mohanad(decision.strip())
            print(f"[Gmail Poller] SMS sent.")
