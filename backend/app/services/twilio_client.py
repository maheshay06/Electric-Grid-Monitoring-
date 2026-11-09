"""Minimal Twilio Programmable Messaging client (REST, no SDK).

Only `Messages.json` is used. The auth token is read from settings at call time and is never logged,
returned by the API, or stored in the database.
"""
import logging

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)

API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
_transport: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport


def set_transport(t: httpx.BaseTransport | None) -> None:
    global _transport
    _transport = t


class TwilioError(Exception):
    def __init__(self, message: str, code: int | None = None, permanent: bool = False):
        super().__init__(message)
        self.code = code
        self.permanent = permanent  # True: retrying cannot help (bad number, bad credentials, ...)


def send_sms(to: str, body: str) -> dict:
    """Returns {"sid": ..., "status": ...} once Twilio ACCEPTED the message ("queued"). This is not delivery."""
    s = get_settings()
    if not s.sms_configured:
        raise TwilioError("Twilio is not configured", permanent=True)
    data = {"To": to, "Body": body}
    if s.twilio_messaging_service_sid:
        data["MessagingServiceSid"] = s.twilio_messaging_service_sid
    else:
        data["From"] = s.twilio_from_number
    try:
        with httpx.Client(transport=_transport, timeout=10.0) as c:
            r = c.post(API.format(sid=s.twilio_account_sid), data=data,
                       auth=(s.twilio_account_sid, s.twilio_auth_token.get_secret_value()))
    except httpx.HTTPError as e:  # network problem: worth retrying
        raise TwilioError(f"network error: {type(e).__name__}") from e

    payload = {}
    try:
        payload = r.json()
    except ValueError:
        pass
    if r.status_code in (200, 201):
        return {"sid": payload.get("sid", ""), "status": payload.get("status", "queued")}
    code = payload.get("code")
    msg = f"{code or r.status_code}: {payload.get('message', 'Twilio request failed')}"[:200]
    # 4xx (except 429 rate limit) will not succeed on retry: invalid/unverified number, bad credentials, etc.
    raise TwilioError(msg, code=code, permanent=400 <= r.status_code < 500 and r.status_code != 429)
