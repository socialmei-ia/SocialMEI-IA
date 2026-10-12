# Contas individuais: piloto protegido

A migration `010_account_authentication.sql` e a API implementam contas persistidas, convites, sessões revogáveis e separação dos negócios. A ativação é explícita: `TEAM_AUTH_ENABLED` permanece `false` até existir um administrador e a configuração privada do site estar preparada. Aplicar a migration não cria uma senha, não transforma usuários antigos em administradores e não abre cadastro público.

O GitHub Pages continua sendo uma demonstração local. No servidor da equipe, a proteção Basic do Caddy permanece ativa durante este piloto: primeiro a pessoa passa pela proteção do site e depois entra na própria conta da aplicação. A retirada dessa proteção e a abertura ao público continuam dependendo da decisão do dono do projeto.

## O que é persistido

| Informação                                                           | Persistência                                                                        |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Usuário, e-mail, nome e telefone                                     | PostgreSQL `users`                                                                  |
| Senha                                                                | Hash Argon2id em `auth_credenciais`; nunca texto puro                               |
| Administrador do projeto                                             | Flag separada do papel de administrador de um negócio; criada pelo terminal privado |
| Negócio e vínculo do usuário                                         | `workspaces` e `workspace_members`                                                  |
| Nome, CNPJ, telefone, horário, Pix e logo do negócio                 | Configuração do workspace no PostgreSQL                                             |
| Clientes, produtos, vendas e financeiro                              | CRM do workspace autenticado                                                        |
| Sessões, convites e auditoria de acesso                              | Tabelas `auth_*`                                                                    |
| Tema, notificações, regras, rascunhos e preferências de apresentação | Ainda locais no navegador, separados ao trocar de conta                             |
| WhatsApp                                                             | Apenas fundação 009; conexão continua aguardando o chip dedicado                    |

O administrador inicial usa o workspace `team`, preservando os registros compartilhados existentes. Cada cadastro por convite cria um workspace próprio, vazio, com papel `owner` e sem administração global. Não há seleção livre de workspace ou promoção pelo formulário. Convites atuais criam negócios independentes; não convidam colegas para um negócio existente.

As APIs de gestão resolvem o workspace pela sessão no servidor. IDs de outra empresa não dão acesso a registros nem podem ser usados para criar vínculos cruzados. A credencial técnica n8n continua limitada aos cinco GETs de leitura do workspace `team`; não recebe acesso às novas empresas, administração ou senhas.

## Senhas e sessões

- Senha nova de 12 a 128 caracteres, com Argon2id (19 MiB, duas iterações, paralelismo 1). No máximo duas verificações/gerações de hash simultâneas por processo.
- Cookie `__Host-socialmei-session`: `Secure`, `HttpOnly`, `SameSite=Lax`, caminho `/`, sem domínio. O banco guarda somente o SHA-256 de um token aleatório de 48 bytes.
- Sem “Lembrar de mim”: cookie de sessão do navegador, com limite de 24 horas no banco. Com a opção: até sete dias. Restaurar uma sessão do navegador depende também do comportamento do navegador.
- Sair revoga a sessão atual. Alterar ou recuperar a senha e desativar a conta revogam todas as sessões dessa conta. Reativar exige novo login.
- Escritas exigem a origem HTTPS configurada e CSRF vinculado à sessão. Login/cadastro exigem JSON e o cabeçalho da aplicação. Respostas de autenticação não são cacheadas; validação não devolve valores de senhas/convites.
- Login/cadastro: até dez tentativas por e-mail em 15 minutos e 30 por ação/minuto no piloto. A troca de senha também tem limite por conta. Contadores ficam no banco, sobrevivendo a reinícios. O limite global pode afetar outras pessoas se houver muitas tentativas; revisar capacidade e proteção de borda antes da abertura pública.

O vínculo de apresentação no navegador é conferido contra `/auth/me`; uma entrada visual ou `sessionStorage` da demonstração não libera a aplicação. Ao trocar/sair, o site arquiva trabalho local da conta anterior e recarrega com o contexto correto. Esses arquivos locais não são uma barreira criptográfica: alguém com acesso ao mesmo perfil do navegador pode inspecioná-los. Para dispositivos compartilhados, use perfis separados e não marque “Lembrar de mim”. Backups JSON normais e limpeza da conta atual excluem arquivos internos de outras contas. O trabalho local anterior à ativação fica preservado em um arquivo interno `legacy`; não é importado para novos MEIs.

## Atualização e ativação no servidor

Use uma revisão aprovada e fixa, com `COMPOSE_PARALLEL_LIMIT=1` no servidor pequeno. Crie um backup antes da atualização e outro após ativar. Não use `git reset --hard`, não altere o projeto legado `/home/ubuntu/socialmei` e não remova volumes.

1. Na pasta `/home/ubuntu/socialmei-team`, execute o backup, confira ausência de alterações rastreadas, busque o commit aprovado e atualize o worktree destacado.
2. Recrie a stack com `docker compose --env-file .env.team -f compose.team.yaml up -d --build --wait --wait-timeout 180`. O migrador aplica 010 antes da API iniciar. Nesta primeira fase o login real ainda está desligado.
3. Crie o seu administrador **em terminal interativo**, sem colocar senha em comandos, arquivos, GitHub ou chat. No PowerShell:

```powershell
ssh -t -o IdentitiesOnly=yes `
  -i "C:\Users\richa\OneDrive\Documentos\SocialMEI-Servidor\socialmei-key.pem" `
  ubuntu@54.94.213.7 `
  "cd /home/ubuntu/socialmei-team && docker compose --env-file .env.team -f compose.team.yaml exec -it team-api python account_admin.py create-admin"
```

O terminal pergunta seu e-mail, nome e senha duas vezes. A senha não aparece. E-mails existentes não são promovidos automaticamente; se isso acontecer, pare e confira o cadastro pelo procedimento privado. Repetir a criação de administrador é recusado.

4. Depois da criação, no terminal Ubuntu:

```bash
(
set -euo pipefail
cd /home/ubuntu/socialmei-team
python3 tools/team-accounts.py enable
docker compose --env-file .env.team -f compose.team.yaml \
  up -d --no-deps --force-recreate --wait --wait-timeout 180 team-api team-gateway
python3 tools/team-maintenance.py doctor
python3 tools/team-maintenance.py backup
)
```

O preparador confere a conta administrativa, os quatro módulos remotos na API do mesmo site e a proteção Basic. Faz uma cópia privada da configuração anterior, grava `TEAM_AUTH_ENABLED=true` e a configuração pública `auth` sem credenciais. Ele não reinicia serviços; os comandos seguintes aplicam a configuração.

5. Abra o site por HTTPS, passe pela proteção atual e entre com seu e-mail/senha próprios. Confira seus dados de gestão existentes e **Configurações → Conta → Administração do projeto**. Gere um convite para um e-mail de teste; confirme que a nova empresa começa sem os dados de `team`.

Não convide MEIs reais antes dessa conferência. A senha de proteção Basic, a senha da conta do app e a conta do WAHA são acessos distintos.

## Recuperar ou reativar uma conta

Ainda não há envio de e-mail para recuperação, Google login, MFA ou troca de e-mail. O botão de recuperação informa que o administrador precisa ser contatado. Para redefinir uma senha, use a mesma conexão SSH interativa acima, substituindo `create-admin` por `reset-password`. O terminal pede o e-mail e a nova senha, revogando todas as sessões. Não muda o papel nem reativa uma conta desativada.

Para reativar, use `enable-user`: o terminal pede o e-mail, mantém os dados e exige novo login. O painel permite desativar MEIs e impede desativar administradores globais. Não há exclusão definitiva da empresa pelo painel; a limpeza de dados locais não exclui registros do PostgreSQL.

## Incidentes e próximos limites

Se a ativação falhar antes do primeiro uso real, mantenha a proteção Basic e confira os arquivos privados, a migration e os logs redigidos. Depois de existirem contas reais, **não desligue a autenticação para voltar à gestão compartilhada**: isso reabre o workspace legado para quem possui acesso Basic. Em incidente, mantenha a autenticação exigida e suspenda a entrada no gateway até corrigir ou restaurar em ambiente isolado.

O backup da equipe inclui as tabelas de contas, negócios e sessões por ser um dump completo do PostgreSQL. Trate os dumps como privados; após restaurar em produção, revogue sessões conforme o incidente. Para abrir o produto ao público faltam decisão do dono, proteção de borda/capacidade, recuperação e verificação de e-mail, política de dados e expansão dos fluxos de administração. O piloto não liga o WhatsApp, não automatiza mensagens e não habilita cobrança.
