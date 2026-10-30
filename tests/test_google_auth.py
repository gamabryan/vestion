import json

from google.auth.exceptions import RefreshError

from lia.google import auth
from lia.google.auth import SCOPES, connect_interactive, credentials_file, load_credentials, token_file


class FakeCreds:
    def __init__(self, expired=False, fail=False, scopes=None):
        self.expired = expired
        self.valid = not expired
        self.refresh_token = "r"
        self.fail = fail
        self.scopes = scopes if scopes is not None else list(SCOPES)

    def refresh(self, request):
        if self.fail:
            raise RefreshError("revogado")
        self.expired, self.valid = False, True

    def to_json(self):
        return json.dumps({"token": "novo"})


def _with_token(tmp_path, monkeypatch, creds):
    token_file(tmp_path).parent.mkdir(parents=True)
    token_file(tmp_path).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(auth.Credentials, "from_authorized_user_file", staticmethod(lambda path, scopes=None: creds))


def test_paths(tmp_path):
    assert credentials_file(tmp_path) == tmp_path / "google_credentials.json"
    assert token_file(tmp_path) == tmp_path / ".lia" / "google_token.json"
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.modify",
                      "https://www.googleapis.com/auth/calendar.events"]


def test_load_none_without_token(tmp_path):
    assert load_credentials(tmp_path) is None


def test_load_valid(tmp_path, monkeypatch):
    creds = FakeCreds()
    _with_token(tmp_path, monkeypatch, creds)
    assert load_credentials(tmp_path) is creds


def test_load_refreshes_expired_and_saves(tmp_path, monkeypatch):
    creds = FakeCreds(expired=True)
    _with_token(tmp_path, monkeypatch, creds)
    assert load_credentials(tmp_path) is creds
    assert json.loads(token_file(tmp_path).read_text(encoding="utf-8")) == {"token": "novo"}


def test_load_none_when_refresh_fails(tmp_path, monkeypatch):
    _with_token(tmp_path, monkeypatch, FakeCreds(expired=True, fail=True))
    assert load_credentials(tmp_path) is None


def test_load_none_when_scopes_differ(tmp_path, monkeypatch):
    _with_token(tmp_path, monkeypatch, FakeCreds(scopes=["https://www.googleapis.com/auth/gmail.readonly"]))
    assert load_credentials(tmp_path) is None


def test_connect_false_without_credentials_file(tmp_path):
    assert connect_interactive(tmp_path) is False
