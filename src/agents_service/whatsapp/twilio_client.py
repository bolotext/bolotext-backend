"""Thin Twilio REST client (httpx, no SDK) for WhatsApp messages and Content
templates. Everything sits behind `TwilioClient` so the provider can be swapped.
In dry-run mode nothing leaves the process: calls are simulated.
"""

import asyncio
import base64
import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass

import httpx
from common.log_utils import setup_logger

logger = setup_logger(__name__)

_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
_MESSAGE_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages/{msg}.json"
_ACCOUNT_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}.json"
_CONTENT_URL = "https://content.twilio.com/v1/Content"
_CONTENT_APPROVALS_URL = "https://content.twilio.com/v1/ContentAndApprovals"
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3


class TwilioError(Exception):
    def __init__(self, message: str, code: str | int | None = None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


STATUS_CALLBACK_PATH = "/api/v1/whatsapp/twilio/status-callback"


def callback_url(public_base: str | None) -> str | None:
    """Twilio's status-callback URL, or None when it can't be reached from the
    internet (no known base, or localhost) — then delivery stays at `sent`.
    """
    if not public_base:
        return None
    host = public_base.split("://", 1)[-1].split("/", 1)[0].rsplit("@", 1)[-1]
    if host.split(":")[0] in {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}:  # noqa: S104
        return None
    return public_base.rstrip("/") + STATUS_CALLBACK_PATH


def whatsapp_address(number: str) -> str:
    number = number.strip()
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


@dataclass(frozen=True)
class TwilioConfig:
    """One organization's resolved Twilio settings (token already decrypted).
    The default is a safe, fully simulated configuration.
    """

    account_sid: str = ""
    auth_token: str = ""
    whatsapp_from: str = ""
    sms_from: str = ""
    dry_run: bool = True
    default_country_code: str = "91"

    @property
    def simulated(self) -> bool:
        """True when nothing will reach Twilio: dry-run, or credentials missing."""
        return self.dry_run or not (self.account_sid and self.auth_token)


def compute_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Twilio's X-Twilio-Signature: base64(HMAC-SHA1(token, url + sorted k+v))."""
    payload = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def verify_signature(auth_token: str, url: str, params: dict[str, str], signature: str) -> bool:
    return hmac.compare_digest(compute_signature(auth_token, url, params), signature or "")


class TwilioClient:
    def __init__(self, config: TwilioConfig):
        self.config = config
        self.dry_run = config.simulated

    def _auth(self) -> tuple[str, str]:
        return (self.config.account_sid, self.config.auth_token)

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        last: TwilioError | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                async with httpx.AsyncClient(timeout=20.0) as http:
                    resp = await http.request(method, url, auth=self._auth(), **kwargs)
            except httpx.HTTPError as e:
                last = TwilioError(f"Network error talking to Twilio: {e}", retryable=True)
            else:
                body = resp.json() if resp.content else {}
                if resp.status_code < 300:
                    return body if isinstance(body, dict) else {}
                last = TwilioError(
                    str(body.get("message") or f"Twilio HTTP {resp.status_code}"),
                    code=body.get("code") or resp.status_code,
                    retryable=resp.status_code in _RETRY_STATUSES,
                )
            if not last.retryable or attempt == _MAX_ATTEMPTS:
                break
            await asyncio.sleep(0.5 * 2 ** (attempt - 1))
        assert last is not None
        raise last

    async def fetch_message(self, message_sid: str) -> dict[str, str] | None:
        """The message's current state in Twilio, shaped like a status-callback payload
        (MessageSid, MessageStatus, ErrorCode, …). None for simulated messages.
        """
        if self.dry_run or message_sid.startswith("DRY"):
            return None
        res = await self._request("GET", _MESSAGE_URL.format(sid=self.config.account_sid, msg=message_sid))
        fields = {
            "MessageSid": res.get("sid"), "MessageStatus": res.get("status"), "ErrorCode": res.get("error_code"),
            "ErrorMessage": res.get("error_message"), "To": res.get("to"), "From": res.get("from"),
            "Direction": res.get("direction"), "NumSegments": res.get("num_segments"), "Price": res.get("price"),
            "PriceUnit": res.get("price_unit"), "DateCreated": res.get("date_created"), "DateSent": res.get("date_sent"),
            "DateUpdated": res.get("date_updated"),
        }  # fmt: skip
        return {k: str(v) for k, v in fields.items() if v is not None}

    async def verify_credentials(self) -> str:
        """Checks the account SID/token against Twilio; returns the account's
        friendly name. Simulated configs always pass.
        """
        if self.dry_run:
            return "Simulated (dry-run)"
        res = await self._request("GET", _ACCOUNT_URL.format(sid=self.config.account_sid))
        if res.get("status") != "active":
            raise TwilioError(f"Twilio account is {res.get('status', 'not active')}")
        return str(res.get("friendly_name") or self.config.account_sid)

    # ---- messages ----
    async def send_message(
        self,
        *,
        to: str,
        sender: str,
        body: str | None = None,
        content_sid: str | None = None,
        content_variables: str | None = None,
        status_callback: str | None = None,
        channel: str = "whatsapp",
    ) -> str:
        """Returns the Twilio message SID. `channel="sms"` sends plain text from an
        SMS-capable number (or a Messaging Service SID `MG…`)."""
        if self.dry_run:
            logger.info("[dry-run] WhatsApp message to=%s via template=%s", to[-4:].rjust(len(to), "*"), bool(content_sid))
            return f"DRY{uuid.uuid4().hex}"
        if channel == "sms":
            data = {"To": to.removeprefix("whatsapp:"), "Body": body or ""}
            data["MessagingServiceSid" if sender.upper().startswith("MG") else "From"] = sender.removeprefix("whatsapp:")
            if status_callback:
                data["StatusCallback"] = status_callback
            res = await self._request("POST", _MESSAGES_URL.format(sid=self.config.account_sid), data=data)
            return str(res["sid"])
        data = {"From": whatsapp_address(sender), "To": whatsapp_address(to)}
        if content_sid:
            data["ContentSid"] = content_sid
            if content_variables:
                data["ContentVariables"] = content_variables
        else:
            data["Body"] = body or ""
        if status_callback:
            data["StatusCallback"] = status_callback
        res = await self._request("POST", _MESSAGES_URL.format(sid=self.config.account_sid), data=data)
        return str(res["sid"])

    # ---- templates (Twilio Content API) ----
    async def create_template(self, *, name: str, language: str, body: str, variables: dict[str, str]) -> str:
        if self.dry_run:
            return f"HXDRY{uuid.uuid4().hex[:28]}"
        res = await self._request(
            "POST",
            _CONTENT_URL,
            json={
                "friendly_name": name,
                "language": language,
                "variables": variables,
                "types": {"twilio/text": {"body": body}},
            },
        )
        return str(res["sid"])

    async def submit_for_approval(self, *, content_sid: str, name: str, category: str) -> None:
        if self.dry_run:
            return
        await self._request(
            "POST",
            f"{_CONTENT_URL}/{content_sid}/ApprovalRequests/whatsapp",
            json={"name": name, "category": category.upper()},
        )

    async def list_templates(self) -> list[dict]:
        """Every Content template in the Twilio account, with its WhatsApp approval
        status: [{sid, name, language, body, variables, approval_status, category,
        rejection_reason}]. Dry-run returns two sample templates.
        """
        if self.dry_run:
            return [
                {"sid": "HXDRYSAMPLE0000000000000000000001", "name": "sample_appointment", "language": "en",
                 "body": "Your appointment is coming up on {{1}} at {{2}}", "variables": ["1", "2"],
                 "approval_status": "approved", "category": "utility", "rejection_reason": None},
                {"sid": "HXDRYSAMPLE0000000000000000000002", "name": "sample_greeting", "language": "en",
                 "body": "Hello {{1}}, thanks for choosing us.", "variables": ["1"],
                 "approval_status": "unsubmitted", "category": None, "rejection_reason": None},
            ]  # fmt: skip
        out: list[dict] = []
        url: str | None = _CONTENT_APPROVALS_URL
        params: dict | None = {"PageSize": 100}
        for _ in range(10):  # up to 1000 templates
            res = await self._request("GET", url, params=params)
            for c in res.get("contents") or []:
                body = next((t["body"] for t in (c.get("types") or {}).values() if isinstance(t, dict) and t.get("body")), "")
                names = list(dict.fromkeys(re.findall(r"\{\{\s*([^{}\s]+)\s*\}\}", body))) or sorted((c.get("variables") or {}).keys())
                wa = (c.get("approval_requests") or {}).get("whatsapp") or {}
                out.append({
                    "sid": c["sid"], "name": c.get("friendly_name") or c["sid"], "language": c.get("language") or "en",
                    "body": body, "variables": names, "approval_status": str(wa.get("status") or "unsubmitted"),
                    "category": (wa.get("category") or "").lower() or None, "rejection_reason": wa.get("rejection_reason") or None,
                })  # fmt: skip
            url, params = (res.get("meta") or {}).get("next_page_url"), None
            if not url:
                break
        return out

    async def approval_status(self, content_sid: str) -> tuple[str, str | None]:
        """Returns (twilio status, rejection reason). Dry-run auto-approves so
        the whole flow can be exercised without Meta.
        """
        if self.dry_run:
            return "approved", None
        res = await self._request("GET", f"{_CONTENT_URL}/{content_sid}/ApprovalRequests")
        wa = res.get("whatsapp") or {}
        return str(wa.get("status") or "unsubmitted"), (wa.get("rejection_reason") or None)

    async def delete_template(self, content_sid: str) -> None:
        if self.dry_run:
            return
        await self._request("DELETE", f"{_CONTENT_URL}/{content_sid}")
