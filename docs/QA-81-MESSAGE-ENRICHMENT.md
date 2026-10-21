# Issue #81 — Caixa, sentimento e preparação RAG/n8n

## Base e escopo

Branch `feat/message-enrichment-81`, criada exatamente de `cb7fa6efcf7fc48b1b676af86d2929330c5c4995` (#79). Ancestralidade #75 → #77 → #79 conferida, sem cherry-picks ou alteração dessas branches. Main permanece independente. #80 é uma Issue aberta de preparação de release, não uma PR; seu plano não foi executado. #73 permanece investigação separada.

O laboratório está dentro da Caixa Unificada oficial. Reutiliza lista, conversa, temas e componentes; fica fechado até uma ação explícita. Mensagens e conhecimento são fictícios e persistidos somente no namespace autenticado isolado. Identidade é workspace/canal/conta/contato, nunca nome. O composer local não opera nessas conversas; salvar revisão apenas confirma um rascunho. O modo local e suas chaves anteriores não são migrados.

## Funcional e demonstrável

- Criar mensagens sintéticas, analisar individualmente, consultar sentimento/confiança heurística baixa e fontes do próprio negócio.
- Adicionar/remover texto fictício, consulta lexical limitada e invalidação das sugestões quando a fonte é removida/expira.
- Revisão humana com CAS: aprovar/descartar uma única vez; outra decisão requer nova análise. Sem envio.
- Duas sessões, conflito, falha offline e recarga explícita sem perda silenciosa do rascunho. Sem sincronização em tempo real.
- Viewer lê; member opera mensagens/revisões; owner/admin gerencia documentos. Backend decide identidade e papéis.
- Adaptador interno stub com assinatura, replay persistido, expiração, tentativa limitada, quota e rejeição de resultados fora de ordem. Nenhum cliente de rede, endpoint público de callback ou workflow instalado.

Contratos e limites: [MESSAGE-ENRICHMENT-CONTRACT.md](MESSAGE-ENRICHMENT-CONTRACT.md) e [MESSAGE-ENRICHMENT-ADAPTER.md](MESSAGE-ENRICHMENT-ADAPTER.md).

## Defeitos encontrados e corrigidos com regressões

- Mesmo ID de mensagem por canal/conta, alterando contato, escapava da deduplicação por conversa: chave externa persistida na fronteira correta; novos aliases de operação consomem quota, replay exato não.
- Ordenação de jobs por horário de início podia escolher resultado antigo: usar revisão da mensagem.
- Remoção de fonte podia preservar conteúdo em jobs históricos substituídos: invalidar também histórico/replays.
- Frases curtas de negação recebiam sentimento incorreto: regras conservadoras, conflito de sinais como indefinido, confiança sempre heurística baixa.
- Aba antiga após troca de login em outra aba: conferir escopo verificado do navegador e workspace certificado nas respostas; limpar dados sintéticos e formulários quando a identidade muda.
- Recarga explícita sem rede descartava o rascunho: só substituir após leitura nova confirmada no mesmo escopo. Resposta POST confirmada seguida de falha de leitura mantém a chave idempotente para nova tentativa.
- Renderização recursiva por eventos gerais da Caixa: usar evento específico de demonstração e proteção de atualização. Painel recolhe após criar mensagem, com área limitada no mobile.

## Verificação

Resultados finais, SHA, checks e evidências constam na PR Draft. Testes Node e PostgreSQL exercitam isolamento, replay, CAS, assinatura, 401/403/404/409/422/429/503, validação, expiração e exclusão. Navegador controlado cobre UI/roles/teclado/offline/troca de aba e 320/390/768/1440 claro/escuro. Prova adicional usa duas sessões independentes reais sobre HTTPS/FastAPI/PostgreSQL descartáveis e um segundo negócio; nenhuma fonte real ou socket externo é usado.

## Publicação e rollback — apenas plano

1. Revisar dependências #75/#77/#79 e esta PR; CI no HEAD final e homologação autorizada em staging realmente identificado. O staging atual continua não confirmado.
2. Obter autorização separada de ambiente, backup e migration 014. Aplicar incrementalmente pelo migrador existente, backend compatível antes do frontend; não editar migrations anteriores.
3. Manter `SOCIALMEI_MESSAGE_ENRICHMENT_MODE=disabled`. O modo stub exige chave de teste própria exclusivamente no servidor. Não usar chave do n8n ou qualquer credencial real.
4. Conferir isolamento/roles em dados fictícios. Não conectar webhooks ou canais. Em regressão, restaurar imagens anteriores; preservar as tabelas novas e seus dados, sem DROP automático nem restore destrutivo.

## Bloqueios reais e riscos

**P0 operacional:** nenhuma publicação/integração real está liberada. Identidade e topologia dos workflows Alana/REVIEW são não confirmadas; só há evidência histórica, sem nova consulta viva. Autorização, credenciais, canais, destinos e contratos de callback/envio precisam de etapa própria. Não foi alterada AWS/n8n/Meta, main ou banco real.

**P1 antes de produção:** extração segura de PDF, armazenamento privado/embeddings com isolamento, contrato autenticado de conector e webhook interno de rede, scheduler de retenção, revisão de capacidade/observabilidade e homologação com dados autorizados. Hoje a retenção é aplicada em leitura/processamento; não existe serviço agendado. RAG é lexical, e sentimento é heurístico experimental; não representa compreensão contextual homologada.

**P2:** homologação física de celular e leitor de tela, avaliação linguística ampliada, política operacional de retenção para mensagens/jobs/metadados e paginação além dos limites da consulta. Rascunhos não confirmados ficam apenas em memória na página aberta; fechar/recarregar pode descartá-los. A revisão desta PR não substitui autorização de merge ou deploy.
