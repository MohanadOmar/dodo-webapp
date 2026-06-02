import os
import hmac
import hashlib
from urllib.parse import urlencode, quote

from fastapi import APIRouter, Request, Response
from agent import run_agent
from system_prompts import get_sms_system_prompt

router = APIRouter()


def validate_twilio_signature(request_url: str, post_data: dict, signature: str, auth_token: str) -> bool:
    """Validate that the request came from Twilio."""
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(post_data.items()))
    s = request_url + sorted_params
    mac = hmac.new(auth_token.encode(), s.encode(), hashlib.sha1)
    expected = mac.digest()
    import base64
    return hmac.compare_digest(base64.b64encode(expected).decode(), signature)


@router.post("/incoming")
async def incoming_sms(request: Request):
    form = await request.form()
    data = dict(form)

    from_number = data.get("From", "")
    body = data.get("Body", "").strip()
    print(f"[SMS In] From {from_number}: {body}")

    # Validate Twilio signature in production
    if os.getenv("NODE_ENV") == "production":
        signature = request.headers.get("X-Twilio-Signature", "")
        base_url = f"{os.environ['BASE_URL']}/sms/incoming"
        if not validate_twilio_signature(base_url, data, signature, os.environ["TWILIO_AUTH_TOKEN"]):
            return Response(content="Forbidden", status_code=403)

    try:
        reply = run_agent(
            user_message=body,
            system_prompt=get_sms_system_prompt(),
            phone_number=from_number,
        )
        print(f"[SMS Out] To {from_number}: {reply}")
    except Exception as e:
        print(f"[SMS Error] {e}")
        reply = "Dodo hit an error. Try again in a moment."

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>{reply}</Message>
</Response>"""
    return Response(content=twiml, media_type="text/xml")
