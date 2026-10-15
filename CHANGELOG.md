# Changelog

## Correção do cadastro atrás de Basic — 2026-10-15

- Bootstrap consulta sessão opcional com200/null, evitando que401 anônimo invalide o acesso Basic do navegador.
- Erros normais de credenciais de login usam400; rotas protegidas preservam401, sessão, autorização e limites.
- Cadastro pode repetir a consulta de disponibilidade; e-mail incompleto é bloqueado e erros de envio recebem foco.
- Regressão com desafio Basic humano no Chromium, sem credenciais automáticas que ocultem a falha.

## Cadastro do piloto sem convite — 2026-10-15

- Cadastro temporariamente aberto por padrão no Compose team, com reversão por `TEAM_REGISTRATION_MODE=invite`.
- Formulário consulta a política da API e oculta o convite no modo aberto; login continua disponível se a consulta falhar.
- Preservados autenticação, Basic, validação de contato/senha, limites, convites existentes e criação de negócios separados sem privilégio administrativo.
- Sem migration, alteração de dados existentes ou integração externa. Publicação no servidor é uma etapa separada.

## Preparação da base — 2026-10-14

- Limpeza do PR #42 incorporada à branch de preparação, preservando os commits revisados.
- Leitura de ambiente da API centralizada em `settings.py`, com compatibilidade dos helpers, auth inválida bloqueada e workspace da sessão preservado.
- `db:status` local tornou-se consulta sem criar schema/tabela; `db:migrate` continua inicializando e aplicando pendências explicitamente.
- Dez testes de configuração e quatro do executor local; teste HTTPS aceita Chromium já instalado e informa status HTTP em falha de inicialização.
- Mapa de ambientes, estrutura/estado por módulo e relatório de preparação; roadmap remove afirmações superadas. Backups locais e resíduos de patch ignorados pelo Git.
- Sem redesign, nova feature, migration, alteração de grafo n8n ou publicação na AWS.

## Manutenção do código — 2026-10-14

- Seleção de período extraída do listener principal; hora comercial compartilhada entre Home e header.
- Revisão de venda consolidada sem redefinir a função; estados financeiros mais legíveis.
- Mensagem inicial local da Inbox compartilhada; composição do texto do Assistente separada do histórico.
- Quatro declarações CSS idênticas removidas, mantendo as posteriores na cascata; comentários de seções e confirmação de contato legíveis.
- Consultas de saúde agrupadas por capacidade, preservando SQL, transação e tratamento de falhas.
- Três testes de período e relatório de manutenção; orientações de desenvolvimento/deploy atualizadas. Sem alterações de schema, workflows ou runtime.

## Aplicação da base team — 2026-10-13

- PR #35 integrado em `ae73f6e093fc2d271a69a2ba9de1ebffc66c0705`; CI do merge aprovado, separado das evidências AWS.
- Responsável confirmou backup privado de dados/configuração/roles e imagens anteriores API/gateway preservadas para rollback.
- Migration 011 aplicada no PostgreSQL team 16.15; versões 001–011 e sete constraints validadas.
- Somente gateway recriado; 37 arquivos do frontend comparados por SHA256, configuração privada preservada e Basic continuou respondendo 401. Demais containers preservados sem reinício.
- Responsável confirmou login, abertura de Clientes/Produtos/Vendas/Financeiro/Relatórios, saída e reentrada após Ctrl+F5. Perfil de consulta não aplicado; role da API observada como superuser, a revisar em etapa própria. n8n/WAHA não alterados; nenhum restore, redesign ou calculadora executado.

## Estabilização da base — 2026-10-13

- Corrigido fechamento tardio de formulários remotos: a resposta de uma operação anterior preserva uma nova edição/criação já aberta, mantendo feedback do salvamento.
- Regressão de Vendas com atraso controlado e quatro testes de ownership dos formulários.
- Preparada migration aditiva 011 para vínculos de CRM/importações do mesmo workspace; testes de upgrade, rollback, histórico e SQL cruzado. Migrations 001–010 preservadas.
- Preparado perfil de consulta interno sem login, acesso a auth ou concessão automática a novas tabelas; nenhum acesso da AWS provisionado.
- Acrescentada matriz de nove resoluções e cinco modos de tema ao CI.
- Classificados os nomes dos sete exports n8n inativos, preservando grafos/parâmetros; nenhuma alteração na instância viva.
- README, contratos, acesso ao banco e relatório da base atualizados com distinção entre código, CI e runtime. Sem redesign, calculadora ou deploy nesta rodada.

## Polimento visual do GitHub e superfícies públicas — 2026-10-10

- README ganhou apresentação visual, navegação curta e visão rápida do produto.
- Banner SVG foi redesenhado para refletir a identidade atual do SocialMEI: azul, amarelo e interface do produto, removendo referências antigas de Sprint/cyber visual.
- Metadados Open Graph/Twitter passaram a apontar para o banner visual atualizado.
- Landing removeu prova social e preços fictícios/pendentes; a seção comercial foi substituída por uma apresentação honesta da demonstração.
- Rodapé público deixou de exibir contatos, links legais e redes sociais inexistentes; agora mostra apenas destinos reais do projeto e o estado atual da demonstração.
- Mike DevHub preservou o conceito de cockpit, mas recebeu menos glow, menos ruído, paleta mais próxima do SocialMEI e nomenclatura mais direta em português.
- Nenhuma lógica de backend, n8n, WAHA, banco, CRUD ou contratos de armazenamento foi alterada nesta rodada.

## Revisão técnica — 2026-10-10

- Adotado o `socialmei-app.html` aprovado como fonte oficial; V3.14 duplicada substituída por entradas de compatibilidade.
- Separados scripts e CSS do frontend e do Mike DevHub, sem framework/build obrigatório.
- Extraídos ícone/fonte sem alterar seus bytes; preservada a licença Inter no HTML.
- Centralizada configuração pública em `frontend/config.js`; corrigidos canonical e imagens de compartilhamento para o endereço adotado pelo repositório.
- Consolidada a definição dos seis serviços Compose; corrigida indentação WAHA, removidas opções que desativavam autenticação e mantido bind localhost.
- Preservados schema, nomes de volumes, rotas e contratos JSON/localStorage; nomes internos Python e normalização n8n em inglês.
- Workflows de teste/experimento organizados; exports inativos sem credenciais de instância, dados fixados ou Authorization literal.
- Backup usa diretório configurável/volume real, inclui configuração do override e relata falha de restart.
- Atualizados guias, inventário, roadmap e CI; acrescentados testes de dados/temas/contratos/backup e regressão de navegador.
- Ajustado o comando de testes para compatibilidade com o Node 22 do CI após a primeira execução remota.

O histórico anterior permanece nos commits Git. Esta revisão não aplica alterações na VPS nem ativa workflows.
