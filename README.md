# Lia

Assistente de voz para o seu Windows. Você fala, ela entende e faz, usando o Claude Code do seu plano (sem custo extra).

## Instalar (uma vez)

No PowerShell, dentro de `D:\Lia`:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File scripts\criar_atalho.ps1
```

Isso cria o atalho **Lia** na Área de Trabalho e no menu Iniciar. Ela **não** inicia com o Windows.

Requisito: o Claude Code instalado e logado com a sua conta (`claude` no terminal).

## Usar

- Abra pelo atalho **Lia**. A central aparece e ela diz "Oi, estou pronta."
- Aperte **Ctrl + Alt + Espaço** e fale. Ela para de ouvir quando você faz uma pausa.
- Se apertar o atalho enquanto ela fala, ela para e escuta você.
- Fechar a janela só esconde a Lia; ela fica no ícone perto do relógio. Para encerrar: clique com o botão direito no ícone → **Sair**.

## Confirmações

Tudo que altera o computador (criar, mover, apagar arquivos, instalar, comandos) mostra o cartão **PODE / CANCELAR**.
Você pode clicar, apertar Enter / Esc, ou dizer **"pode"** depois que ela terminar de ler o cartão (até 15 segundos).
Qualquer outra resposta cancela. Sem resposta em 60 segundos, cancela.

Comandos de administrador também mostram a janela de permissão do próprio Windows.

## Personalizar

Copie `config.example.toml` para `config.toml` e ajuste: tecla de atalho, voz, modelo do Whisper.

## Memória

A Lia guarda fatos e preferências em `C:\Users\<você>\Lia\memoria.md`. Pode abrir e editar à vontade.
A personalidade dela fica em `C:\Users\<você>\Lia\CLAUDE.md`.

## Custos

- O raciocínio usa o seu plano Claude. Se aparecer **LIMITE ATINGIDO**, espere a janela do plano renovar.
- Se existir uma variável `ANTHROPIC_API_KEY` no seu PC, a Lia a ignora para nunca cobrar pela API.
- Voz e reconhecimento de fala são gratuitos (Whisper roda no seu PC).

## Problemas

O registro fica em `D:\Lia\lia.log`.
