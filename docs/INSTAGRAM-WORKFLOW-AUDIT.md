# Auditoria — publicação Instagram (export recebido)

**Data:** 19/10/2026 · **Método:** leitura estática do arquivo recebido pelo responsável, sem executar nós, consultar tokens, alterar n8n, publicar no Instagram ou fazer deploy.

## Evidência e proveniência

- Export `Publicar post no Instagram` com **40 nós** e `active: true` no arquivo; isso **não comprova** a ativação atual no servidor.
- O export declara um **ID de workflow diferente** do `A0EcNxcRvfWnMwKI` historicamente inventariado no n8n da AWS (este inventário o mostrava inativo). Não tratar dois fluxos com mesmo nome como a mesma versão.
- A navegação de retorno do formulário aponta para **`facepe2027.app.n8n.cloud`**, enquanto o SocialMEI usa outra instância em AWS. Confirmar com o responsável onde o fluxo roda e quem controla a conta antes de abrir qualquer piloto.
- Há referências a credenciais de Meta e ImgBB no export, **sem os valores secretos**. Os identificadores, preset e conta de terceiros não foram incorporados ao código público.

## Contrato observado no formulário (não é API)

| Campo | Entrada | Observação |
| --- | --- | --- |
| `tipo_publicacao` | `Post no Feed`, `Reels`, `Story` | Escolha da modalidade |
| `quando_publicar` | `Agora (usar hora atual)` ou `Agendar` | Opção de horário |
| `media` | JPG/JPEG/PNG/MP4/MOV | Um arquivo para Reels/Story; múltiplos no Feed |
| `modo_varias` | `Carrossel (um único post)` ou `Posts separados (um por foto)` | Só para Feed |
| `legenda` | Texto | Legenda não aplicada ao Story na rota Meta |
| `data_agendamento`, `hora_agendamento` | Data/hora | Só agendamento; interpretado em `America/Sao_Paulo` |

O n8n recebe arquivo binário no **Form Trigger**, não em webhook autenticado de API do SocialMEI. O resultado é exibido pela etapa de conclusão do próprio formulário (`status`, `mensagem` e eventual `instagram_media_id`); não há contrato HTTP com `publication_id` consultável pelo app.

Fluxo declarado: formulário em duas etapas → normalização → divisão dos arquivos → hospedagem pública ImgBB/Cloudinary → consolidação → Wait por horário → switch Feed/Reels/Story → criação e publicação dos containers na Graph API da Meta → confirmação ou erro.

## Achados e prioridade

| Prioridade | Achado | Efeito / ação |
| --- | --- | --- |
| **P0** | Destino de publicação preso a um ID de conta Instagram nos URLs da Graph API. | Publicaria na **mesma conta**, sem autorização por negócio/usuário. Substituir por conta vinculada e autorizada **no backend**, nunca aceitar ID arbitrário do navegador. |
| **P0** | Trigger de formulário sem autenticação, autorização por workspace nem prova de permissão de publicação neste export. | Não reutilizar como API multi-tenant. Avaliar controles externos de acesso separadamente. |
| **P0** | Sem idempotência, estado persistido consultável, callbacks autenticados ou reconciliação após timeout. | Cliques repetidos podem duplicar posts; aceite/sucesso do formulário não fornece rastreio seguro ao SocialMEI. |
| **P1** | Vídeo único de Feed é aceito pelo campo de arquivo, mas `Feed - Criar container` sempre envia `image_url`. | Vídeo de Feed **não homologado**; validar mídia por modalidade e corrigir ramo antes de anunciá-lo. |
| **P1** | O seletor de Reels aceita imagem; o ramo Reels envia `video_url` sem verificar que é vídeo. | Falha previsível na Meta. Validar extensão, MIME, assinatura e limites no backend. |
| **P1** | Hora inválida é limitada com `Math.min` em vez de gerar erro e não há rejeição explícita de data passada. | O agendamento pode ocorrer em momento diferente do escolhido. Validar janela, timezone, formato e passado. |
| **P1** | Agendamento usa Wait dentro do mesmo fluxo de formulário; não existe acompanhamento assíncrono no app. | Não afirmar “agendado” ou “publicado” sem recibo durável e confirmação Meta. |
| **P1** | Hospedagem externa de mídia e credenciais próprias de outra instância. | Rever privacidade, URLs públicas, retenção e armazenamento da mídia; configurar secrets no n8n/backend, nunca no JS. |
| **P2** | Link “Voltar” usa endereço absoluto da instância n8n.cloud. | Se importar para AWS, o link aponta para instância errada; tornar dinâmico. |
| **P2** | Carrossel limitado a 10 fotos e Reels com espera/consulta de processamento. | Manter validações e tratar estados `FINISHED`/erro/timeout antes de publicar. |

## Encaminhamento no SocialMEI.IA

1. **Agora:** manter Divulgação, prévia, cópia de legenda e rascunhos; o piloto de **handoff externo** não transfere mídia/texto, não publica e começa `disabled`.
2. **Antes de qualquer teste real:** verificar instância, titular da conta Meta, credenciais, permissões e fluxo efetivamente publicado; usar conta de testes isolada. A configuração externa exige `mode: "external-pilot"`, `formUrl` e `approvedOrigin` idêntica à origem. **Não configurar URL de terceiro sem consentimento.**
3. **Integração nativa:** app autenticado → API FastAPI autenticada por sessão/workspace → armazenamento privado temporário de mídia e registro persistido idempotente → execução interna n8n por credencial de serviço → status consultável e confirmação Meta por conta autorizada.
4. Criar testes com imagens e vídeos sintéticos, carrossel (2 e 10 arquivos), duas contas isoladas, agendamento futuro/passado, duplicidade, erro Meta, vídeo aguardando processamento, revogação de permissão e timeout com resultado incerto.

**Não realizado:** ativar workflow, abrir link de publicação com credenciais, editar VPS, publicar no Instagram, conectar conta Meta, criar endpoint de publicação real, mesclar PR ou fazer deploy.

## Segurança do material recebido

O JSON original permanece somente como anexo privado da conversa e **não deve ser commitado integralmente** sem revisão e sanitização de IDs de credencial, identificadores Meta, conta de hospedagem, metadados da instância e domínios de terceiros. Esta auditoria descreve estrutura/risco sem reproduzir identificadores privados.
