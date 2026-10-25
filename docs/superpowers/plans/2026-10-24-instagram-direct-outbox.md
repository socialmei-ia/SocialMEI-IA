# Instagram Direct Outbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persistir respostas Direct aprovadas com execução isolada, confirmação validada e recuperação conservadora após resultados desconhecidos.

**Architecture:** A identidade vem das mensagens e conexões das migrations019/020. A outbox Direct é um domínio distinto da fila de publicações de mídia015 e reutiliza o adaptador104 e o vault105. Claim/tentativa são comprometidos antes do transporte; ambiguidades ficam em `uncertain` sem repetição automática.

**Tech Stack:** FastAPI, PostgreSQL16, psycopg, transporte injetado e testes unittest.

**Spec:** Escopo C do pedido de continuação funcional; fronteiras de identidade e criptografia em `docs/INSTAGRAM-PERSISTENT-OAUTH.md` e `docs/INSTAGRAM-DURABLE-WEBHOOK.md`. Esta unidade C1 cobre respostas Direct; publicação de mídia permanece separada, pois depende de armazenamento de mídia e outro protocolo.

## Global Constraints

- Não modificar HTML/CSS, layouts, animações ou identidade visual.
- Não fazer merge ou deploy; não acessar produção, contas Meta, AWS, n8n ou WAHA reais.
- PostgreSQL de testes descartável; nenhuma chamada externa por padrão.
- Workspace BIGINT derivado da sessão autenticada; destino derivado da mensagem recebida, sem seletor de negócio ou destinatário fornecido pelo cliente.
- Tokens somente pelo vault existente, AAD vinculada à conexão/negócio/conta; nenhum token em logs/HTTP/novas tabelas.
- Texto UTF-8 até1000 bytes, janela conservadora de24h, sem exceção HUMAN_AGENT.
- Operação local idempotente não equivale a idempotência da Meta. Timeout, resposta inválida e lease vencida após claim não permitem retry automático.
- Revisão de payload invalida aprovação. Sessão/role/conexão/escopos/prazo são revalidados antes do claim.
- Exclusão/revogação de sessão ou membership não pode ser impedida por FKs históricas da outbox.

## Review Focus

- Cancelamento/reconexão durante HTTP não pode ser anunciado como cancelamento do efeito externo.
- Crash após aceitação e antes do commit deve preservar `uncertain`, sem novo envio.
- Remoção de membro/sessão deve funcionar e impedir novos claims, preservando histórico.
- Mensagens antigas/futuras não podem estender artificialmente a janela de resposta.
- Confirmação incorreta, credencial ilegível e resposta com segredos devem falhar sem fallback ou vazamento.

### Task1: Contrato do adaptador

**Files:** `python-service/instagram_meta_adapter.py`, `python-service/test_instagram_direct_outbox.py`.

**Interfaces:** `InstagramAdapter.send_direct` consome `TokenGrant` e destino/texto validados; produz confirmação de recipient/MID ou `ProviderError` sanitizado.

- [ ] Escrever testes de corpo UTF-8, destino, resposta estrita e transporte privado; observar RED.
- [ ] Acrescentar o método ao adaptador existente, sem cliente HTTP padrão.
- [ ] Executar testes de contrato e regressão dos métodos OAuth; observar GREEN.

### Task2: Outbox e autorização persistentes

**Files:** migration021, `python-service/instagram_direct_outbox.py`, seu teste, `app.py`, `settings.py`.

**Interfaces:** `InstagramDirectService.mutate(user,session,action,payload,job_id=None)`, `read(user,session)` e `run(user,session,job_id)`; dependência `outbox_service` fechada por padrão.

- [ ] Testar operações/revisões, aprovação, isolamento e revogação antes da implementação.
- [ ] Criar `ig_direct_jobs/operations/attempts/events`, FKs compostas e constraints que não aceitem aprovação nula por semântica SQL NULL.
- [ ] Implementar draft/edição/aprovação/cancelamento e histórico, preservando Origin/CSRF e decisões de sessão atuais.
- [ ] Comprometer claim/tentativa antes de HTTP; validar recibo antes de confirmar.
- [ ] Testar concorrência, janela, conexão, escopos, rotação, falhas/leases e ausência de retry após ambiguidade.

### Task3: Recuperação e revisão

**Files:** `tests/release-candidate-db.py`, `.github/workflows/repository-checks.yml`, `docs/IG-DIRECT-OUTBOX.md`.

**Interfaces:** Fixtures SQL021 entram no ensaio descartável existente; CI da nova PR aponta para a branch107.

- [ ] Incluir fixtures das quatro tabelas e provas de FKs/valores históricos no dump/restore/replay.
- [ ] Executar backend, Node, formatação, migrations/backup/restore, preview e navegador; separar skips de passes.
- [ ] Fazer revisão fresca, corrigir achados importantes com testes e abrir PR Draft independente sobre107.
- [ ] Registrar SHA e CI finais, gates externos e limitações de confirmação/idempotência; não ativar tráfego real.
