# Conectar o Vestion ao seu Gmail e Google Agenda

Você faz isso **uma vez só** e leva uns 10 minutos. É gratuito.

Você cria um "acesso" no Google em seu próprio nome, e o Vestion usa esse acesso para ler sua agenda e seus e-mails. O login e as autorizações são sempre feitos por você; o Vestion nunca vê a sua senha.

## 1. Criar o projeto

1. Abra **https://console.cloud.google.com** e entre com a sua conta Google (a do Gmail que você quer conectar).
2. No topo, clique no seletor de projetos → **Novo projeto**.
3. Nome: `Vestion`. Clique em **Criar** e espere terminar.
4. Confira que o projeto **Vestion** está selecionado no topo.

## 2. Ligar o Gmail e a Agenda

1. No menu (☰), vá em **APIs e serviços → Biblioteca**.
2. Procure **Gmail API**, abra e clique em **Ativar**.
3. Volte à Biblioteca, procure **Google Calendar API**, abra e clique em **Ativar**.

## 3. Tela de consentimento

1. Vá em **APIs e serviços → Tela de consentimento OAuth** (ou **Google Auth Platform → Branding**).
2. Tipo de usuário: **Externo**. Clique em **Criar**.
3. Nome do app: `Vestion`. E-mail de suporte e e-mail de contato: o seu. Salve e continue até o fim.
4. Em **Público-alvo** (ou **Usuários de teste**), adicione o seu próprio e-mail como usuário de teste.
5. **Importante:** clique em **Publicar app** e confirme.
   - Sem isso, o Google desconecta o Vestion a cada 7 dias.
   - O app vai aparecer como "não verificado". Para uso pessoal, isso é normal.

## 4. Criar a credencial

1. Vá em **APIs e serviços → Credenciais** (ou **Google Auth Platform → Clientes**).
2. **Criar credenciais → ID do cliente OAuth**.
3. Tipo de aplicativo: **App para computador**. Nome: `Vestion`. Clique em **Criar**.
4. Na janela que abrir, clique em **Baixar JSON**.
5. Renomeie o arquivo baixado para `google_credentials.json` e coloque-o em:

   ```
   C:\Users\PC\Lia\google_credentials.json
   ```

## 5. Conectar

1. Com o Vestion aberto, clique com o botão direito no ícone dele perto do relógio → **Conectar Google**.
2. O navegador abre. Entre na sua conta e autorize.
   - Na tela "O Google não verificou este app", clique em **Avançado → Acessar Vestion (não seguro)**. O app é seu, criado por você.
   - Marque as permissões de **Gmail** e **Agenda** e clique em **Continuar**.
3. Quando aparecer "Pronto! Pode fechar esta aba", volte ao Vestion. Ele avisa "Pronto, conectei sua conta Google" e os painéis passam a mostrar sua agenda e seus e-mails.

## O que o Vestion pode fazer

- **Sem perguntar:** ler e resumir e-mails, procurar, criar rascunhos, ver a agenda, criar compromissos só seus e mudar horários.
- **Com o cartão PODE / CANCELAR:**
  - enviar e-mail;
  - cancelar compromisso;
  - criar compromisso com convidados, porque isso manda convites.

## Para desconectar

Abra **https://myaccount.google.com/permissions**, encontre **Vestion** e clique em **Remover acesso**.
