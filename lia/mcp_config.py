"""Arquivo de configuração MCP que diz ao Claude Code como iniciar o servidor da Lia."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def write_mcp_config(path: Path, port: int, token: str) -> Path:
    config = {
        "mcpServers": {
            "lia": {
                "command": sys.executable,
                "args": ["-m", "lia.mcp_server"],
                "env": {
                    "LIA_BRIDGE_PORT": str(port),
                    "LIA_BRIDGE_TOKEN": token,
                    "PYTHONPATH": str(PROJECT_ROOT),
                },
            }
        }
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path
