import json
import os
from collections import defaultdict
from anthropic import Anthropic
from tools import (
    get_emails, create_draft, send_email, reply_to_email, add_label,
    get_calendar_events, create_calendar_event,
    get_notion_tasks, update_notion_task, create_notion_task,
    send_sms, search_knowledge_base,
    search_contacts, create_contact, update_contact,
    list_recent_docs, read_doc, create_doc, append_to_doc,
    list_recent_sheets, read_sheet, create_sheet, append_row, update_cell,
    web_search,
    create_reminder, list_reminders, delete_reminder,
)
from workflow_engine import WORKFLOW_TOOLS, WORKFLOW_FUNCS

# Claude Sonnet 4.6 — best balance of accuracy + cost for tool-use agents
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

# ─── Tool definitions ────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_emails",
            "description": "Read emails from Mohanad's Gmail inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "Max emails to return (default 5)"},
                    "query": {"type": "string", "description": "Gmail search query (default: is:unread)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft",
            "description": "Create an email draft. Use for 'draft', 'write', 'compose' — never for 'send'.",
            "parameters": {
                "type": "object",
                "required": ["to", "subject", "body"],
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email. ONLY use when user explicitly says 'send'.",
            "parameters": {
                "type": "object",
                "required": ["to", "subject", "body"],
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reply_to_email",
            "description": "Reply to an existing email thread. Requires the original message ID.",
            "parameters": {
                "type": "object",
                "required": ["message_id", "body"],
                "properties": {
                    "message_id": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_label",
            "description": "Add a label to a Gmail message.",
            "parameters": {
                "type": "object",
                "required": ["message_id", "label_name"],
                "properties": {
                    "message_id": {"type": "string"},
                    "label_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get upcoming events from Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {"type": "string", "description": "ISO datetime start"},
                    "time_max": {"type": "string", "description": "ISO datetime end"},
                    "max_results": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Create a new Google Calendar event.",
            "parameters": {
                "type": "object",
                "required": ["title", "start"],
                "properties": {
                    "title": {"type": "string"},
                    "start": {"type": "string", "description": "ISO datetime"},
                    "end": {"type": "string", "description": "ISO datetime (default: 30 min after start)"},
                    "description": {"type": "string"},
                    "location": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_notion_tasks",
            "description": "Get tasks from the EG23 Notion database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "return_all": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_notion_task",
            "description": "Update an existing Notion task. Requires page ID.",
            "parameters": {
                "type": "object",
                "required": ["page_id"],
                "properties": {
                    "page_id": {"type": "string"},
                    "status": {"type": "string"},
                    "title": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_notion_task",
            "description": "Create a new task in Notion.",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_sms",
            "description": "Send an SMS via Twilio.",
            "parameters": {
                "type": "object",
                "required": ["to", "message"],
                "properties": {
                    "to": {"type": "string", "description": "Phone number in E.164 format"},
                    "message": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search EG23's internal knowledge base in Supabase.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                },
            },
        },
    },
    # ─── Google Contacts ───────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "search_contacts",
            "description": "Search Google Contacts by name, email, or phone. Use this when the user mentions a person by name and you need their contact info.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Name, email, or phone fragment"},
                    "max_results": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_contact",
            "description": "Add a new contact to Google Contacts.",
            "parameters": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "company": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_contact",
            "description": "Update an existing contact's email or phone. Get resource_name from search_contacts first.",
            "parameters": {
                "type": "object",
                "required": ["resource_name"],
                "properties": {
                    "resource_name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                },
            },
        },
    },
    # ─── Google Docs ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_recent_docs",
            "description": "List recent Google Docs, optionally filtered by name keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer"},
                    "query": {"type": "string", "description": "Filter docs by name keyword"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": "Read the full text content of a Google Doc. Get the doc_id from list_recent_docs.",
            "parameters": {
                "type": "object",
                "required": ["doc_id"],
                "properties": {
                    "doc_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_doc",
            "description": "Create a new Google Doc with optional initial content.",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_to_doc",
            "description": "Append text to the end of a Google Doc.",
            "parameters": {
                "type": "object",
                "required": ["doc_id", "text"],
                "properties": {
                    "doc_id": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
    },
    # ─── Google Sheets ─────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "list_recent_sheets",
            "description": "List recent Google Sheets, optionally filtered by name keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer"},
                    "query": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_sheet",
            "description": "Read data from a Google Sheet. Returns headers + rows. Get sheet_id from list_recent_sheets.",
            "parameters": {
                "type": "object",
                "required": ["sheet_id"],
                "properties": {
                    "sheet_id": {"type": "string"},
                    "range_name": {"type": "string", "description": "A1 notation like 'Sheet1!A1:E20'. Default is first sheet A1:Z100."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_sheet",
            "description": "Create a new Google Sheet with optional column headers.",
            "parameters": {
                "type": "object",
                "required": ["title"],
                "properties": {
                    "title": {"type": "string"},
                    "headers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Column headers for row 1",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_row",
            "description": "Append a row to a Google Sheet.",
            "parameters": {
                "type": "object",
                "required": ["sheet_id", "values"],
                "properties": {
                    "sheet_id": {"type": "string"},
                    "values": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Cell values left-to-right",
                    },
                    "sheet_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_cell",
            "description": "Update a single cell in a Google Sheet (e.g. mark deal status, change a value).",
            "parameters": {
                "type": "object",
                "required": ["sheet_id", "cell", "value"],
                "properties": {
                    "sheet_id": {"type": "string"},
                    "cell": {"type": "string", "description": "A1 notation like 'B5'"},
                    "value": {"type": "string"},
                    "sheet_name": {"type": "string"},
                },
            },
        },
    },
    # ─── Reminders ───────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "create_reminder",
            "description": "Create a timed reminder. Dodo will text Mohanad when the time comes. Use for 'remind me', 'don't let me forget', 'alert me at', etc.",
            "parameters": {
                "type": "object",
                "required": ["message", "remind_at"],
                "properties": {
                    "message": {"type": "string", "description": "What to remind about, e.g. 'Buy soap'"},
                    "remind_at": {"type": "string", "description": "ISO 8601 datetime with timezone, e.g. '2026-05-13T18:00:00-05:00'"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List upcoming reminders that haven't been sent yet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_sent": {"type": "boolean", "description": "Include already-sent reminders. Default false."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_reminder",
            "description": "Cancel/delete a reminder by its ID. Use list_reminders first to find the ID.",
            "parameters": {
                "type": "object",
                "required": ["reminder_id"],
                "properties": {
                    "reminder_id": {"type": "string"},
                },
            },
        },
    },
    # ─── Perplexity Web Search ─────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web in real-time using Perplexity. Use for any question needing current info: news, prices, events, company info, regulations, people, recent developments, market data, or anything Dodo doesn't already know.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query. Be specific: 'Texas infrastructure grants 2026' not 'grants'.",
                    },
                },
            },
        },
    },
    # ─── n8n Workflows are auto-injected below from workflows.py ───
]

# Append workflows from workflows.py — adding new ones doesn't require touching this file
TOOLS.extend(WORKFLOW_TOOLS)

TOOL_MAP = {
    "get_emails": get_emails,
    "create_draft": create_draft,
    "send_email": send_email,
    "reply_to_email": reply_to_email,
    "add_label": add_label,
    "get_calendar_events": get_calendar_events,
    "create_calendar_event": create_calendar_event,
    "get_notion_tasks": get_notion_tasks,
    "update_notion_task": update_notion_task,
    "create_notion_task": create_notion_task,
    "send_sms": send_sms,
    "search_knowledge_base": search_knowledge_base,
    "search_contacts": search_contacts,
    "create_contact": create_contact,
    "update_contact": update_contact,
    "list_recent_docs": list_recent_docs,
    "read_doc": read_doc,
    "create_doc": create_doc,
    "append_to_doc": append_to_doc,
    "list_recent_sheets": list_recent_sheets,
    "read_sheet": read_sheet,
    "create_sheet": create_sheet,
    "append_row": append_row,
    "update_cell": update_cell,
    "web_search": web_search,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
    "delete_reminder": delete_reminder,
}

# Merge in n8n workflows automatically
TOOL_MAP.update(WORKFLOW_FUNCS)

# ─── In-memory session store (keyed by phone number) ─────────────────────────

_sessions: dict[str, list] = defaultdict(list)
MAX_HISTORY = 20


def _convert_tools_to_anthropic(openai_tools: list) -> list:
    """OpenAI tool schemas -> Anthropic format.

    OpenAI: { type: "function", function: { name, description, parameters } }
    Claude: { name, description, input_schema }
    """
    converted = []
    for t in openai_tools:
        if t.get("type") == "function" and "function" in t:
            fn = t["function"]
            converted.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        else:
            # Already in Anthropic format
            converted.append(t)
    return converted


def run_agent(user_message: str, system_prompt: str, phone_number: str = None, tools: list = None) -> str:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = _sessions[phone_number] if phone_number else []

    # Anthropic uses 'user'/'assistant' roles; system is a separate param.
    # Filter out any 'system' or 'tool' entries from saved history (shouldn't be there, but safety).
    messages = [m for m in history if m.get("role") in ("user", "assistant")]
    messages.append({"role": "user", "content": user_message})

    active_tools_openai = TOOLS if tools is None else tools
    active_tools = _convert_tools_to_anthropic(active_tools_openai) if active_tools_openai else []

    final_text = ""

    while True:
        kwargs = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
            "messages": messages,
        }
        if active_tools:
            kwargs["tools"] = active_tools

        response = client.messages.create(**kwargs)

        # Append the assistant turn (Claude expects content to be the list of blocks)
        messages.append({
            "role": "assistant",
            "content": response.content,
        })

        # Check stop reason — if not tool_use, we're done
        if response.stop_reason != "tool_use":
            # Pull out the final text from any text blocks
            text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
            final_text = "\n".join(text_parts).strip()
            break

        # Run all tool_use blocks and append a single user message with tool_results
        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            name = block.name
            args = block.input or {}
            print(f"[Tool] {name}({args})")

            try:
                fn = TOOL_MAP.get(name)
                if not fn:
                    raise ValueError(f"Unknown tool: {name}")
                result = fn(**args)
            except Exception as e:
                result = {"error": str(e)}
                print(f"[Tool Error] {name}: {e}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        messages.append({
            "role": "user",
            "content": tool_results,
        })

    # Save to session memory (keep only text-form turns to avoid bloat)
    if phone_number:
        session = _sessions[phone_number]
        session.append({"role": "user", "content": user_message})
        session.append({"role": "assistant", "content": final_text})
        if len(session) > MAX_HISTORY:
            _sessions[phone_number] = session[-MAX_HISTORY:]

    return final_text
