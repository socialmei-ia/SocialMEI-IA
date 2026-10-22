# Auditoria — publicação Instagram (export recebido)

**Data:** 19/10/2026 · **Método:** leitura estática do arquivo recebido pelo responsável, sem executar nós, consultar tokens, alterar n8n, publicar no Instagram ou fazer deploy.

## Evidência e proveniência

- Export `Publicar post no Instagram` com **40 nós** e `active: true` no arquivo; isso **não comprova** a ativação atual no servidor.
- O export declara um **ID de workflow diferente** do `A0EcNxcRvfWnMwKI` historicamente inventariado no n8n da AWS (este inventário o mostrava inativo). Não tratar dois fluxos com mesmo nome como a mesma versão.
- A navegação de retorno do formulário aponta para **`facepe2027.app.n8n.cloud`**, enquanto o SocialMEI usa outra instância em AWS. Confirmar com o responsável onde o fluxo roda e quem controla a conta antes de abrir qualquer piloto.
- Há referências a credenciais de Meta e ImgBB no export, **sem os valores secretos**. Os identificadores, preset e conta de terceiros não foram incorporados ao código público.

## Contrato observado no formulário (não é API)

**Campos de entrada observados:**

- `tipo_publicacao`: `Post no Feed`, `Reels` ou `Story`.
- `quando_publicar`: `Agora (usar hora atual)` ou `Agendar`.
- `media`: JPG, JPEG, PNG, MP4 ou MOV. Um arquivo para Reels/Story, múltiplos no Feed.
- `modo_varias`: `Carrossel (um único post)` ou `Posts separados (um por foto)`, apenas no Feed.
- `legenda`: texto livre. A rota de Story não transmite legenda para a Meta.
- `data_agendamento` e `hora_agendamento`: data/hora, interpretada em `America/Sao_Paulo`.

O n8n recebe arquivo binário no **Form Trigger**, não em webhook autenticado de API do SocialMEI. O resultado é exibido pela etapa de conclusão do próprio formulário (`status`, `mensagem` e eventual `instagram_media_id`); não há contrato HTTP com `publication_id` consultável pelo app.

Fluxo declarado: formulário em duas etapas → normalização → divisão dos arquivos → hospedagem pública ImgBB/Cloudinary → consolidação → Wait por horário → switch Feed/Reels/Story → criação e publicação dos containers na Graph API da Meta → confirmação ou erro.

## Achados e prioridade

**P0 — Bloqueadores de segurança e publicação**

- **Conta fixa na Meta:** o destino `/media` e `/media_publish` usa um mesmo ID de conta. Não há seleção autorizada por MEI. Resolver no backend, nunca com ID arbitrário recebido do navegador.
- **Sem autorização por negócio:** o Form Trigger não demonstra autenticação por usuário ou workspace; eventuais controles externos precisam ser conferidos.
- **Sem idempotência:** não há registro persistido consultável, callbacks autenticados ou reconciliação após timeout. Reenvios podem duplicar posts.

**P1 — Consistência funcional**

- **Vídeo de Feed:** o formulário aceita vídeo único, mas o nó `Feed - Criar container` envia sempre `image_url`. Corrigir/validar antes de homologar.
- **Reels:** o campo aceita imagens mesmo que a rota da Meta exija `video_url`. Restringir mídia conforme a modalidade.
- **Agendamento:** `Math.min` limita hora inválida silenciosamente e não rejeita explicitamente datas passadas. Validar horário de Brasília e janela permitida.
- **Estado do agendamento:** o Wait ocorre dentro do formulário, sem consulta assíncrona pelo app. Mostrar estado real do backend, não prometer postagem concluída.
- **Hospedagem externa:** revisar privacidade, URLs públicas, retenção, tratamento de mídias e credenciais próprias da instância. Segredos nunca no frontend.

**P2 — Usabilidade e limites**

- **Link de retorno:** endereço absoluto n8n.cloud, que ficaria incorreto se o fluxo fosse importado para AWS.
- **Carrossel e vídeo:** carrossel limitado a 10 fotos; Reels espera e consulta o processamento da Meta. Preservar validações, expiração e timeout.

## Encaminhamento no SocialMEI.IA

1. **Agora:** manter Divulgação, prévia, cópia de legenda e rascunhos; o piloto de **handoff externo** não transfere mídia/texto, não publica e começa `disabled`, com o painel oculto na interface pública.
2. **Antes de qualquer teste real:** verificar instância, titular da conta Meta, credenciais, permissões e fluxo efetivamente publicado; usar conta de testes isolada. A configuração externa exige `mode: "external-pilot"`, `formUrl` e `approvedOrigin` idêntica à origem. **Não configurar URL de terceiro sem consentimento.**
3. **Integração nativa:** app autenticado → API FastAPI autenticada por sessão/workspace → armazenamento privado temporário de mídia e registro persistido idempotente → execução interna n8n por credencial de serviço → status consultável e confirmação Meta por conta autorizada.
4. Criar testes com imagens e vídeos sintéticos, carrossel (2 e 10 arquivos), duas contas isoladas, agendamento futuro/passado, duplicidade, erro Meta, vídeo aguardando processamento, revogação de permissão e timeout com resultado incerto.

**Não realizado:** ativar workflow, abrir link de publicação com credenciais, editar VPS, publicar no Instagram, conectar conta Meta, criar endpoint de publicação real, mesclar PR ou fazer deploy.

## Segurança do material recebido

O JSON original permanece somente como anexo privado da conversa e **não deve ser commitado integralmente** sem revisão e sanitização de IDs de credencial, identificadores Meta, conta de hospedagem, metadados da instância e domínios de terceiros. Esta auditoria descreve estrutura/risco sem reproduzir identificadores privados.
