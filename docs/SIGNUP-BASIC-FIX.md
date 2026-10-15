# Cadastro bloqueado pela consulta inicial de sessão

Diagnóstico de 15/10/2026. Baseline `db775dc`, branch `fix/signup-basic-session`. Correção independente do PR #48 de V2 Foundation.

## Evidências e causa

O responsável confirmou na AWS a política `/auth/registration` com HTTP200/mode=open e nenhuma tentativa de POST de cadastro no recorte de logs. O navegador mostrou401 em `/auth/me`, `/auth/registration` e estilos. O formulário exibiu “Não foi possível consultar o cadastro” e manteve Continuar desabilitado. Não era um pedido de convite nem uma execução Python.

Foi reproduzido no Chromium com um único acesso humano à proteção Basic: depois de uma resposta401 da aplicação, o navegador invalida as credenciais HTTP em cache. A consulta seguinte recebe um novo desafio Basic e não libera o cadastro. O controle idêntico com resposta200 não perde o acesso. Os testes antigos com `httpCredentials` do Playwright respondiam automaticamente a novos desafios e não detectavam esse ciclo.

## Correção

- Novo `GET /api/v1/auth/session`:200/null sem sessão válida;200/identidade com cookie válido. Nunca cria conta, sessão ou negócio; permanece atrás do Basic e exige configuração de auth válida. GET apenas, no-store, sem CORS aberto.
- Bootstrap usa essa consulta. `/auth/me` e os módulos protegidos continuam respondendo401 a acesso anônimo.
- Erros de credenciais no formulário de login usam400 com a mesma mensagem genérica para usuário inexistente, senha errada ou conta desativada. Não concedem sessão/permissão e mantêm hash/rate limit. Evita invalidar o Basic em um erro normal de digitação.401 continua representando sessão exigida nas rotas protegidas e proteção Basic na borda.
- Falha na consulta da política mostra um botão de tentar novamente; nenhum cadastro é enviado sem política válida. Não transforma indisponibilidade em cadastro aberto.
- O formulário exige e-mail com domínio completo, compatível com a regra do servidor. Não marca um endereço incompleto como “Tudo certo”. Erro de envio recebe foco para ficar visível também no desktop.

Não foram alterados convites, isolamento por negócio, schemas/migrations, configurações privadas, workflows, n8n, WAHA ou o design aprovado.

## Testes e limites

`tests/signup-basic-browser.cjs` usa desafios HTTP reais do Chromium e fornece credenciais fictícias somente no primeiro desafio, sem `httpCredentials` que mascararia o defeito. Verifica desktop/mobile, login recusado sem perder o Basic, cadastro completo e um controle401 que reproduz a invalidação. Não acessa AWS ou integrações externas.

Suites de contas verificam consulta anônima sem banco, cookie válido/revogado, auth desativada, no-store, recusa de outros métodos, isolamento e limite de tentativas. Browser cobre e-mail incompleto, foco no erro e recuperação após falha da política. Gateway continua recusando a nova rota sem Basic. Resultados de testes/CI pertencem ao SHA do PR; não comprovam publicação.

## Publicação

Preparar backup/rollback e imagens específicas após revisão/CI. Atualizar **API primeiro**, conferindo `/auth/session`200/null sem sessão e `/auth/me`401. Depois publicar gateway/frontend que usa a nova consulta. Preservar os arquivos privados e o usuário compartilhado; não recriar banco/migrador ou reiniciar integrações. Não executar workflow genérico de deploy.

Confirmar no navegador sem sessão anterior: um único acesso Basic → cadastro disponível → telefone confirmado → conta criada → sair/entrar. Testar e-mail incompleto e login incorreto sem bloquear o acesso. Nenhum dado real foi usado nos testes locais e nenhum deploy foi realizado durante o diagnóstico.
