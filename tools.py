import os
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from notion_client import Client as NotionClient
from twilio.rest import Client as TwilioClient
from supabase import create_client
from openai import OpenAI

# ─── Clients ────────────────────────────────────────────────────────────────

NOTION_DATABASE_ID = "17e3ff1d-c591-458f-9bf5-fb6d3448e130"
TWILIO_FROM = "+18663288127"
MOHANAD_PHONE = "+12107219295"
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "mohanadomark@gmail.com")


def get_google_creds():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=[
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/contacts",
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    creds.refresh(Request())
    return creds


def get_gmail():
    return build("gmail", "v1", credentials=get_google_creds())


def get_calendar():
    return build("calendar", "v3", credentials=get_google_creds())


def get_contacts():
    return build("people", "v1", credentials=get_google_creds())


def get_docs():
    return build("docs", "v1", credentials=get_google_creds())


def get_sheets():
    return build("sheets", "v4", credentials=get_google_creds())


def get_drive():
    return build("drive", "v3", credentials=get_google_creds())


def get_notion():
    return NotionClient(auth=os.environ["NOTION_API_KEY"])


def get_twilio():
    return TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def get_openai():
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ─── Gmail ──────────────────────────────────────────────────────────────────

def get_emails(max_results: int = 5, query: str = "is:unread") -> list:
    service = get_gmail()
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = result.get("messages", [])

    emails = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": detail.get("snippet", ""),
        })
    return emails


def _make_raw(to: str, subject: str, body: str, reply_headers: dict = None) -> str:
    msg = MIMEMultipart()
    msg["To"] = to
    msg["Subject"] = subject
    if reply_headers:
        msg["In-Reply-To"] = reply_headers.get("message_id", "")
        msg["References"] = reply_headers.get("references", "")
    msg.attach(MIMEText(body, "plain"))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def create_draft(to: str, subject: str, body: str) -> dict:
    service = get_gmail()
    raw = _make_raw(to, subject, body)
    draft = service.users().drafts().create(
        userId="me", body={"message": {"raw": raw}}
    ).execute()
    return {"draft_id": draft["id"]}


def send_email(to: str, subject: str, body: str) -> dict:
    service = get_gmail()
    raw = _make_raw(to, subject, body)
    msg = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"message_id": msg["id"]}


def reply_to_email(message_id: str, body: str) -> dict:
    service = get_gmail()
    detail = service.users().messages().get(
        userId="me", id=message_id, format="metadata",
        metadataHeaders=["From", "Subject", "Message-ID", "References"]
    ).execute()
    headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
    thread_id = detail["threadId"]

    subject = headers.get("Subject", "")
    if not subject.startswith("Re:"):
        subject = f"Re: {subject}"

    raw = _make_raw(
        to=headers.get("From", ""),
        subject=subject,
        body=body,
        reply_headers={
            "message_id": headers.get("Message-ID", ""),
            "references": f"{headers.get('References', '')} {headers.get('Message-ID', '')}".strip(),
        },
    )
    msg = service.users().messages().send(
        userId="me", body={"raw": raw, "threadId": thread_id}
    ).execute()
    return {"message_id": msg["id"]}


def add_label(message_id: str, label_name: str) -> dict:
    service = get_gmail()
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    match = next((l for l in labels if l["name"].lower() == label_name.lower()), None)
    if not match:
        raise ValueError(f'Label "{label_name}" not found')
    service.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": [match["id"]]}
    ).execute()
    return {"success": True, "label": label_name}


# ─── Google Calendar ─────────────────────────────────────────────────────────

def get_calendar_events(time_min: str = None, time_max: str = None, max_results: int = 20) -> list:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    service = get_calendar()
    now = datetime.now(ZoneInfo("America/Chicago"))
    start = time_min or now.isoformat()
    end = time_max or (now + timedelta(days=7)).isoformat()

    result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start, timeMax=end,
        maxResults=max_results,
        singleEvents=True, orderBy="startTime"
    ).execute()

    return [
        {
            "id": e["id"],
            "title": e.get("summary", ""),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "location": e.get("location", ""),
            "description": e.get("description", ""),
        }
        for e in result.get("items", [])
    ]


def create_calendar_event(title: str, start: str, end: str = None, description: str = "", location: str = "") -> dict:
    from datetime import datetime, timedelta
    service = get_calendar()
    if not end:
        end = (datetime.fromisoformat(start) + timedelta(minutes=30)).isoformat()

    # Conflict check — query freebusy for the exact requested window
    freebusy = service.freebusy().query(body={
        "timeMin": start,
        "timeMax": end,
        "timeZone": "America/Chicago",
        "items": [{"id": CALENDAR_ID}],
    }).execute()

    busy_slots = freebusy["calendars"][CALENDAR_ID].get("busy", [])
    if busy_slots:
        # There's a conflict — fetch event titles for context
        conflicts = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=start,
            timeMax=end,
            singleEvents=True,
            orderBy="startTime",
        ).execute().get("items", [])

        conflict_list = [
            {
                "title": e.get("summary", "Untitled"),
                "start": e["start"].get("dateTime", e["start"].get("date")),
                "end": e["end"].get("dateTime", e["end"].get("date")),
            }
            for e in conflicts
        ]
        return {
            "conflict": True,
            "message": f"Cannot create '{title}' — conflicts with existing event(s).",
            "existing_events": conflict_list,
        }

    # No conflict, safe to create
    event = service.events().insert(
        calendarId=CALENDAR_ID,
        body={
            "summary": title,
            "start": {"dateTime": start, "timeZone": "America/Chicago"},
            "end": {"dateTime": end, "timeZone": "America/Chicago"},
            "description": description,
            "location": location,
        },
    ).execute()
    return {"event_id": event["id"], "link": event.get("htmlLink", ""), "conflict": False}


# ─── Notion ──────────────────────────────────────────────────────────────────

def get_notion_tasks(return_all: bool = True) -> list:
    notion = get_notion()
    result = notion.databases.query(
        database_id=NOTION_DATABASE_ID,
        page_size=100 if return_all else 10
    )
    tasks = []
    for page in result["results"]:
        props = page["properties"]
        title = (
            props.get("Task", props.get("Name", {}))
            .get("title", [{}])[0]
            .get("plain_text", "Untitled")
        )
        status = (
            props.get("Status", {}).get("select", {}) or
            props.get("Status", {}).get("status", {})
        ).get("name", "Unknown")
        tasks.append({"id": page["id"], "title": title, "status": status})
    return tasks


def update_notion_task(page_id: str, status: str = None, title: str = None) -> dict:
    notion = get_notion()
    properties = {}
    if status:
        properties["Status"] = {"select": {"name": status}}
    if title:
        properties["Task"] = {"title": [{"text": {"content": title}}]}
    notion.pages.update(page_id=page_id, properties=properties)
    return {"success": True, "page_id": page_id}


def create_notion_task(title: str) -> dict:
    notion = get_notion()
    page = notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties={"Task": {"title": [{"text": {"content": title}}]}},
    )
    return {"page_id": page["id"], "title": title}


# ─── Twilio ──────────────────────────────────────────────────────────────────

def send_sms(to: str, message: str) -> dict:
    client = get_twilio()
    msg = client.messages.create(from_=TWILIO_FROM, to=to, body=message)
    return {"sid": msg.sid}


def send_sms_to_mohanad(message: str) -> dict:
    return send_sms(to=MOHANAD_PHONE, message=message)


# ─── Supabase Knowledge Base ─────────────────────────────────────────────────

def search_knowledge_base(query: str) -> list:
    client = get_openai()
    supabase = get_supabase()

    embedding_res = client.embeddings.create(
        model="text-embedding-3-small", input=query
    )
    embedding = embedding_res.data[0].embedding

    result = supabase.rpc("match_documents", {
        "query_embedding": embedding,
        "match_count": 5,
        "filter": {},
    }).execute()

    return result.data or []


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE CONTACTS
# ════════════════════════════════════════════════════════════════════════════

def search_contacts(query: str, max_results: int = 5) -> list:
    """Search the user's Google Contacts by name, email, or phone."""
    service = get_contacts()
    # Trigger the warmup cache for searches (recommended by Google)
    try:
        service.people().searchContacts(query="", readMask="names").execute()
    except Exception:
        pass

    result = service.people().searchContacts(
        query=query,
        readMask="names,emailAddresses,phoneNumbers,organizations",
        pageSize=max_results,
    ).execute()

    contacts = []
    for r in result.get("results", []):
        person = r.get("person", {})
        names = person.get("names", [])
        emails = person.get("emailAddresses", [])
        phones = person.get("phoneNumbers", [])
        orgs = person.get("organizations", [])

        contacts.append({
            "resource_name": person.get("resourceName", ""),
            "name": names[0].get("displayName", "") if names else "",
            "emails": [e.get("value", "") for e in emails],
            "phones": [p.get("value", "") for p in phones],
            "company": orgs[0].get("name", "") if orgs else "",
        })
    return contacts


def create_contact(name: str, email: str = None, phone: str = None, company: str = None) -> dict:
    """Create a new contact."""
    service = get_contacts()
    body = {"names": [{"givenName": name}]}
    if email:
        body["emailAddresses"] = [{"value": email}]
    if phone:
        body["phoneNumbers"] = [{"value": phone}]
    if company:
        body["organizations"] = [{"name": company}]

    person = service.people().createContact(body=body).execute()
    return {"resource_name": person["resourceName"], "name": name}


def update_contact(resource_name: str, email: str = None, phone: str = None) -> dict:
    """Update an existing contact's email or phone. Use search_contacts first to get the resource_name."""
    service = get_contacts()

    # Need to fetch current state first
    person = service.people().get(
        resourceName=resource_name,
        personFields="names,emailAddresses,phoneNumbers"
    ).execute()

    update_fields = []
    body = {"etag": person["etag"]}

    if email:
        body["emailAddresses"] = [{"value": email}]
        update_fields.append("emailAddresses")
    if phone:
        body["phoneNumbers"] = [{"value": phone}]
        update_fields.append("phoneNumbers")

    if not update_fields:
        return {"error": "No fields to update"}

    updated = service.people().updateContact(
        resourceName=resource_name,
        updatePersonFields=",".join(update_fields),
        body=body,
    ).execute()

    return {"success": True, "resource_name": updated["resourceName"]}


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE DOCS
# ════════════════════════════════════════════════════════════════════════════

def list_recent_docs(max_results: int = 10, query: str = None) -> list:
    """List recent Google Docs. Optionally filter by name/keyword."""
    drive = get_drive()
    q = "mimeType='application/vnd.google-apps.document' and trashed=false"
    if query:
        q += f" and name contains '{query}'"

    result = drive.files().list(
        q=q,
        orderBy="modifiedTime desc",
        pageSize=max_results,
        fields="files(id, name, modifiedTime, webViewLink)",
    ).execute()

    return [
        {
            "id": f["id"],
            "title": f["name"],
            "modified": f.get("modifiedTime", ""),
            "url": f.get("webViewLink", ""),
        }
        for f in result.get("files", [])
    ]


def read_doc(doc_id: str) -> dict:
    """Read the full text content of a Google Doc."""
    docs = get_docs()
    doc = docs.documents().get(documentId=doc_id).execute()

    # Extract plain text from the doc structure
    text_parts = []
    for elem in doc.get("body", {}).get("content", []):
        para = elem.get("paragraph")
        if not para:
            continue
        for run in para.get("elements", []):
            text_run = run.get("textRun", {})
            text_parts.append(text_run.get("content", ""))

    return {
        "id": doc_id,
        "title": doc.get("title", ""),
        "content": "".join(text_parts),
    }


def create_doc(title: str, content: str = "") -> dict:
    """Create a new Google Doc with optional initial content."""
    docs = get_docs()
    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]

    if content:
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
        ).execute()

    return {
        "id": doc_id,
        "title": title,
        "url": f"https://docs.google.com/document/d/{doc_id}/edit",
    }


def append_to_doc(doc_id: str, text: str) -> dict:
    """Append text to the end of a Google Doc."""
    docs = get_docs()
    # Get the current end index
    doc = docs.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1

    docs.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": [{
            "insertText": {"location": {"index": end_index}, "text": "\n" + text}
        }]},
    ).execute()

    return {"success": True, "doc_id": doc_id}


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ════════════════════════════════════════════════════════════════════════════

def list_recent_sheets(max_results: int = 10, query: str = None) -> list:
    """List recent Google Sheets. Optionally filter by name/keyword."""
    drive = get_drive()
    q = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    if query:
        q += f" and name contains '{query}'"

    result = drive.files().list(
        q=q,
        orderBy="modifiedTime desc",
        pageSize=max_results,
        fields="files(id, name, modifiedTime, webViewLink)",
    ).execute()

    return [
        {
            "id": f["id"],
            "title": f["name"],
            "modified": f.get("modifiedTime", ""),
            "url": f.get("webViewLink", ""),
        }
        for f in result.get("files", [])
    ]


def read_sheet(sheet_id: str, range_name: str = "A1:Z100") -> dict:
    """Read a range from a Google Sheet. Default range covers most small sheets."""
    sheets = get_sheets()

    # If no specific range, try to read the first sheet's used range
    if range_name == "A1:Z100":
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        first_sheet_name = meta["sheets"][0]["properties"]["title"]
        range_name = f"{first_sheet_name}!A1:Z100"

    result = sheets.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=range_name
    ).execute()

    values = result.get("values", [])
    if not values:
        return {"sheet_id": sheet_id, "rows": [], "row_count": 0}

    # First row is usually headers
    headers = values[0] if values else []
    data_rows = values[1:] if len(values) > 1 else []

    return {
        "sheet_id": sheet_id,
        "headers": headers,
        "rows": data_rows,
        "row_count": len(data_rows),
        "range": range_name,
    }


def create_sheet(title: str, headers: list = None) -> dict:
    """Create a new Google Sheet with optional headers in row 1."""
    sheets = get_sheets()
    body = {"properties": {"title": title}}
    sheet = sheets.spreadsheets().create(body=body).execute()
    sheet_id = sheet["spreadsheetId"]

    if headers:
        sheets.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()

    return {
        "id": sheet_id,
        "title": title,
        "url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
    }


def append_row(sheet_id: str, values: list, sheet_name: str = None) -> dict:
    """Append a row of values to a sheet. values should be a list of strings/numbers."""
    sheets = get_sheets()

    if not sheet_name:
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheet_name = meta["sheets"][0]["properties"]["title"]

    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()

    return {"success": True, "sheet_id": sheet_id, "appended": values}


def update_cell(sheet_id: str, cell: str, value: str, sheet_name: str = None) -> dict:
    """Update a single cell. cell is in A1 notation like 'B5'."""
    sheets = get_sheets()

    if not sheet_name:
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheet_name = meta["sheets"][0]["properties"]["title"]

    range_name = f"{sheet_name}!{cell}"

    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body={"values": [[value]]},
    ).execute()

    return {"success": True, "sheet_id": sheet_id, "cell": cell, "value": value}




# ════════════════════════════════════════════════════════════════════════════
# PERPLEXITY — real-time web search
# ════════════════════════════════════════════════════════════════════════════

import requests as _requests

def web_search(query: str) -> dict:
    """Search the web in real-time using Perplexity Sonar.

    Returns a concise answer with source citations.
    Use this for any question that needs current/real-time information,
    news, research, facts, pricing, comparisons, or anything
    outside of Mohanad's own tools (Gmail, Calendar, Notion, etc.).
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        return {"error": "PERPLEXITY_API_KEY not set"}

    try:
        response = _requests.post(
            "https://api.perplexity.ai/v1/sonar",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a research assistant. Provide a concise, factual answer "
                            "with key details. Keep it under 200 words. Include specific "
                            "numbers, dates, and names when relevant."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
            },
            timeout=30,
        )

        if response.status_code >= 400:
            return {"error": f"Perplexity returned {response.status_code}: {response.text[:200]}"}

        data = response.json()
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        result = {"answer": answer}
        if citations:
            result["sources"] = citations[:5]  # top 5 sources

        return result

    except _requests.Timeout:
        return {"error": "Perplexity search timed out"}
    except Exception as e:
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════════════════
# PERPLEXITY — Real-time web search via Sonar API
# ════════════════════════════════════════════════════════════════════════════

def web_search(query: str) -> dict:
    """Search the web in real-time using Perplexity Sonar.

    Use this for any question that needs current information:
    news, prices, recent events, company info, regulations, etc.
    """
    import requests as _req

    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        return {"error": "PERPLEXITY_API_KEY not set"}

    try:
        response = _req.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a research assistant. Provide a concise, factual answer "
                            "with the most important details. Keep it under 300 words. "
                            "Include specific numbers, dates, and names where relevant."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
            },
            timeout=30,
        )

        if response.status_code >= 400:
            return {"error": f"Perplexity returned {response.status_code}: {response.text[:200]}"}

        data = response.json()
        answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        citations = data.get("citations", [])

        result = {"answer": answer}
        if citations:
            result["sources"] = citations[:5]  # Top 5 sources
        return result

    except _req.Timeout:
        return {"error": "Perplexity search timed out"}
    except Exception as e:
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════════════════
# REMINDERS (Supabase)
# ════════════════════════════════════════════════════════════════════════════

def create_reminder(message: str, remind_at: str) -> dict:
    """Create a timed reminder. remind_at must be ISO 8601 with timezone (e.g. 2026-05-13T18:00:00-05:00)."""
    supabase = get_supabase()
    row = supabase.table("reminders").insert({
        "message": message,
        "remind_at": remind_at,
        "sent": False,
    }).execute()

    if row.data:
        return {"success": True, "id": row.data[0]["id"], "message": message, "remind_at": remind_at}
    return {"success": False, "error": "Failed to create reminder"}


def list_reminders(include_sent: bool = False) -> list:
    """List upcoming reminders. By default only shows unsent ones."""
    supabase = get_supabase()
    query = supabase.table("reminders").select("*").order("remind_at")
    if not include_sent:
        query = query.eq("sent", False)
    result = query.execute()
    return result.data or []


def delete_reminder(reminder_id: str) -> dict:
    """Delete a reminder by ID."""
    supabase = get_supabase()
    supabase.table("reminders").delete().eq("id", reminder_id).execute()
    return {"success": True, "deleted": reminder_id}
