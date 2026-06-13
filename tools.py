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

# ─── Constants ───────────────────────────────────────────────────────────────

NOTION_DATABASE_ID = "17e3ff1d-c591-458f-9bf5-fb6d3448e130"
TWILIO_FROM = "+18663288127"
MOHANAD_PHONE = "+12107219295"
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "mohanadomark@gmail.com")


class IntegrationNotConnected(Exception):
    def __init__(self, integration: str):
        self.integration = integration
        labels = {
            "gmail": "Gmail",
            "google_calendar": "Google Calendar",
            "google_contacts": "Google Contacts",
            "google_docs": "Google Docs",
            "google_sheets": "Google Sheets",
            "notion": "Notion",
        }
        label = labels.get(integration, integration)
        super().__init__(f"NOT_CONNECTED:{integration}:{label}")


# ─── Base clients ─────────────────────────────────────────────────────────────

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

def get_openai():
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def get_twilio():
    return TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


# ─── Client profile helpers ───────────────────────────────────────────────────

def get_client_phone(user_id: str) -> str | None:
    """Get a client's phone number from client_profiles. Returns None if not set."""
    try:
        result = get_supabase().table("client_profiles").select("phone_number").eq("user_id", user_id).limit(1).execute()
        if result.data:
            return result.data[0].get("phone_number")
    except Exception:
        pass
    return None


def get_client_timezone(user_id: str) -> str:
    """Get a client's timezone. Defaults to America/Chicago."""
    try:
        result = get_supabase().table("client_profiles").select("timezone").eq("user_id", user_id).limit(1).execute()
        if result.data:
            return result.data[0].get("timezone") or "America/Chicago"
    except Exception:
        pass
    return "America/Chicago"


# ─── Connection helpers ───────────────────────────────────────────────────────

def _get_client_connection(user_id: str, integration: str) -> dict:
    if user_id is None:
        return {"mode": "env"}
    result = (
        get_supabase().table("client_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("integration", integration)
        .eq("status", "connected")
        .limit(1)
        .execute()
    )
    if not result.data:
        raise IntegrationNotConnected(integration)
    return result.data[0]


# ─── Google credentials ───────────────────────────────────────────────────────

def _build_creds_from_env():
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


def get_google_creds_for(user_id: str, integration: str):
    if user_id is None:
        return _build_creds_from_env()
    row = _get_client_connection(user_id, integration)
    if row.get("mode") == "env":
        return _build_creds_from_env()
    refresh_token = row.get("refresh_token")
    if not refresh_token:
        raise IntegrationNotConnected(integration)
    creds = Credentials(
        token=row.get("access_token"),
        refresh_token=refresh_token,
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
    try:
        get_supabase().table("client_connections").update(
            {"access_token": creds.token}
        ).eq("user_id", user_id).eq("integration", integration).execute()
    except Exception:
        pass
    return creds


def get_notion_client(user_id: str = None):
    if user_id is None:
        return NotionClient(auth=os.environ["NOTION_API_KEY"])
    row = _get_client_connection(user_id, "notion")
    if row.get("mode") == "env":
        return NotionClient(auth=os.environ["NOTION_API_KEY"])
    token = row.get("access_token") or row.get("refresh_token")
    if not token:
        raise IntegrationNotConnected("notion")
    return NotionClient(auth=token)


# ─── Service builders ─────────────────────────────────────────────────────────

def get_gmail(user_id=None):
    return build("gmail", "v1", credentials=get_google_creds_for(user_id, "gmail"))

def get_calendar(user_id=None):
    return build("calendar", "v3", credentials=get_google_creds_for(user_id, "google_calendar"))

def get_contacts(user_id=None):
    return build("people", "v1", credentials=get_google_creds_for(user_id, "google_contacts"))

def get_docs(user_id=None):
    return build("docs", "v1", credentials=get_google_creds_for(user_id, "google_docs"))

def get_sheets(user_id=None):
    return build("sheets", "v4", credentials=get_google_creds_for(user_id, "google_sheets"))

def get_drive(user_id=None):
    return build("drive", "v3", credentials=get_google_creds_for(user_id, "google_docs"))


# ─── Gmail ────────────────────────────────────────────────────────────────────

def get_emails(max_results: int = 5, query: str = "is:unread", user_id: str = None) -> list:
    service = get_gmail(user_id)
    result = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    emails = []
    for msg in result.get("messages", []):
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


def create_draft(to: str, subject: str, body: str, user_id: str = None) -> dict:
    service = get_gmail(user_id)
    raw = _make_raw(to, subject, body)
    draft = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return {"draft_id": draft["id"]}


def send_email(to: str, subject: str, body: str, user_id: str = None) -> dict:
    service = get_gmail(user_id)
    raw = _make_raw(to, subject, body)
    msg = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"message_id": msg["id"]}


def reply_to_email(message_id: str, body: str, user_id: str = None) -> dict:
    service = get_gmail(user_id)
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


def add_label(message_id: str, label_name: str, user_id: str = None) -> dict:
    service = get_gmail(user_id)
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    match = next((l for l in labels if l["name"].lower() == label_name.lower()), None)
    if not match:
        raise ValueError(f'Label "{label_name}" not found')
    service.users().messages().modify(
        userId="me", id=message_id, body={"addLabelIds": [match["id"]]}
    ).execute()
    return {"success": True, "label": label_name}


# ─── Google Calendar ──────────────────────────────────────────────────────────

def get_calendar_events(time_min: str = None, time_max: str = None, max_results: int = 20, user_id: str = None) -> list:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    service = get_calendar(user_id)
    tz = get_client_timezone(user_id) if user_id else "America/Chicago"
    now = datetime.now(ZoneInfo(tz))
    start = time_min or now.isoformat()
    end = time_max or (now + timedelta(days=7)).isoformat()
    result = service.events().list(
        calendarId="primary" if user_id else CALENDAR_ID,
        timeMin=start, timeMax=end,
        maxResults=max_results, singleEvents=True, orderBy="startTime"
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


def create_calendar_event(title: str, start: str, end: str = None, description: str = "", location: str = "", user_id: str = None) -> dict:
    from datetime import datetime, timedelta
    service = get_calendar(user_id)
    tz = get_client_timezone(user_id) if user_id else "America/Chicago"
    cal_id = "primary" if user_id else CALENDAR_ID
    if not end:
        end = (datetime.fromisoformat(start) + timedelta(minutes=30)).isoformat()
    freebusy = service.freebusy().query(body={
        "timeMin": start, "timeMax": end,
        "timeZone": tz, "items": [{"id": cal_id}],
    }).execute()
    busy_slots = freebusy["calendars"][cal_id].get("busy", [])
    if busy_slots:
        conflicts = service.events().list(
            calendarId=cal_id, timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime",
        ).execute().get("items", [])
        return {
            "conflict": True,
            "message": f"Cannot create '{title}' — conflicts with existing event(s).",
            "existing_events": [
                {
                    "title": e.get("summary", "Untitled"),
                    "start": e["start"].get("dateTime", e["start"].get("date")),
                    "end": e["end"].get("dateTime", e["end"].get("date")),
                }
                for e in conflicts
            ],
        }
    event = service.events().insert(
        calendarId=cal_id,
        body={
            "summary": title,
            "start": {"dateTime": start, "timeZone": tz},
            "end": {"dateTime": end, "timeZone": tz},
            "description": description,
            "location": location,
        },
    ).execute()
    return {"event_id": event["id"], "link": event.get("htmlLink", ""), "conflict": False}


# ─── Notion ───────────────────────────────────────────────────────────────────

def get_notion_tasks(return_all: bool = True, user_id: str = None) -> list:
    notion = get_notion_client(user_id)
    result = notion.databases.query(database_id=NOTION_DATABASE_ID, page_size=100 if return_all else 10)
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


def update_notion_task(page_id: str, status: str = None, title: str = None, user_id: str = None) -> dict:
    notion = get_notion_client(user_id)
    properties = {}
    if status:
        properties["Status"] = {"select": {"name": status}}
    if title:
        properties["Task"] = {"title": [{"text": {"content": title}}]}
    notion.pages.update(page_id=page_id, properties=properties)
    return {"success": True, "page_id": page_id}


def create_notion_task(title: str, user_id: str = None) -> dict:
    notion = get_notion_client(user_id)
    page = notion.pages.create(
        parent={"database_id": NOTION_DATABASE_ID},
        properties={"Task": {"title": [{"text": {"content": title}}]}},
    )
    return {"page_id": page["id"], "title": title}


# ─── SMS ──────────────────────────────────────────────────────────────────────

def send_sms(to: str, message: str) -> dict:
    client = get_twilio()
    msg = client.messages.create(from_=TWILIO_FROM, to=to, body=message)
    return {"sid": msg.sid}


def send_sms_to_mohanad(message: str) -> dict:
    """Personal SMS to Mohanad — used by SMS/voice Dodo only (user_id=None)."""
    return send_sms(to=MOHANAD_PHONE, message=message)


def send_sms_to_client(message: str, user_id: str) -> dict:
    """Send SMS to a client using their phone number from client_profiles."""
    phone = get_client_phone(user_id)
    if not phone:
        return {"error": "No phone number on file for this client. They need to add it in their profile."}
    return send_sms(to=phone, message=message)


def send_whatsapp(to: str, message: str) -> dict:
    """Send a WhatsApp message via Whapi."""
    api_key = os.environ.get("WHAPI_API_KEY", "")
    phone = to.replace("@s.whatsapp.net", "").replace("@c.us", "").lstrip("+")
    _requests.post(
        "https://gate.whapi.cloud/messages/text",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"to": f"{phone}@s.whatsapp.net", "body": message},
        timeout=15,
    )
    return {"success": True, "to": to}


def send_message_to_client(message: str, user_id: str) -> dict:
    """Send a message to a client via their preferred channel (SMS or WhatsApp)."""
    supabase = get_supabase()
    result = (
        supabase.table("client_profiles")
        .select("messaging_channel, phone_number, whatsapp_number")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {"error": "No profile found for this client."}

    profile = result.data[0]
    channel = profile.get("messaging_channel") or "sms"

    if channel == "whatsapp":
        wa_number = profile.get("whatsapp_number")
        if not wa_number:
            return {"error": "No WhatsApp number on file for this client."}
        return send_whatsapp(to=wa_number, message=message)
    else:
        phone = profile.get("phone_number")
        if not phone:
            return {"error": "No phone number on file for this client."}
        return send_sms(to=phone, message=message)


# ─── Knowledge Base (per-client) ──────────────────────────────────────────────

def search_knowledge_base(query: str, user_id: str = None) -> list:
    """
    Search the knowledge base. If user_id is set, only searches that
    client's documents. Falls back to EG23's global docs if no user_id.
    """
    client = get_openai()
    supabase = get_supabase()

    embedding_res = client.embeddings.create(model="text-embedding-3-small", input=query)
    embedding = embedding_res.data[0].embedding

    # Pass user_id as filter so the RPC only returns their documents
    filter_obj = {}
    if user_id:
        filter_obj["user_id"] = user_id

    result = supabase.rpc("match_documents", {
        "query_embedding": embedding,
        "match_count": 5,
        "filter": filter_obj,
    }).execute()

    return result.data or []


def upload_document_chunks(chunks: list[dict], user_id: str, source_name: str) -> dict:
    """
    Store pre-embedded document chunks in Supabase.
    Each chunk: {"content": str, "embedding": list[float]}
    Called by the /knowledge/upload endpoint.
    """
    supabase = get_supabase()
    rows = [
        {
            "content": chunk["content"],
            "embedding": chunk["embedding"],
            "metadata": {"source": source_name},
            "user_id": user_id,
            "source_name": source_name,
        }
        for chunk in chunks
    ]
    result = supabase.table("documents").insert(rows).execute()
    return {"uploaded": len(rows), "source": source_name}


def list_client_documents(user_id: str) -> list:
    """List documents uploaded by a client (distinct source names)."""
    supabase = get_supabase()
    result = (
        supabase.table("documents")
        .select("id, source_name, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    # Deduplicate by source_name
    seen = {}
    for row in (result.data or []):
        name = row.get("source_name", "Unknown")
        if name not in seen:
            seen[name] = {"source_name": name, "created_at": row.get("created_at")}
    return list(seen.values())


def delete_client_document(source_name: str, user_id: str) -> dict:
    """Delete all chunks for a given source document."""
    supabase = get_supabase()
    supabase.table("documents").delete().eq("user_id", user_id).eq("source_name", source_name).execute()
    return {"deleted": source_name}


# ─── Google Contacts ──────────────────────────────────────────────────────────

def search_contacts(query: str, max_results: int = 5, user_id: str = None) -> list:
    service = get_contacts(user_id)
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


def create_contact(name: str, email: str = None, phone: str = None, company: str = None, user_id: str = None) -> dict:
    service = get_contacts(user_id)
    body = {"names": [{"givenName": name}]}
    if email:
        body["emailAddresses"] = [{"value": email}]
    if phone:
        body["phoneNumbers"] = [{"value": phone}]
    if company:
        body["organizations"] = [{"name": company}]
    person = service.people().createContact(body=body).execute()
    return {"resource_name": person["resourceName"], "name": name}


def update_contact(resource_name: str, email: str = None, phone: str = None, user_id: str = None) -> dict:
    service = get_contacts(user_id)
    person = service.people().get(resourceName=resource_name, personFields="names,emailAddresses,phoneNumbers").execute()
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


# ─── Google Docs ──────────────────────────────────────────────────────────────

def list_recent_docs(max_results: int = 10, query: str = None, user_id: str = None) -> list:
    drive = get_drive(user_id)
    q = "mimeType='application/vnd.google-apps.document' and trashed=false"
    if query:
        q += f" and name contains '{query}'"
    result = drive.files().list(q=q, orderBy="modifiedTime desc", pageSize=max_results, fields="files(id, name, modifiedTime, webViewLink)").execute()
    return [{"id": f["id"], "title": f["name"], "modified": f.get("modifiedTime", ""), "url": f.get("webViewLink", "")} for f in result.get("files", [])]


def read_doc(doc_id: str, user_id: str = None) -> dict:
    docs = get_docs(user_id)
    doc = docs.documents().get(documentId=doc_id).execute()
    text_parts = []
    for elem in doc.get("body", {}).get("content", []):
        para = elem.get("paragraph")
        if not para:
            continue
        for run in para.get("elements", []):
            text_parts.append(run.get("textRun", {}).get("content", ""))
    return {"id": doc_id, "title": doc.get("title", ""), "content": "".join(text_parts)}


def create_doc(title: str, content: str = "", user_id: str = None) -> dict:
    docs = get_docs(user_id)
    doc = docs.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    if content:
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]}).execute()
    return {"id": doc_id, "title": title, "url": f"https://docs.google.com/document/d/{doc_id}/edit"}


def append_to_doc(doc_id: str, text: str, user_id: str = None) -> dict:
    docs = get_docs(user_id)
    doc = docs.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": [{"insertText": {"location": {"index": end_index}, "text": "\n" + text}}]}).execute()
    return {"success": True, "doc_id": doc_id}


# ─── Google Sheets ────────────────────────────────────────────────────────────

def list_recent_sheets(max_results: int = 10, query: str = None, user_id: str = None) -> list:
    drive = get_drive(user_id)
    q = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    if query:
        q += f" and name contains '{query}'"
    result = drive.files().list(q=q, orderBy="modifiedTime desc", pageSize=max_results, fields="files(id, name, modifiedTime, webViewLink)").execute()
    return [{"id": f["id"], "title": f["name"], "modified": f.get("modifiedTime", ""), "url": f.get("webViewLink", "")} for f in result.get("files", [])]


def read_sheet(sheet_id: str, range_name: str = "A1:Z100", user_id: str = None) -> dict:
    sheets = get_sheets(user_id)
    if range_name == "A1:Z100":
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        first_sheet_name = meta["sheets"][0]["properties"]["title"]
        range_name = f"{first_sheet_name}!A1:Z100"
    result = sheets.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_name).execute()
    values = result.get("values", [])
    if not values:
        return {"sheet_id": sheet_id, "rows": [], "row_count": 0}
    return {"sheet_id": sheet_id, "headers": values[0], "rows": values[1:], "row_count": len(values) - 1, "range": range_name}


def create_sheet(title: str, headers: list = None, user_id: str = None) -> dict:
    sheets = get_sheets(user_id)
    sheet = sheets.spreadsheets().create(body={"properties": {"title": title}}).execute()
    sheet_id = sheet["spreadsheetId"]
    if headers:
        sheets.spreadsheets().values().update(spreadsheetId=sheet_id, range="A1", valueInputOption="USER_ENTERED", body={"values": [headers]}).execute()
    return {"id": sheet_id, "title": title, "url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"}


def append_row(sheet_id: str, values: list, sheet_name: str = None, user_id: str = None) -> dict:
    sheets = get_sheets(user_id)
    if not sheet_name:
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheet_name = meta["sheets"][0]["properties"]["title"]
    sheets.spreadsheets().values().append(spreadsheetId=sheet_id, range=f"{sheet_name}!A1", valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body={"values": [values]}).execute()
    return {"success": True, "sheet_id": sheet_id, "appended": values}


def update_cell(sheet_id: str, cell: str, value: str, sheet_name: str = None, user_id: str = None) -> dict:
    sheets = get_sheets(user_id)
    if not sheet_name:
        meta = sheets.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheet_name = meta["sheets"][0]["properties"]["title"]
    sheets.spreadsheets().values().update(spreadsheetId=sheet_id, range=f"{sheet_name}!{cell}", valueInputOption="USER_ENTERED", body={"values": [[value]]}).execute()
    return {"success": True, "sheet_id": sheet_id, "cell": cell, "value": value}


# ─── Perplexity ───────────────────────────────────────────────────────────────

import requests as _requests

def web_search(query: str) -> dict:
    api_key = os.environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        return {"error": "PERPLEXITY_API_KEY not set"}
    try:
        response = _requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": "You are a research assistant. Provide a concise, factual answer with the most important details. Keep it under 300 words. Include specific numbers, dates, and names where relevant."},
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
            result["sources"] = citations[:5]
        return result
    except _requests.Timeout:
        return {"error": "Perplexity search timed out"}
    except Exception as e:
        return {"error": str(e)}


# ─── Reminders ────────────────────────────────────────────────────────────────

def create_reminder(message: str, remind_at: str, user_id: str = None) -> dict:
    """
    Create a reminder. Stores user_id so the reminder poller
    knows whose phone to send it to.
    """
    supabase = get_supabase()
    row = supabase.table("reminders").insert({
        "message": message,
        "remind_at": remind_at,
        "sent": False,
        "user_id": user_id,
    }).execute()
    if row.data:
        return {"success": True, "id": row.data[0]["id"], "message": message, "remind_at": remind_at}
    return {"success": False, "error": "Failed to create reminder"}


def list_reminders(include_sent: bool = False, user_id: str = None) -> list:
    supabase = get_supabase()
    query = supabase.table("reminders").select("*").order("remind_at")
    if user_id:
        query = query.eq("user_id", user_id)
    if not include_sent:
        query = query.eq("sent", False)
    return query.execute().data or []


def delete_reminder(reminder_id: str) -> dict:
    get_supabase().table("reminders").delete().eq("id", reminder_id).execute()
    return {"success": True, "deleted": reminder_id}
