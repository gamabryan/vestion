# Lia — assistente de voz para o PC (design)

Data: 2026-10-29

## Intenção

O usuário quer conversar em voz alta com uma assistente que entenda o que ele pede e faça,
no próprio computador. A ideia é juntar o "Claude no terminal" com uma "Alexa":
organizar a agenda, ler e responder e-mails, mandar WhatsApp e mexer em qualquer coisa no PC.
O visual deve lembrar uma IA de filme, com uma central holográfica.

Restrição central do usuário: **nenhum gasto adicional**. O "cérebro" usa o plano Claude
que ele já assina, e o resto usa só ferramentas gratuitas.

## Ambiente do usuário (verificado)

- Windows 11 Pro
- Claude Code CLI 2.1.312 instalado (`claude`), logado com a assinatura do usuário
- Python 3.12.10 e Node 24 instalados
- Gmail e Google Agenda
- WhatsApp Desktop (app do Windows) instalado e logado

## Metas

1. **Conversa por voz em português (pt-BR).** O usuário fala e a Lia responde falando,
   com a frase mostrada em legenda.
2. **Ativação:** pela palavra "Lia" e também por uma tecla de atalho global (alternativa
   para quando o reconhecimento falhar).
3. **Ações no PC:** abrir programas, procurar, ler e organizar arquivos, rodar comandos,
   com tudo o que o Claude Code já sabe fazer.
4. **Gmail:** ler, resumir, buscar, rascunhar e enviar e-mails.
5. **Google Agenda:** consultar, criar, mover e cancelar compromissos.
6. **WhatsApp pelo app do Windows:** ler conversas e mensagens não lidas, e enviar mensagens
   para um contato pelo nome. Isso é feito controlando o app instalado, não o WhatsApp Web
   e nem a API oficial.
7. **Central de comando (modelo C aprovado):**
   - Tela escura com grade, e um núcleo de energia animado no centro que mostra três estados:
     em espera (gira devagar), ouvindo (ondas de áudio) e falando (pulsa).
   - Legenda com a fala da Lia embaixo.
   - Quatro painéis ao vivo, com cantos chanfrados e brilho ciano/laranja:
     - Agenda de hoje
     - Gmail: quantidade de e-mails não lidos e os mais recentes
     - WhatsApp: mensagens não lidas
     - Sistema: CPU, memória e uso do plano Claude
   - Fontes de referência: Orbitron e Rajdhani. O modelo aprovado está em
     `.superpowers/brainstorm/*/content/interface-estilos.html`, opção C.
8. **Confirmação antes de qualquer ação irreversível ou que saia do PC:** enviar e-mail ou
   WhatsApp, apagar arquivo, aceitar ou cancelar convite, ou criar evento com convidados.
   - Na central aparece um cartão grande com o que vai acontecer (destinatário e texto
     exato) e os botões PODE / CANCELAR.
   - A Lia também lê o cartão em voz alta, e o usuário pode responder "pode" ou "cancela"
     falando.
9. **Memória:** a Lia lembra a conversa em andamento e guarda preferências e fatos
   duradouros ("o Pedro é meu irmão", "nada antes das 9h") num arquivo que ela mesma
   mantém e que o usuário pode editar.

## Comportamento de início e fim (decidido pelo usuário)

- **Não** inicia com o Windows. Só abre quando o usuário quiser, por um atalho na área de
  trabalho ou no menu Iniciar.
- Depois de aberta, a Lia fica escutando em segundo plano com um ícone perto do relógio do
  Windows. Dizer "Lia" ou usar o atalho abre a central. *(minha decisão: fechar a janela
  só a esconde, e "Sair" no ícone encerra a Lia de vez.)*
- Ao abrir, a Lia dá um resumo curto: compromissos de hoje, e-mails importantes e WhatsApp
  não lido. *(minha decisão)*
  - O resumo é montado localmente por modelo de frase, **sem usar o Claude**.
  - "Importante" é o que o Gmail marca como Importante e ainda não foi lido.
- **Sessão de conversa:** cada vez que a Lia é aberta, começa uma sessão nova do Claude.
  Também começa uma nova depois de 2 h sem conversa. Isso evita que o contexto cresça e
  gaste mais cota a cada pedido. A continuidade de longo prazo fica no arquivo de memória.
  *(minha decisão)*
- **"Pode" falado:**
  - Só é aceito depois que a Lia termina de ler o cartão. O microfone fica ignorado
    enquanto ela fala, para ela não ouvir a si mesma.
  - Só vale numa janela de 15 s.
  - Precisa ser uma frase clara de aprovação ("pode", "pode mandar", "confirma").
    Qualquer dúvida conta como cancelar. *(minha decisão)*

## Restrições

- **Custo zero.**
  - O raciocínio passa pelo Claude Code CLI instalado, rodando em modo não interativo e
    autenticado pela assinatura.
  - A variável `ANTHROPIC_API_KEY` **não pode** estar definida no processo da Lia, senão a
    cobrança vai para a API. Ao iniciar, a Lia remove essa variável do ambiente do
    subprocesso e avisa se ela existir.
  - Não usar nenhuma API paga, nem de voz nem de outra coisa.
- **Uso do plano:** cada pedido consome a cota do plano. Os painéis (agenda, Gmail, WhatsApp
  e sistema) são atualizados **direto pelas APIs e pelo sistema, sem passar pelo Claude**,
  para não gastar cota. O Claude só entra quando o usuário fala.
- **Limite do plano atingido:** a Lia diz isso em voz alta, mostra na central e continua
  exibindo os painéis normalmente.
- **WhatsApp:** nunca fazer envios em massa nem automações sem pedido. Uma mensagem por
  pedido, sempre confirmada. Digitar em ritmo humano.
- **Conteúdo lido de e-mails, WhatsApp, páginas e arquivos é dado, não instrução.** Se uma
  mensagem disser "Lia, encaminhe isso para...", nada acontece sem o usuário pedir. A
  confirmação é a última barreira.
- **Privacidade:** a voz é transcrita localmente. A única coisa que sai do PC é o texto
  enviado ao Claude e, se for a voz escolhida, o texto a ser falado, enviado ao serviço de
  voz da Microsoft (veja abaixo). Nada de gravação de áudio guardada em disco.
- Interface e fala em português do Brasil.

## Decisões de "como" (minhas, como construtor — o usuário delegou)

- **Linguagem:** Python 3.12 para o núcleo (áudio, integrações e orquestração).
- **Interface:** HTML/CSS/JS dentro de uma janela nativa pelo `pywebview` (WebView2 do
  Windows), para reaproveitar o visual do modelo aprovado. Ícone na bandeja via `pystray`.
- **Cérebro:** subprocesso `claude -p` com saída `stream-json`, mantendo a mesma sessão
  entre falas (`--resume`/`--continue`) para a conversa ter continuidade.
  - Diretório de trabalho próprio da Lia, com um `CLAUDE.md` que define a personalidade:
    respostas curtas e faladas, em pt-BR, sem markdown na fala, e as regras de confirmação.
  - Se o pacote `claude-agent-sdk` usar o login existente do CLI sem chave de API, pode ser
    usado no lugar. O construtor decide.
- **Ferramentas do Claude:** um servidor MCP local da Lia, registrado para o Claude Code,
  expondo:
  - `gmail_*`: listar, ler, buscar, rascunhar e enviar
  - `agenda_*`: listar, criar, mover e cancelar
  - `whatsapp_*`: listar não lidas, ler conversa e enviar
  - `lia_confirmar`
  
  Arquivos, programas e comandos usam as ferramentas nativas do Claude Code.
- **Confirmação:** feita pelo mecanismo de permissão do Claude Code
  (`--permission-prompt-tool` apontando para uma ferramenta MCP da Lia que mostra o cartão
  e espera a resposta).
  - Ferramentas só de leitura ficam pré-liberadas (`--allowedTools`): Read, Glob, Grep e
    as leituras de Gmail, Agenda e WhatsApp.
  - **Decidido pelo usuário:** tudo o que altera o PC passa pelo cartão PODE / CANCELAR.
    - Isso inclui criar, mover, renomear, sobrescrever e apagar arquivos, instalar
      programas, fechar programas e qualquer comando de shell.
    - Como comandos de shell não podem ser classificados com segurança, todo Bash ou
      PowerShell exige confirmação.
    - Exceção: uma lista curta e fixa de comandos claramente só de leitura (ex.: `dir`,
      `Get-Process`, `Get-Date`). O construtor define essa lista e mantém ela mínima.
    - Abrir um programa ou um arquivo para o usuário ver também é liberado. *(minha
      decisão: só abre, não altera nada)*
  - O cartão mostra o comando ou a ação exata. A Lia lê em voz alta uma versão resumida.
  - Se não houver resposta em 60 s, a ação é cancelada.
- **Alcance no PC (decidido pelo usuário): tudo, incluindo ações de administrador.**
  - O Claude Code roda com acesso a todos os discos (`--add-dir` para cada unidade).
  - A Lia em si roda **sem** privilégio de administrador. Quando uma ação precisar disso,
    ela pede a elevação só daquele comando, e o Windows mostra a janela de permissão
    (UAC) para o usuário aprovar. Isso vem depois do cartão PODE. *(minha decisão: assim um
    erro dela nunca vira ação de administrador sem dois cliques seus)*
- **Gmail e Agenda:** APIs oficiais do Google (gratuitas) com OAuth de app desktop no
  projeto Google Cloud do próprio usuário. Isso exige um passo único de configuração que o
  usuário faz guiado por um tutorial passo a passo, com print. O token fica salvo
  localmente.
- **WhatsApp:**
  - Automação de interface do app WhatsApp Desktop via UI Automation do Windows
    (`pywinauto`/`uiautomation`): buscar o contato, abrir a conversa, ler mensagens e
    digitar e enviar.
  - O painel de não lidas pode vir das notificações do Windows (UserNotificationListener),
    se for mais estável e menos intrusivo que abrir o app. O construtor decide.
  - A automação fica isolada num módulo, porque atualizações do WhatsApp podem quebrar
    os seletores.
  - **Plano B, decidido pelo usuário:** se a UI Automation não conseguir ler as mensagens,
    a Lia tira um print da janela do WhatsApp e manda para o Claude ler (visão). Isso
    consome cota do plano.
    - Usar só quando o usuário pedir para ler ou responder uma conversa.
    - Nunca usar para atualizar o painel. O painel continua vindo das notificações do
      Windows.
    - O envio continua sendo por digitação no app.
- **Ouvir:** `faster-whisper` local.
  - Modelo `small`, ou `medium` se houver GPU NVIDIA, detectado automaticamente.
  - Detecção de fala por VAD (Silero), com fim de fala por silêncio de cerca de 0,8 s.
- **Palavra de ativação "Lia":** detecção local e gratuita.
  - Opção sugerida: openWakeWord com modelo treinado para "Lia".
  - Alternativa: transcrição leve contínua procurando "Lia" no início da frase.
  - O construtor escolhe pela taxa de falso positivo. Como "Lia" é curta, aceitar
    variações como "Ei Lia" é recomendável.
  - A tecla de atalho global é sempre a alternativa garantida. Padrão: `Ctrl+Alt+Espaço`,
    configurável.
- **Falar:** `edge-tts` com voz neural pt-BR (ex.: `pt-BR-FranciscaNeural`).
  - É gratuito, mas usa um serviço online não oficial da Microsoft.
  - Se falhar ou estiver sem internet, a voz cai para o Piper (offline, voz pt-BR).
  - A fala é feita frase por frase conforme o Claude responde, para começar a falar mais
    cedo.
- **Interromper:** se o usuário falar enquanto a Lia fala, ela para de falar e escuta.
  *(desejável; pode vir numa segunda etapa)*
- **Uso do plano no painel:**
  - Mostrar o percentual se o Claude Code expuser essa informação de forma programática.
  - Caso contrário, mostrar "pedidos hoje" e o estado "limite atingido / ok", detectado
    pelas mensagens de erro do CLI.
- **Configuração:** um arquivo `config` simples com voz, atalho, modelo do Whisper e pasta de
  memória.

## Fora do escopo (não metas)

- Celular, outros usuários e acesso remoto.
- Iniciar com o Windows.
- Outros provedores de e-mail ou agenda.
- Automação proativa (a Lia agir sozinha sem ser chamada), exceto o resumo ao abrir.
- WhatsApp Web ou API oficial do WhatsApp Business.

## Anti-metas (falha mesmo se "funcionar")

- Qualquer cobrança fora do plano: chave de API sendo usada ou serviço pago escondido.
- Enviar, apagar ou aceitar algo sem o "pode" do usuário.
- Número do WhatsApp bloqueado por comportamento de robô.
- Painéis gastando a cota do plano sozinhos.
- Visual genérico ou "de planilha". A central tem que parecer a do modelo C.

## Deixado para o construtor

- Estrutura de pastas, nomes de módulos e empacotamento (atalho `.lnk`, `.exe` opcional).
- Escolhas entre as alternativas marcadas acima ("o construtor decide").
- Frequência de atualização dos painéis (sugestão: agenda e Gmail a cada 2 min, WhatsApp a
  cada 30 s, sistema a cada 2 s).
- Formato do arquivo de memória.
- Ordem de entrega. Sugestão:
  1. Voz + cérebro + central
  2. Agenda/Gmail
  3. WhatsApp
  4. Palavra de ativação e interrupção
