"""Acesso à conta Google do usuário (OAuth de app para computador, criado por ele no Google Cloud)."""
import json
import logging
import os
from pathlib import Path

import win32crypt
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify",
          "https://www.googleapis.com/auth/calendar.events",
          "https://www.googleapis.com/auth/tasks"]
log = logging.getLogger(__name__)


def credentials_file(workspace: Path) -> Path:
    return Path(workspace) / "google_credentials.json"


def token_file(workspace: Path) -> Path:
    # Fica em .lia, pasta que o Claude é proibido de ler; e o conteúdo é criptografado pelo Windows.
    return Path(workspace) / ".lia" / "google_token.json"


def _save_info(info: dict, workspace: Path) -> None:
    """Grava o token criptografado (DPAPI, só este usuário do Windows abre) e de forma atômica."""
    path = token_file(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = win32crypt.CryptProtectData(json.dumps(info).encode("utf-8"), "Vestion", None, None, None, 0)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, path)  # o app e o servidor MCP podem gravar ao mesmo tempo


def _load_info(workspace: Path) -> dict:
    _, data = win32crypt.CryptUnprotectData(token_file(workspace).read_bytes(), None, None, None, 0)
    return json.loads(data)


def load_credentials(workspace: Path):
    """Credenciais prontas, ou None se não houver conexão válida (pede reconectar).

    Sem internet, levanta TransportError: quem chama mantém o que já mostrava, em vez de "desconectado".
    """
    if not token_file(workspace).exists():
        return None
    try:
        info = _load_info(workspace)
        if set(info.get("scopes") or []) != set(SCOPES):
            return None
        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if creds.expired:
            creds.refresh(Request())
            _save_info(json.loads(creds.to_json()), workspace)
        return creds if creds.valid else None
    except TransportError:
        raise
    except (RefreshError, ValueError, OSError, Exception) as e:  # revogado, arquivo corrompido ou de outro usuário
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
    _save_info(json.loads(creds.to_json()), workspace)
    return True
