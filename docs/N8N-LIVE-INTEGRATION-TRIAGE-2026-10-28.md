# Corte funcional SocialMEI.IA — inventário n8n vivo de 28–29/10/2026

## Proveniência e limites

Relatório sanitizado produzido pelo operador diretamente na AWS com `tools/n8n-live-catalog.py --target team`; dados da API n8n: **56 workflows, 10 ativos e 46 inativos**. 26 foram atualizados desde 20/10, 30 são mais antigos. O relatório só comprova metadados, estrutura de tipos de nós e diferenças salvo/publicado. **Não** prova que webhooks chegam, que credenciais funcionam, que uma mensagem foi enviada, que o site recebeu dados, nem que fluxos com nome "RAG" realmente fazem RAG. Nenhuma mutação ou execução foi realizada nessa coleta.

### Achados P0 (dados atuais da AWS)

- **Instagram Direct** (`LHlqroY2xzvpYAmD`): ativo, 17 nós salvos e 9 publicados. Manter o fluxo publicado, não publicar o rascunho duplicado, resolver 403 e corrigir o Bearer estático.
- **Cópia segura** (`gu1meyWuQMJcVB8i`): inativa, 8 nós salvos, sem versão publicada; envio bloqueado e credencial ainda pendente.
- **WhatsApp WAHA/Groq/CPF** (`NFcJfjvpaUsjh1x1`): ativo, 42 nós informados no inventário inicial e 21 publicados; comparar a versão publicada antes de prometer CPF/CNPJ, sentimento ou menu.
- **Publicação Instagram** (`A0EcNxcRvfWnMwKI`): ativa, 40 nós salvos/publicados; possui Form Trigger e exige contrato autenticado do site antes de qualquer integração multi-MEI.
- **Caixa PostgreSQL** (`BtvlHv4mt90tn70z`): ativa, 8 nós salvos/publicados; verificar webhooks e evitar mistura com a Caixa multitenant.
- **Caixa local** (`WWzhvmdPh9LrpuYy`): ativa, 6 nós salvos/publicados; evitar envio/ingresso concorrente e não promover o legado diretamente.
- **Atendimento** (`DDrphANXE8QdxoWy`): ativo, 7 nós salvos/publicados; preservar referências às ferramentas de consulta, registro e confirmação de pedidos.

### Candidatos novos, ainda não publicados

- `uNfLQ5ZJsLX9iu12`: WhatsApp WAHA + Groq + CPF/CNPJ + análise de sentimento RAG, 30 nós, inativo.
- `I0LzS0yk4MTV8NPr` e `1Ie5tDyLavZwpcPs`: duas versões de Instagram + sentimentos/RAG, 16 nós salvos cada, ambas inativas. Inspecionar origem/contratos antes de escolher uma; não ativar clones.
- `TuvBHyIAK0k8VBlX`: Análise de Sentimento/rag, 11 nós, inativo. A existência do título não comprova armazenamento vetorial ou resultado confiável.
- `dPWzzYxwzPjhPiZj`: Agendamento de Relatórios PDF, 6 nós, inativo; `IGHA2FsgfC6zJOjS` e `JfetfC597C6NBTyU`: PDFs experimentais, 6 e 5 nós.
- `rVFOLd96gRwhKUJR`: Menu interativo teste, 14 nós, inativo; `M9BN1KgXN0cqxmXi`: CPF/CNPJ por Python, 6 nós, inativo.
- Há outras cópias Instagram e alguns exports inativos com marca de Bearer fixo: revisar e rotacionar credenciais comprometidas; não repetir valores em auditorias.

**Correção na ferramenta:** o relatório da primeira versão marcou algumas rotinas "Instagram — Análise de Sentimento + Resposta IA" como `instagram_publicacao` por encontrar "post" dentro da palavra "resposta". Corrigido em testes da PR #141. A classificação original desse grupo é incorreta; são candidatas a Direct/atendimento, não publicação.

## Mapear para o SocialMEI já implementado (branch candidata #140 → #137 → #136)

### 1. Instagram Direct + sentimento na Caixa (P0)

**Partes existentes:** Instagram OAuth/vault, `python-service/instagram_meta_ingress.py` e migrações 019–021, serviço de inbox e `frontend/scripts/v22-instagram-direct.js`. Caixa consome dados do backend por sessão/workspace. Serviço de enriquecimento atual `message_enrichment.py` é heurístico/sintético e **não** recebe automaticamente análise Groq/Gemini de origem real.

**Gargalos:** Meta precisa entregar evento autêntico com bytes e HMAC preservados à API do team (por um fan-out seguro ou cutover aprovado); o n8n atual pode responder com IA, e a API possui outro caminho de envio. Escolher **um só remetente**, garantir armazenamento idempotente e não misturar workspace. O token usado no workflow anterior não deve voltar a ser codificado nos nós. Erro 403 anterior ainda exige inspeção de permissões e resposta Meta sanitizada.

**Aceite mínimo:** uma mensagem de conta externa autorizada → evento válido gravado uma vez em workspace correto → aparece na Caixa no site → metadado/resultado de sentimento rastreável e ligado a mensagem → resposta humana ou automática autorizada uma vez, recibo Meta verificado; reconciliação se resultado incerto. Não alegar que RAG faz parte do MVP até provar fontes/documentos e isolamento.

### 2. WhatsApp + consulta catálogo pelo número de teste (P0)

**Partes existentes:** ingresso assinado WAHA (`waha_ingress.py`), catálogo do banco, bot persistente/menu/claim/receipt (`whatsapp_bot.py`, migration 032, PR #137) e workflow preparado `n8n-workflows/experimental/whatsapp-bot-planner.json`, inativo.

**Gargalos:** inspeção anterior AWS indicou WAHA container WEBJS presente, nenhum canal vinculado/provisionado no banco, registry privado ausente e migration 032 não aplicada. Publicação da PR #137 exige ensaio de migration 032 e imagens/overlays de runtime próprios, sem usar publicador antigo travado em 001–031. O workflow vivo `NFc...` é o candidato de comparação; não substituir silenciosamente o bot preparado nem usar dois emissores.

**Aceite mínimo:** número de teste pareado e vinculado exclusivamente ao negócio; mensagem HMAC validada/persistida → menu numerado consultando produtos e estoque reais do workspace → uma resposta WAHA `sendText` com recibo → handoff humano; teste com dois negócios e erro/reenvio. Botões/listas não fazem parte do primeiro corte WEBJS.

### 3. Publicação do Instagram (P1 após Direct+WA)

**Partes existentes:** publicação de imagem única preparada no backend e Divulgação V25, workflow 40 nós com Form Trigger para Feed/Stories/Reels/agenda. **Não** unir esses dois caminhos com POST direto no formulário; revisar modelo de credencial e permissão da conta Instagram Login vs Graph Facebook.

**Aceite mínimo até 30/10 (se homologável):** foto única em conta autorizada, recibo real consultável no site. Reels, Stories, carrossel e agendamento devem ter critérios e testes próprios; não rotular suporte fictício como concluído.

### 4. Outros recursos (P2)

Relatórios PDF, validação CPF/CNPJ, orçamentos, RAG e lembretes: inventariados como candidatos; não ativar sem confirmar entradas, fonte/tenant, privacidade, retorno à UI e testes. Primeiro aproveite relatórios e backend existentes; Sheets legadas continuam fora do corte.

## Sequência de execução até 30/10

1. **Sem mutação:** conferir os grafos publicados do Direct (9) e WhatsApp (21), os dois ingressos de Caixa (8/6), e os workflows candidatos inativos de sentimento; identificar webhook de entrada, destino do HTTP, credencial por _tipo_, método e fluxo de saída, sem extrair valores.
2. **Preparar branch candidata e CI:** respeitar ancestralidade PR #136 → #137 → #140 e mudanças da PR #141. Codificar ponte de mensagens/resultado de IA somente após definir contrato, com testes de idempotência, isolamento, assinatura, janelas/erros.
3. **Pré-corte AWS:** conferir saúde, versão de imagem, migrações e flags reais; backup restaurável e rollback; validar credencial Meta por rota privada e pareamento WAHA, nunca imprimir token.
4. **Piloto Instagram:** mensagem externa real autorizada entra na Caixa; escolher único remetente; testar uma resposta, recibo e erro; desativar caminhos concorrentes antes de ligar outro.
5. **Piloto WhatsApp:** instalar migration 032 somente após ensaio, provisionar canal/registry, webhook assinado, bot com menus de texto/consulta; testar com dois negócios.
6. **Site público de testes:** confirmar login, acesso aos dados, Caixa, respostas, Divulgação, mensagens de erro honestas, renovação de token/recibo e monitoramento sem PII em logs.
7. **Extras condicionais:** publicar imagem simples; classificador de sentimento real; PDFs, orçamentos, Reels/Stories conforme capacidades e tempo. Não declarar pronto se dependências externas ainda estiverem pendentes.

## Não fazer

- Não publicar o rascunho duplicado de 17 nós sobre a versão Direct publicada de 9.
- Não publicar o rascunho WhatsApp de 42 nós sobre 21 sem revisão.
- Não deixar dois serviços enviarem respostas à mesma mensagem.
- Não expor endpoints `/internal/*`, dados reais, tokens ou exports privados no Git/browser.
- Não implementar integração multiempresa com IDs fixos dos workflows legados.
- Não executar ações na AWS, mexer em flags, credenciais, migrations, webhooks, WAHA ou Meta com base somente neste inventário.

**Situação após esta PR:** inventário e plano rastreáveis no Git. Integração real, testes de ponta a ponta e publicação na AWS continuam pendentes.
