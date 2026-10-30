import base64
import email
from email import policy

from lia.google.gmail import GmailClient, build_mime
from tests.google_fakes import fake_service


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode()


def msg(mid, frm, subject, snippet, labels=("UNREAD", "INBOX")):
    return {"id": mid, "threadId": "t" + mid, "snippet": snippet, "labelIds": list(labels),
            "payload": {"headers": [{"name": "From", "value": frm}, {"name": "Subject", "value": subject},
                                    {"name": "To", "value": "eu@gmail.com"}, {"name": "Date", "value": "Thu, 29 Oct 2026 10:00:00 -0300"},
                                    {"name": "Message-ID", "value": f"<{mid}@mail.gmail.com>"}],
                        "mimeType": "text/plain", "body": {"data": b64("corpo")}}}


MESSAGES = {"1": msg("1", '"Ana Souza" <ana@x.com>', "Proposta revisada", "Segue a proposta", ("UNREAD", "INBOX", "IMPORTANT")),
            "2": msg("2", "banco@y.com", "Fatura disponível", "Sua fatura")}


def client(extra=None):
    responses = {
        "users.messages.list": {"messages": [{"id": "1"}, {"id": "2"}]},
        "users.messages.get": lambda userId, id, **kw: MESSAGES[id],
        "users.labels.get": {"messagesUnread": 7},
        "users.messages.send": {"id": "enviado1"},
        "users.drafts.create": {"id": "rascunho1"},
    }
    responses.update(extra or {})
    service, calls = fake_service(responses)
    return GmailClient(service), calls


def test_unread_parses_from_subject_snippet_important():
    c, calls = client()
    items = c.unread(5)
    assert items[0] == {"id": "1", "de": "Ana Souza", "assunto": "Proposta revisada", "trecho": "Segue a proposta", "importante": True}
    assert items[1]["de"] == "banco@y.com" and items[1]["importante"] is False
    assert calls[0][1]["q"] == "is:unread in:inbox"


def test_unread_count():
    c, _ = client()
    assert c.unread_count() == 7


def test_read_prefers_plain_text():
    m = msg("3", "a@b.com", "Oi", "x")
    m["payload"] = {"mimeType": "multipart/alternative", "headers": m["payload"]["headers"], "parts": [
        {"mimeType": "text/html", "body": {"data": b64("<p>versão html</p>")}},
        {"mimeType": "text/plain", "body": {"data": b64("versão texto")}}]}
    c, _ = client({"users.messages.get": m})
    assert c.read("3")["texto"] == "versão texto"


def test_read_html_only_strips_tags_and_truncates():
    html = "<html><style>.x{color:red}</style><script>alert(1)</script><p>Olá &amp; bem-vindo</p>" + "<div>palavra</div>" * 3000
    m = msg("4", "a@b.com", "Oi", "x")
    m["payload"] = {"mimeType": "text/html", "headers": m["payload"]["headers"], "body": {"data": b64(html)}}
    c, _ = client({"users.messages.get": m})
    texto = c.read("4")["texto"]
    assert texto.startswith("Olá & bem-vindo")
    assert "<" not in texto and "alert" not in texto and "color" not in texto
    assert len(texto) <= 8000 and texto.endswith("…")


def test_build_mime_utf8_subject_roundtrip():
    raw = build_mime("ana@x.com", "Reunião às 15h", "Olá, tudo certo?")
    parsed = email.message_from_bytes(base64.urlsafe_b64decode(raw), policy=policy.default)
    assert parsed["Subject"] == "Reunião às 15h"
    assert parsed["To"] == "ana@x.com"
    assert parsed.get_content().strip() == "Olá, tudo certo?"


def test_send_reply_sets_thread_and_headers():
    c, calls = client()
    assert c.send("ana@x.com", "Re: Proposta revisada", "Recebido, obrigado.", reply_to_id="1") == "enviado1"
    path, kw = [x for x in calls if x[0] == "users.messages.send"][0]
    assert kw["body"]["threadId"] == "t1"
    parsed = email.message_from_bytes(base64.urlsafe_b64decode(kw["body"]["raw"]), policy=policy.default)
    assert parsed["In-Reply-To"] == "<1@mail.gmail.com>"
    assert parsed["References"] == "<1@mail.gmail.com>"


def test_draft_returns_id():
    c, calls = client()
    assert c.draft("ana@x.com", "Oi", "texto") == "rascunho1"
    assert "raw" in [x for x in calls if x[0] == "users.drafts.create"][0][1]["body"]["message"]
