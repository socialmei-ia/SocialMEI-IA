# Instagram — simulação isolada

## O que foi implementado

O fluxo de testes funciona sem serviços externos: editor Divulgação, mídia local,
API autenticada, registro no PostgreSQL e leitura do estado `simulated`.

Não é publicação real. Não há token Meta, upload, chamada ao n8n ou conta Instagram
real. A mídia é registrada somente por nome, tipo MIME e tamanho.

## Ativação restrita

Exigir staging HTTPS, autenticação remota e um banco de testes migrado.
A ativação é manual e independente em ambas as camadas:

- Backend: `SOCIALMEI_INSTAGRAM_MODE=simulation` (padrão: `disabled`).
- Frontend: `instagramSimulation: { mode: "simulation" }` (padrão: `disabled`).

Nenhuma configuração ou infraestrutura de produção foi alterada.

## Contrato dos endpoints

Todas as rotas abaixo estão sob `/api/v1/instagram/simulation`.

- `GET /status`: indica `transport: "none"` e `published: false`.
- `GET /accounts`: retorna contas fictícias do workspace autenticado.
- `POST /accounts`: cria conta fictícia a partir de `{label}`; apenas owner/admin.
- `POST /publications`: simula um pedido com conta, chave idempotente UUID,
  tipo, legenda, metadados das mídias e data opcional com timezone.
- `GET /publications`: consulta até 30 simulações do workspace.
- `GET /publications/{id}`: consulta somente registro do mesmo workspace.

Os endpoints reutilizam sessão HttpOnly, Origin, CSRF e papéis. O workspace é
obtido da identidade no servidor, não do JSON enviado.

Chaves idempotentes repetidas com conteúdo igual devolvem o registro original.
Usar a mesma chave com conteúdo diferente retorna HTTP 409.
Nenhum registro pode ter `published: true`.

A API aceita até dez imagens no Feed, uma imagem/vídeo para Story e vídeo único
para Reels. O editor ainda seleciona uma mídia. Nenhum agendamento dispara envio.

## Próximas etapas para publicar de verdade

1. Confirmar a instância n8n, o titular da conta Meta e autorização de testes.
2. Implementar conta Instagram vinculada ao workspace com segredos no backend.
3. Acrescentar upload privado, inspeção de bytes, acesso temporário e retenção.
4. Criar disparo autenticado n8n, callback, status durável e reconciliação segura.
5. Homologar mídia, carrossel, agendamento e erros usando uma conta de teste.

O fluxo original possui ID de conta fixo e não deve ser utilizado para vários
MEIs sem essa adaptação. Não ocorreu merge, deploy, migração AWS ou publicação.
