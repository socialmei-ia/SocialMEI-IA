# Retomada do SocialMEI-IA sem Codex — 13/11/2026

## Objetivo

Preservar a produção e transformar a candidata validada em uma versão pronta para homologação real, sem repetir diagnósticos nem fazer o corte enquanto faltarem condições externas.

- **Base verificada:** `release/functional-completion-20261112`, commit `3ce82445a6c87dcc3df3dc43890baa72ac83b127`.
- **Continuação isolada:** `ops/readiness-sem-codex-20261113`.
- **Sem publicação:** esta branch não representa aprovação de deploy, configuração de AWS, troca de banco ou habilitação de canais.
- **Sem alterações no Prisma:** não alterar credenciais, DSN, schema, migrations ou executar restauração em produção.

## Decisões fixadas — fonte única desta retomada

| Decisão | Regra operacional |
| --- | --- |
| Base de referência | `3ce82445a6c87dcc3df3dc43890baa72ac83b127` — candidata funcional aprovada em ambiente isolado |
| Linha de trabalho | Apenas `ops/readiness-sem-codex-20261113`; não alterar `main`, PR #223 ou branches de canais |
| Prioridade até a volta do executor | Corrigir bugs verificáveis, melhorar testes e preparar evidências para homologação |
| Produção e dados reais | Congelados. Sem deploy, troca de DSN, alteração de Prisma, migrations, envio, mudança de credenciais ou reinícios |
| Canais automáticos | Permanecem opt-in; confirmar respondedor único antes de testes reais |
| Evidência | Diferenciar testes históricos (`3ce8244`), verificações desta branch e homologação em produção |
| Próximo marco | Validar os novos testes Node/navegador em ambiente isolado e conciliar o pacote completo; depois avaliar gates externos |

**Não registrar uma nova decisão contraditória em conversa ou script sem atualizar primeiro esta seção.** Os bloqueios externos permanecem na seção de pendências abaixo.

### Proteção adicional contra ativação acidental

- `tests/release-activation-guards.test.cjs` protege padrões desativados para WhatsApp, Instagram, e-mail e agenda pública; confirma perfis opcionais dos workers, compartilhamento do override de banco da aplicação e isolamento de credenciais no gateway público.
- O teste de navegador do botão **Tentar novamente** agora espera a resposta HTTP simulada, evitando afirmar sucesso antes da requisição.
- **25 verificações de conteúdo e sintaxe feitas nesta sessão, todas aprovadas**, incluindo uma mutação simulada que habilitaria o agendamento sem autorização e foi detectada. Isso não substitui a execução completa do arquivo Node.
- Ao retomar localmente: `node --test tests/release-activation-guards.test.cjs tests/public-booking-timeout.test.cjs`; depois `node tests/public-booking-browser.cjs` com Playwright em ambiente isolado. Nenhum desses testes exige banco Prisma real.

## Correções adicionais nesta branch — sem ativação

- A tela real de agendamento público tinha chamadas `fetch` sem prazo máximo. Agora cada solicitação, incluindo a leitura do JSON, é limitada a 20 segundos. Uma confirmação interrompida continua sendo tratada como **resultado incerto**, permitindo reenviar **a mesma** solicitação idempotente para consultar o comprovante, sem anunciar falha definitiva.
- A tela de indisponibilidade ganhou **Tentar novamente**, recuperando o carregamento sem exigir atualizar a página manualmente.
- Novos testes automatizados em `tests/public-booking-timeout.test.cjs` (5 cenários com rede simulada). O teste de navegador `tests/public-booking-browser.cjs` também foi ampliado para cobrir o botão de tentar novamente.
- Verificações efetuadas nesta sessão: sintaxe válida dos três arquivos JS; **5 cenários isolados da função de requisição aprovados** em simulação de rede e relógio. Isso **não equivale** à execução do arquivo de teste no Node nem à suíte real de navegador.
- Próximos testes obrigatórios, no ambiente de desenvolvimento isolado (não no servidor de produção):
  ```powershell
  node --test tests/public-booking-timeout.test.cjs
  node tests/public-booking-browser.cjs
  ```
  O segundo comando exige Playwright e navegador instalados. Não exige acesso a Prisma ou e-mail real.

## O que já foi implementado e testado

O commit `3ce8244` registra, em ambiente isolado e com PostgreSQL schema039 descartável:

| Área | Evidência existente | Significado |
| --- | --- | --- |
| Backend | 947 testes Python aprovados | Cobertura automatizada, não homologação real |
| Frontend | 426 testes JavaScript aprovados e dois skips anteriores | Cobertura local |
| Gateway | 14 testes Docker aprovados | Contrato de encaminhamento |
| Interface de agendamento público | 42 jornadas e 286 estados de layout | Navegador com API controlada |
| WhatsApp, Instagram, Agenda e CRM | Implementações integradas na candidata | Exigem testes com provedores e contas reais |
| Recuperação por e-mail | Worker opcional e fluxo implementado | SMTP privado e recebimento real não comprovados |

Detalhes e evidências: `docs/FINALIZACAO-SEM-PRISMA-20261112.md` e `docs/evidence/20261113-functional-completion.json`.

## Observações reais já conhecidas (não repetir sem necessidade)

- Em 13/11, a API de equipe `socialmei-team-team-api-1` estava `running`, mas `unhealthy`.
- `/health` respondia 200; `/health/db`, 503. O serviço usava conexão efetiva com `db.prisma.io`.
- A conexão direta e a com pool retornaram `planLimitReached`. **É bloqueio do provedor**, não uma falha comprovada de Docker, DNS ou TLS.
- O PostgreSQL local estava saudável, porém **não prova ter o conteúdo atualizado do banco Prisma**.
- AWS CLI 2.40.2 instalada no Windows e no Ubuntu; a função IAM do servidor autentica, mas não autoriza `ec2:DescribeInstances`. Não ampliar a função de produção sem projeto de permissões.
- A conta root usada temporariamente na CLI Windows foi deslogada. Não usar root para agentes.

## Diagnóstico consolidado, quando necessário

No Windows PowerShell 5.1, a partir do repositório atualizado:

```powershell
.\tools\socialmei-producao-somente-leitura.ps1 -Relatorio "$env:TEMP\socialmei-estado.txt"
```

O comando verifica uso de RAM/disco, containers, estados de saúde e identidade AWS do servidor **sem imprimir variáveis de ambiente, conexões, logs, tokens ou dados de clientes**. O relatório é opcional e salvo localmente. O script não testa o Prisma nem envia mensagens; não confundir `running` com operação funcional.

## Pendências que impedem ativação em produção

1. **Banco atual:** recuperar acesso ao Prisma ou obter exportação verificável e atual do schema039 antes de planejar corte. Nunca apontar a API para o PostgreSQL local por suposição.
2. **Backups:** validar cópia externa, permissões IAM mínimas, restauração isolada de dados atuais e plano reversível. A instância de produção não substitui backup off-site.
3. **Capacidade AWS:** verificar RAM e swap, espaço, imagens e redes Docker instaladas. Obter aprovação de capacidade e de custos.
4. **SMTP privado:** configurar credenciais fora do Git, testar TLS, entrega ao destinatário controlado e recuperação de conta; não ativar automaticamente worker de envio.
5. **WhatsApp real:** garantir respondedor único, entrada persistida, menu/catálogo, resposta humana, idempotência e agendamento visível na Agenda.
6. **Instagram real:** conferir conta e callback Meta, mensagens, contatos, pausa humana e agendamento; evitar respostas duplicadas ou troca de identidade.
7. **Agenda e página pública:** provar concorrência entre canais e site, bloqueio de horários, isolamento dos negócios, código de verificação e recuperação do recibo, usando contas de teste autorizadas.
8. **Corte:** validar imagens por SHA, overlays privados, proxy, rollback e aprovação explícita. Não usar `tools/gows-catalog-release.py` como publicador da candidata completa.

## Próxima execução com Codex ou outro executor

- Usar worktree **isolada** da candidata; preservar alterações locais e `main`.
- Conferir SHA da candidata e incorporar apenas alterações revisadas desta branch.
- Revisar o pacote completo de release, redes privadas e imagens antes de propor publicação.
- Testar com PostgreSQL descartável, sem segredos e sem envio real.
- Gerar relatório de aprovação e bloqueios, **não** executar corte ou migrations em produção sem autorização.
- Não criar PR automaticamente se ela disparar workflows que executem migrations, até confirmar o escopo das verificações.

**Regra de sucesso:** código pronto e testado não significa canal ativo, envio homologado, banco recuperado nem produto concluído em produção.
