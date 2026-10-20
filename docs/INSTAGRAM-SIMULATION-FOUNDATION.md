# Instagram — simulação isolada (PR em desenvolvimento)

## Escopo

Foi implementado um primeiro percurso **end-to-end em ambiente de testes**, sem publicar: editor Divulgação → snapshot da mídia local → API FastAPI autenticada → tabelas de simulação no PostgreSQL → consulta do resultado `simulated`. Nenhum arquivo binário deixa o navegador: só nome, tipo e tamanho são gravados. A interface deixa explícito que a simulação não é uma publicação real.

**Não é integração Meta/n8n ativa.** O workflow original tem destino Instagram fixo, referências à instância n8n Cloud FACEPE e não possui autorização multi-MEI nem recibo durável. Não expor esse fluxo a consumidores da plataforma.

## Ativação opcional em ambiente de teste

Requisitos: autenticação remota habilitada, HTTPS same-origin, banco migrado por processo autorizado, conta real do SocialMEI com permissões e uma cópia de ambiente sem dados sensíveis.

- Backend: `SOCIALMEI_INSTAGRAM_MODE=simulation`. Padrão `disabled`.
- `frontend/config.js` da instalação de **teste**: `instagramSimulation: { mode: "simulation" }`. Padrão no repositório `disabled`.
- Nada precisa de webhook, Meta token, ImgBB key, Cloudinary preset ou n8n API key. Não ativar em produção pública.
- Os testes de CI usam banco isolado. **Não aplicar migration ou reiniciar serviço AWS nesta etapa.**

## API do simulador

| Operação | Rota | Resultado |
| --- | --- | --- |
| Estado | `GET /api/v1/instagram/simulation/status` | transport `none` |
| Contas fictícias | `GET /api/v1/instagram/simulation/accounts` | apenas contas do workspace autenticado |
| Criar conta fictícia | `POST /api/v1/instagram/simulation/accounts` | `{label}`, somente owner/admin |
| Registrar simulação | `POST /api/v1/instagram/simulation/publications` | `account_id`, `idempotency_key`, `format`, `caption`, `media`, `scheduled_for` opcional |
| Consultar lista | `GET /api/v1/instagram/simulation/publications` | até 30 do workspace |
| Consultar ID | `GET /api/v1/instagram/simulation/publications/{id}` | 404 para outro workspace |

Todo POST usa sessão HttpOnly, validação Origin e header CSRF existentes. O workspace e o usuário vêm do servidor, nunca do corpo. A chave UUID impede repetição do mesmo pedido e rejeita conteúdos divergentes com HTTP 409. A consulta retorna `published: false` sempre. Datas de agendamento são apenas armazenadas; **não existe worker de publicação nem fila de envio**.

O contrato da API aceita até 10 imagens para Feed, imagem/vídeo únicos em Story, vídeo único em Reel. O editor atual só permite selecionar um arquivo; suporte visual a carrossel continua pendente. MIME/quantidades são validados no backend, mas não há verificação binária remota porque arquivos não são enviados.

## Próxima fase real — aguardando dados e homologação

1. Confirmar proprietário da instância n8n/Meta e conta de teste e obter export autorizado sanitizado; não utilizar IDs fixos do JSON original.
2. Criar fluxo server-to-server autenticado com autorização de conta por workspace e tokens só no backend, nunca no Git/JS.
3. Adicionar upload privado real e verificação de conteúdo, limites e retenção; depois carrossel e agendamento durável.
4. Persistir estados `queued/processing/published/failed/uncertain`, autorização, idempotência do comando, callbacks assinados, reconciliação Meta, revogação, retentativas seguras e trilha de auditoria.
5. Homologar com conta e ambientes de teste antes de permitir qualquer postagem real.

**Sem merge, deployment AWS, upload de mídia, ativação do n8n ou contato com a API da Meta.**
