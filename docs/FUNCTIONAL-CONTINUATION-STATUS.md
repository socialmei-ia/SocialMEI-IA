# Continuação funcional — 27/10/2026

## Atualização em28/10/2026

Base consolidada atual: PR136, `feat/frontend-v25-integration`, HEAD849ead4.
O proprietário confirmou OAuth conectado após a correção93163f9; Direct e post
reais ainda não foram comprovados e suas flags permaneciam desligadas no último
procedimento conhecido. Não tratar os bloqueios históricos abaixo como nova
inspeção da AWS. A imagem efetiva precisa de confirmação antes de novo corte.

Preparação adicional nesta branch: bot WhatsApp com menu, consulta do catálogo,
estado por conversa, handoff, claim único e recibos (migration032), registryWAHA
privado e subworkflown8n inativo. Sem deploy ou envio real. O número de teste agora
está disponível segundo o proprietário; pareamento/engine/workflow ainda precisam
ser conferidos. [Contratos e operação](WHATSAPP-BOT-OPERATIONS.md).

Os dados e as proteções existentes permanecem; migration032 não foi aplicada na
AWS. SMTP/worker, IA generativa com fontes e homologação dos serviços externos
continuam pendentes. A documentação abaixo registra a etapa anterior.

## Fonte e entregas

Base confirmada: PR131 `8d0318bcf4262afde9798b8ad91ce4924cf046b9`. Não reimplementar115–130: a árvore já continha cadastro real, PDFs029, catálogoWhatsApp030, leitura restrita031 e as correções OAuth. O core Instagram da candidata é equivalente ao da130; HEADs de branches não ancestrais não devem ser mesclados cegamente (alguns patches já estão incorporados).

| Unidade            | PR                                                           | Implementação desta continuação                                                                                                                                      |
| ------------------ | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Operação e preview | [131](https://github.com/socialmei-ia/SocialMEI-IA/pull/131) | Preparador com nomes exatos001–031, estágios OAuth/foto/funcional e migrations adiadas; resize sincronizado sem enfraquecer overflow; teste canário de overflow real |
| WhatsApp           | [132](https://github.com/socialmei-ia/SocialMEI-IA/pull/132) | Gestão nativa de credencial por canal, estado real cadastrado, rotação/revogação e auditoria, sem conectar telefone/enviar                                           |
| PDFs               | [133](https://github.com/socialmei-ia/SocialMEI-IA/pull/133) | Parser isolado sem segredos, limites de CPU/memória/tempo; download privado, substituição/conflito, reprocessamento e exclusão de índice                             |
| Relatórios/equipe  | [134](https://github.com/socialmei-ia/SocialMEI-IA/pull/134) | Excluir futuro do período, snapshot consistente e teste completo de concessão/troca/revogação de report_viewer com conta própria preservada                          |
| Direct humano      | [135](https://github.com/socialmei-ia/SocialMEI-IA/pull/135) | Composer nativo para rascunho/revisão/confirmação/recibo; sender dashboard explícito e bloqueado por padrão; nenhum retry automático de resultado incerto            |

As PRs132–135 são propostas independentes baseadas na131, **não merges executados nela ou na main**. O checkout descartável de compatibilidade aplica os mesmos patches sem publicar uma segunda candidata ou fechar as PRs. Não confundir o SHA da131 com a combinação dessas propostas.

## Evidência local

- Baseline131:461 testes backend com PostgreSQL16 exclusivamente descartável,337Node,286 estadosV22 e30 transições de resize com canário de overflow. Reprodução inicial:10/45 medições antecipadas antes de fit/resize, sem suprimir a asserção.
- Preparador:27 testes focados incluindo Caddy real;116 operacionais (14 opt-in não executados na chamada geral). API/gateway e arquivos originais da fixture não mudam na preparação.
- Ensaio001–031:794 verificações; hashes/migrations imutáveis, registros/constraints preservados, pg_dump/pg_restore e rollback transacional, limpeza confirmada dos recursos exclusivos.
  -132:463 backend;133:467;134:463;135:462. Cada unidade executou337Node, formatação e testes relevantes de navegador. API/provedor do navegador e SMTP são controlados; o PostgreSQL é real e descartável.
- CI de cada HEAD deve ser consultado nos checks da respectiva PR. CI verde comprova os cenários automatizados, não Meta/SMTP/WAHA reais.

## O que já existia e foi preservado

Cadastro transacional cria usuário, credencialArgon2, workspace, papelowner e sessão. As suítes exercitam senha7/8, login/logout, perfil entre logins, sessão segura/CSRF, isolamento dos módulos e recuperação single-use/fila/revogação. Não foi criado outro banco nem sistema de identidade. PDFs e relatórios não usam dados demonstrativos na consulta remota.

## Bloqueios operacionais atuais

**Não há SSH, credencialMeta/SMTP/n8n ou acessoTCP à VPS neste ambiente. Nenhuma imagem, migration, configuração, workflow, conta ou mensagem de produção foi alterada.** O inventário anterior informado pelo operador não é nova inspeção do servidor.

Para o corte: executar inspeção somente leitura naVPS, identificar imagens/SHAs/overlays reais, verificar configuraçãoSMTP/worker por estado, ledger, rede e privacidade dos proxies. Fazer backup atualizado e restauração descartável antes de qualquer SQL. O preparador apenas cria artefatos privados, não executa essas etapas.

Depois: OAuth do @testefacep pelo site; confirmar conta e credencial cifrada sem expor valores; uma foto de teste escolhida pelo responsável; definir entrega de webhook e remetente único com n8n; provar Direct recebido/persistido/exibido e resposta humana recebida. WhatsApp depende de número/sessão e workflow autorizado. SMTP depende de conta remetente privada e worker funcionando; aceitaçãoSMTP não é entrega comprovada.

Reels/Stories/vídeo/carrossel não foram adicionados nesta continuação: continuam **não implementados/homologados**, após o primeiro ciclo real de foto+Direct. PDFs digitalizados precisam deOCR; busca por fontes está implementada, sem LLM conectado, treinamento de pesos ou embeddings externos.

Procedimentos: [operação faseada](SOCIALMEI-FASES-INTEGRACAO-REAL.md), [respostas humanas](https://github.com/socialmei-ia/SocialMEI-IA/blob/feat/instagram-native-direct-replies/docs/INSTAGRAM-HUMAN-REPLIES.md) na135, [PDFs privados](https://github.com/socialmei-ia/SocialMEI-IA/blob/fix/knowledge-functional/docs/PRIVATE-PDF-KNOWLEDGE.md) na133, [WhatsApp](WHATSAPP-CATALOG-OPERATIONS.md) na132 e [relatórios](https://github.com/socialmei-ia/SocialMEI-IA/blob/fix/account-team-functional/docs/REPORTING-ACCEPTANCE.md) na134. Documentos das propostas só existem na branch correspondente até aprovação; não presumir que estão na131.
