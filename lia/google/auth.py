"""Acesso à conta Google do usuário (OAuth de app para computador, criado por ele no Google Cloud)."""
import logging
from pathlib import Path

from google.auth.exceptions import GoogleAuthError, RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify",
          "https://www.googleapis.com/auth/calendar.events"]
log = logging.getLogger(__name__)


def credentials_file(workspace: Path) -> Path:
    return Path(workspace) / "google_credentials.json"


def token_file(workspace: Path) -> Path:
    # Fica em .lia, pasta que o Claude é proibido de ler.
    return Path(workspace) / ".lia" / "google_token.json"


def _save(creds, workspace: Path) -> None:
    path = token_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")


def load_credentials(workspace: Path):
    """Credenciais prontas para uso, ou None se não houver conexão válida (pede reconectar)."""
    path = token_file(workspace)
    if not path.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
        if set(creds.scopes or []) != set(SCOPES):
            return None
        if creds.expired:
            creds.refresh(Request())
            _save(creds, workspace)
        return creds if creds.valid else None
    except (RefreshError, GoogleAuthError, ValueError, OSError) as e:
        log.warning("conexão Google inválida: %s", e)
        return None


def connect_interactive(workspace: Path) -> bool:
    """Abre o navegador para o usuário entrar e autorizar; ele faz o login, nunca o Vestion."""
    secrets = credentials_file(workspace)
    if not secrets.exists():
        return False
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True, timeout_seconds=300,
                                      success_message="Pronto! Pode fechar esta aba e voltar para o Vestion.")
    except Exception as e:
        log.warning("falha ao conectar Google: %s", e)
        return False
    _save(creds, workspace)
    return True
