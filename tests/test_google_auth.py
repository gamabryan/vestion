import json

import pytest
from google.auth.exceptions import RefreshError, TransportError

from lia.google import auth
from lia.google.auth import SCOPES, connect_interactive, credentials_file, load_credentials, token_file


class FakeCreds:
    def __init__(self, expired=False, fail=None):
        self.expired = expired
        self.valid = not expired
        self.fail = fail

    def refresh(self, request):
        if self.fail:
            raise self.fail
        self.expired, self.valid = False, True

    def to_json(self):
        return json.dumps({"token": "SEGREDO-123", "refresh_token": "r", "scopes": SCOPES})


def _with_token(tmp_path, monkeypatch, creds, scopes=SCOPES):
    auth._save_info({"token": "SEGREDO-123", "refresh_token": "r", "scopes": scopes}, tmp_path)
    monkeypatch.setattr(auth.Credentials, "from_authorized_user_info", staticmethod(lambda info, scopes=None: creds))


def test_paths(tmp_path):
    assert credentials_file(tmp_path) == tmp_path / "google_credentials.json"
    assert token_file(tmp_path) == tmp_path / ".lia" / "google_token.json"
    assert SCOPES == ["https://www.googleapis.com/auth/gmail.modify",
                      "https://www.googleapis.com/auth/calendar.events",
                      "https://www.googleapis.com/auth/tasks"]


def test_token_is_encrypted_at_rest(tmp_path):
    auth._save_info({"token": "SEGREDO-123", "scopes": SCOPES}, tmp_path)
    raw = token_file(tmp_path).read_bytes()
    assert b"SEGREDO" not in raw
    assert auth._load_info(tmp_path)["token"] == "SEGREDO-123"
    assert not list(token_file(tmp_path).parent.glob("*.tmp"))  # gravação atômica não deixa sobra


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
    assert auth._load_info(tmp_path)["token"] == "SEGREDO-123"


def test_load_none_when_refresh_revoked(tmp_path, monkeypatch):
    _with_token(tmp_path, monkeypatch, FakeCreds(expired=True, fail=RefreshError("revogado")))
    assert load_credentials(tmp_path) is None


def test_offline_refresh_is_not_disconnected(tmp_path, monkeypatch):
    _with_token(tmp_path, monkeypatch, FakeCreds(expired=True, fail=TransportError("sem internet")))
    with pytest.raises(TransportError):
        load_credentials(tmp_path)  # quem chama mantém os dados antigos; não é "desconectado"


def test_load_none_when_file_scopes_differ(tmp_path, monkeypatch):
    _with_token(tmp_path, monkeypatch, FakeCreds(), scopes=["https://www.googleapis.com/auth/gmail.readonly"])
    assert load_credentials(tmp_path) is None


def test_load_none_when_file_is_garbage(tmp_path):
    token_file(tmp_path).parent.mkdir(parents=True)
    token_file(tmp_path).write_bytes(b"lixo")
    assert load_credentials(tmp_path) is None


def test_connect_false_without_credentials_file(tmp_path):
    assert connect_interactive(tmp_path) is False
