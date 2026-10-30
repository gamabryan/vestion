"""Gmail do usuário: ler, buscar, rascunhar e enviar (API oficial, gratuita)."""
import base64
import html
import re
from email.message import EmailMessage
from email.utils import parseaddr

MAX_TEXT = 8000


def _headers(msg: dict) -> dict:
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def _sender(value: str) -> str:
    name, addr = parseaddr(value)
    return name or addr or value


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _find_part(payload: dict, mime: str) -> str | None:
    if payload.get("mimeType") == mime and payload.get("body", {}).get("data"):
        return _decode(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        found = _find_part(part, mime)
        if found is not None:
            return found
    return None


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(raw)


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT - 1] + "…"


def build_mime(to: str, subject: str, body: str, in_reply_to: str | None = None) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class GmailClient:
    def __init__(self, service):
        self.service = service

    @classmethod
    def from_credentials(cls, creds):
        from googleapiclient.discovery import build
        return cls(build("gmail", "v1", credentials=creds, cache_discovery=False))

    def _messages(self):
        return self.service.users().messages()

    def _summaries(self, query: str, max_results: int) -> list[dict]:
        listed = self._messages().list(userId="me", q=query, maxResults=max_results).execute()
        items = []
        for ref in listed.get("messages", []) or []:
            msg = self._messages().get(userId="me", id=ref["id"], format="metadata",
                                       metadataHeaders=["From", "Subject"]).execute()
            h = _headers(msg)
            items.append({"id": msg["id"], "de": _sender(h.get("from", "")), "assunto": h.get("subject", "(sem assunto)"),
                          "trecho": html.unescape(msg.get("snippet", "")),
                          "importante": "IMPORTANT" in (msg.get("labelIds") or [])})
        return items

    def unread(self, max_results: int = 5) -> list[dict]:
        return self._summaries("is:unread in:inbox", max_results)

    def today(self, now, max_results: int = 6) -> list[dict]:
        """E-mails que chegaram na caixa de entrada desde a meia-noite local."""
        midnight = now.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        return self._summaries(f"in:inbox after:{int(midnight.timestamp())}", max_results)

    def unread_count(self) -> int:
        return int(self.service.users().labels().get(userId="me", id="INBOX").execute().get("messagesUnread", 0))

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        return self._summaries(query, max_results)

    def read(self, message_id: str) -> dict:
        msg = self._messages().get(userId="me", id=message_id, format="full").execute()
        h = _headers(msg)
        payload = msg.get("payload", {})
        text = _find_part(payload, "text/plain")
        if text is None:
            raw_html = _find_part(payload, "text/html")
            text = html_to_text(raw_html) if raw_html else msg.get("snippet", "")
        return {"de": _sender(h.get("from", "")), "para": h.get("to", ""), "assunto": h.get("subject", ""),
                "data": h.get("date", ""), "texto": _clean_text(text)}

    def draft(self, to: str, subject: str, body: str) -> str:
        created = self.service.users().drafts().create(
            userId="me", body={"message": {"raw": build_mime(to, subject, body)}}).execute()
        return created["id"]

    def send(self, to: str, subject: str, body: str, reply_to_id: str | None = None) -> str:
        message: dict = {}
        in_reply_to = None
        if reply_to_id:
            original = self._messages().get(userId="me", id=reply_to_id, format="metadata",
                                            metadataHeaders=["Message-ID"]).execute()
            in_reply_to = _headers(original).get("message-id")
            message["threadId"] = original.get("threadId")
        message["raw"] = build_mime(to, subject, body, in_reply_to)
        return self._messages().send(userId="me", body=message).execute()["id"]
