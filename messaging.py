"""Shared messaging module — all outbound messages go through here."""
import os
import requests
from twilio.rest import Client as TwilioClient
from supabase import create_client

TWILIO_FROM = "+18663288127"


def _get_supabase():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def get_client_profile(user_id: str) -> dict | None:
    try:
        result = (
            _get_supabase()
            .table("client_profiles")
            .select("*")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
    except Exception as e:
        print(f"[Messaging] get_client_profile error: {e}")
    return None


def send_message_via_wp(to: str, body: str, typing_time: int = 0) -> dict:
    phone = to.replace("@s.whatsapp.net", "").replace("@c.us", "").lstrip("+")
    url = "https://gate.whapi.cloud/messages/text"
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {os.environ['WHAPI_API_KEY']}",
        "content-type": "application/json",
    }
    data = {
        "typing_time": typing_time,
        "to": f"{phone}@s.whatsapp.net",
        "body": body,
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        return response.json()
    except Exception as e:
        print(f"[Messaging] WhatsApp send error: {e}")
        return {"error": str(e)}


def send_message_via_sms(to: str, body: str) -> dict:
    client = TwilioClient(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )
    message = client.messages.create(to=to, body=body, from_=TWILIO_FROM)
    return {"sid": message.sid}


def send_message(user_id: str, body: str) -> dict:
    profile = get_client_profile(user_id)
    if not profile:
        return {"error": "Profile not found"}
    method = profile.get("communication_method", "sms")
    phone = profile.get("phone_number")
    if not phone:
        return {"error": "No phone number on file for this client."}
    if method == "wp":
        return send_message_via_wp(phone, body)
    return send_message_via_sms(phone, body)
