"""Servidor MCP da Lia, iniciado pelo Claude Code via stdio.

Expõe a ferramenta de permissão (que mostra o cartão PODE / CANCELAR no app) e as ações
próprias da Lia: abrir coisas e rodar comandos de administrador.
"""
import json
import os
import urllib.request

from mcp.server.mcpserver import MCPServer

from lia.permissions import open_target, run_elevated

DENY_MESSAGE = "O usuário não autorizou."
BRIDGE_WAIT_S = 90  # maior que o tempo do cartão (60 s) para o app decidir primeiro

server = MCPServer("lia")


def _ask_bridge(tool_name: str, tool_input: dict) -> bool:
    port = os.environ["LIA_BRIDGE_PORT"]
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/confirm",
        data=json.dumps({"tool_name": tool_name, "input": tool_input}).encode(),
        headers={"X-Lia-Token": os.environ["LIA_BRIDGE_TOKEN"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=BRIDGE_WAIT_S) as resp:
        return bool(json.loads(resp.read()).get("approved"))


# Sem saída estruturada: o Claude Code espera o JSON da decisão como texto puro.
@server.tool(structured_output=False)
def lia_confirmar(tool_name: str, input: dict) -> str:
    """Pede ao usuário, no cartão da central, para aprovar uma ação."""
    try:
        approved = _ask_bridge(tool_name, input)
    except Exception:
        approved = False  # ponte fora do ar nunca vira aprovação
    if approved:
        return json.dumps({"behavior": "allow", "updatedInput": input})
    return json.dumps({"behavior": "deny", "message": DENY_MESSAGE}, ensure_ascii=False)


@server.tool()
def lia_abrir(alvo: str) -> str:
    """Abre um programa do menu Iniciar (pelo nome), uma pasta, um site ou um documento para o usuário ver.

    Scripts e executáveis não abrem por aqui: use um comando, que passa pela confirmação.
    """
    return open_target(alvo)


@server.tool()
def lia_admin(comando: str) -> str:
    """Roda um comando PowerShell como administrador; o Windows pede a permissão ao usuário."""
    return run_elevated(comando)


if __name__ == "__main__":
    server.run("stdio")
