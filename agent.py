import json
import os
from collections import defaultdict
from anthropic import Anthropic
from tools import (
    get_emails, create_draft, send_email, reply_to_email, add_label,
    get_calendar_events, create_calendar_event,
    get_notion_tasks, update_notion_task, create_notion_task,
    send_sms, send_sms_to_client,
    search_knowledge_base,
    search_contacts, create_contact, update_contact,
    list_recent_docs, read_doc, create_doc, append_to_doc,
    list_recent_sheets, read_sheet, create_sheet, append_row, update_cell,
    web_search,
    create_reminder, list_reminders, delete_reminder,
    IntegrationNotConnected,
)
from workflow_engine import WORKFLOW_TOOLS, WORKFLOW_FUNCS

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

TOOLS = [
    {"type": "function", "function": {"name": "get_emails", "description": "Read emails from the user's Gmail inbox.", "parameters": {"type": "object", "properties": {"max_results": {"type": "integer"}, "query": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "create_draft", "description": "Create an email draft.", "parameters": {"type": "object", "required": ["to", "subject", "body"], "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "send_email", "description": "Send an email. ONLY use when user explicitly says 'send'.", "parameters": {"type": "object", "required": ["to", "subject", "body"], "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "reply_to_email", "description": "Reply to an existing email thread.", "parameters": {"type": "object", "required": ["message_id", "body"], "properties": {"message_id": {"type": "string"}, "body": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "add_label", "description": "Add a label to a Gmail message.", "parameters": {"type": "object", "required": ["message_id", "label_name"], "properties": {"message_id": {"type": "string"}, "label_name": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_calendar_events", "description": "Get upcoming events from Google Calendar.", "parameters": {"type": "object", "properties": {"time_min": {"type": "string"}, "time_max": {"type": "string"}, "max_results": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "create_calendar_event", "description": "Create a new Google Calendar event.", "parameters": {"type": "object", "required": ["title", "start"], "properties": {"title": {"type": "string"}, "start": {"type": "string"}, "end": {"type": "string"}, "description": {"type": "string"}, "location": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_notion_tasks", "description": "Get tasks from Notion.", "parameters": {"type": "object", "properties": {"return_all": {"type": "boolean"}}}}},
    {"type": "function", "function": {"name": "update_notion_task", "description": "Update an existing Notion task.", "parameters": {"type": "object", "required": ["page_id"], "properties": {"page_id": {"type": "string"}, "status": {"type": "string"}, "title": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "create_notion_task", "description": "Create a new task in Notion.", "parameters": {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "send_sms", "description": "Send an SMS to any phone number.", "parameters": {"type": "object", "required": ["to", "message"], "properties": {"to": {"type": "string"}, "message": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "send_sms_to_client", "description": "Send an SMS to the current client using their saved phone number.", "parameters": {"type": "object", "required": ["message"], "properties": {"message": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "search_knowledge_base", "description": "Search this client's business knowledge base — their uploaded docs, FAQs, SOPs, pricing, etc. Always search here first when asked about the client's business.", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "search_contacts", "description": "Search Google Contacts.", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "create_contact", "description": "Add a new contact to Google Contacts.", "parameters": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}, "company": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "update_contact", "description": "Update an existing contact.", "parameters": {"type": "object", "required": ["resource_name"], "properties": {"resource_name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_recent_docs", "description": "List recent Google Docs.", "parameters": {"type": "object", "properties": {"max_results": {"type": "integer"}, "query": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_doc", "description": "Read a Google Doc.", "parameters": {"type": "object", "required": ["doc_id"], "properties": {"doc_id": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "create_doc", "description": "Create a new Google Doc.", "parameters": {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}, "content": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "append_to_doc", "description": "Append text to a Google Doc.", "parameters": {"type": "object", "required": ["doc_id", "text"], "properties": {"doc_id": {"type": "string"}, "text": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_recent_sheets", "description": "List recent Google Sheets.", "parameters": {"type": "object", "properties": {"max_results": {"type": "integer"}, "query": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_sheet", "description": "Read a Google Sheet.", "parameters": {"type": "object", "required": ["sheet_id"], "properties": {"sheet_id": {"type": "string"}, "range_name": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "create_sheet", "description": "Create a new Google Sheet.", "parameters": {"type": "object", "required": ["title"], "properties": {"title": {"type": "string"}, "headers": {"type": "array", "items": {"type": "string"}}}}}},
    {"type": "function", "function": {"name": "append_row", "description": "Append a row to a Google Sheet.", "parameters": {"type": "object", "required": ["sheet_id", "values"], "properties": {"sheet_id": {"type": "string"}, "values": {"type": "array", "items": {"type": "string"}}, "sheet_name": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "update_cell", "description": "Update a cell in a Google Sheet.", "parameters": {"type": "object", "required": ["sheet_id", "cell", "value"], "properties": {"sheet_id": {"type": "string"}, "cell": {"type": "string"}, "value": {"type": "string"}, "sheet_name": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "web_search", "description": "Search the web in real-time using Perplexity.", "parameters": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "create_reminder", "description": "Create a timed reminder. remind_at must be ISO 8601 with timezone.", "parameters": {"type": "object", "required": ["message", "remind_at"], "properties": {"message": {"type": "string"}, "remind_at": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_reminders", "description": "List upcoming reminders.", "parameters": {"type": "object", "properties": {"include_sent": {"type": "boolean"}}}}},
    {"type": "function", "function": {"name": "delete_reminder", "description": "Delete a reminder by ID.", "parameters": {"type": "object", "required": ["reminder_id"], "properties": {"reminder_id": {"type": "string"}}}}},
]

TOOLS.extend(WORKFLOW_TOOLS)

_sessions: dict[str, list] = defaultdict(list)
MAX_HISTORY = 20


def _make_tool_map(user_id: str) -> dict:
    user_tools = [
        "get_emails", "create_draft", "send_email", "reply_to_email", "add_label",
        "get_calendar_events", "create_calendar_event",
        "get_notion_tasks", "update_notion_task", "create_notion_task",
        "search_contacts", "create_contact", "update_contact",
        "list_recent_docs", "read_doc", "create_doc", "append_to_doc",
        "list_recent_sheets", "read_sheet", "create_sheet", "append_row", "update_cell",
        "search_knowledge_base", "create_reminder", "list_reminders",
    ]

    base_map = {
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
        "send_sms_to_client": lambda message, _uid=user_id: send_sms_to_client(message=message, user_id=_uid) if _uid else {"error": "No user_id"},
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
    base_map.update(WORKFLOW_FUNCS)

    if not user_id:
        return base_map

    tool_map = dict(base_map)
    for name in user_tools:
        fn = base_map[name]
        def _wrap(f=fn):
            def wrapped(**kwargs):
                return f(**kwargs, user_id=user_id)
            return wrapped
        tool_map[name] = _wrap()

    return tool_map


def _convert_tools_to_anthropic(openai_tools: list) -> list:
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
            converted.append(t)
    return converted


def run_agent(
    user_message: str,
    system_prompt: str,
    phone_number: str = None,
    user_id: str = None,
    tools: list = None,
) -> str:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = _sessions[phone_number] if phone_number else []

    messages = [m for m in history if m.get("role") in ("user", "assistant")]
    messages.append({"role": "user", "content": user_message})

    active_tools_openai = TOOLS if tools is None else tools
    active_tools = _convert_tools_to_anthropic(active_tools_openai) if active_tools_openai else []
    tool_map = _make_tool_map(user_id)

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
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            text_parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
            final_text = "\n".join(text_parts).strip()
            break

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            name = block.name
            args = block.input or {}
            print(f"[Tool] {name}({args})")

            try:
                fn = tool_map.get(name)
                if not fn:
                    raise ValueError(f"Unknown tool: {name}")
                result = fn(**args)
            except IntegrationNotConnected as e:
                parts = str(e).split(":", 2)
                label = parts[2] if len(parts) == 3 else "that integration"
                result = {
                    "error": "not_connected",
                    "message": f"You haven't connected your {label} yet. You can connect it from the Connections page in your portal.",
                }
                print(f"[Tool] Not connected: {label}")
            except Exception as e:
                result = {"error": str(e)}
                print(f"[Tool Error] {name}: {e}")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        messages.append({"role": "user", "content": tool_results})

    if phone_number:
        session = _sessions[phone_number]
        session.append({"role": "user", "content": user_message})
        session.append({"role": "assistant", "content": final_text})
        if len(session) > MAX_HISTORY:
            _sessions[phone_number] = session[-MAX_HISTORY:]

    return final_text
