# Instagram Login — candidata de integração e roteiro de homologação

**Escopo:** integração isolada das PRs #127 (HTTP Basic), #128 (retorno sem 404) e #129 (grant OAuth plano e diagnóstico) sobre a PR #113. **Não é uma autorização para implantação.** O código da #113 contém recursos futuros de publicação e Direct, que devem continuar desabilitados nesta etapa.

## Estado e evidências necessários

- PR de integração em **Draft**, a partir de `feat/instagram-posts-inbox-real` (não da `main` antiga). Confirmar CI de `validate`, `browser` e `preview` **no SHA da candidata** e confirmar que não há mudança funcional não revisada.
- Antes de qualquer operação na AWS, registrar somente de forma privada as revisões instaladas, os hashes das imagens, o Compose efetivo de **cada** serviço, os mounts, as versões das migrações e os checksums dos Caddyfiles ativos. O checkout da VPS não identifica por si só a imagem em execução.
- Conforme diagnóstico anterior do operador, a produção tem migrações **001–026** instaladas, OAuth em modo `connect`, e `SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED=false`, `SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false`, `SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED=false`. Reconfirmar esses fatos no momento da mudança; não deduzir o estado atual a partir deste arquivo.
- A atualização de referência `deploy/team/Caddyfile` não deve substituir o Caddyfile privado ativo. A remoção de HTTP Basic já foi aplicada no gateway por procedimento anterior; confirmar igualdade das propriedades de segurança, sem remover autenticação de aplicação, cabeçalhos de origem ou filtros.
- A inspeção **somente leitura** `python tools/instagram-release-preflight.py --target team --inspect` é apropriada **quando o operador estiver na VPS**; não envia segredos para GitHub nem precisa ser executada para desenvolver a candidata.

## Gate de aprovação e backups

1. Solicitar autorização **específica** antes de alteração em produção, incluindo SHA exato da imagem candidata, serviços a trocar, janela, impacto e plano de retorno. Não interpretar aprovação da PR como aprovação de deploy.
2. Antes do corte, conferir saúde HTTPS/API, cadastro/login, sessão, frontend e integrações existentes. Criar backup do PostgreSQL **com restauração verificável em destino descartável**, preservar imagens instaladas e configurações privadas com checksums e identificar volumes/rede do gateway. Não copiar segredos, valores de cookies, state ou códigos OAuth para relatório.
3. Construir API e gateway a partir de um **checkout separado no SHA autorizado**, nunca do checkout antigo da VPS. Conferir Compose renderizado com overlays privados e hashes imutáveis. Não usar `git pull` ou `docker compose up` genérico como procedimento de atualização.
4. O OAuth **já utiliza a migração 019**. Para o piloto de conexão, **não aplicar 027 nem 028** e não habilitar publicação. Se a auditoria encontrar uma dependência não prevista dessas migrações para o modo `connect`, interromper e revisar a candidata em vez de avançar automaticamente.
5. Manter n8n, seu PostgreSQL, banco do SocialMEI, WAHA e proxy público intactos. Se a revisão exigir mudar qualquer um deles, interromper e obter outra aprovação explícita.
6. Trocar apenas os serviços previamente autorizados, usando imagens e overlays auditados, sem recriar dependências/volumes. Validar imediatamente a rota de retorno do OAuth, frontend V22, API/health, cookies, ausência do desafio HTTP Basic e login próprio do SocialMEI.

## Aceite do Instagram @testefacep

1. Na sessão real de responsável do workspace correto, iniciar uma **nova** autorização Meta. States anteriores consumidos, cancelados ou `failed` **não podem ser reaproveitados**.
2. Verificar que a URL pública de retorno preserva a sessão válida e redireciona diretamente a **Configurações → Integrações**, sem tela 404. O fragmento `#instagram=connected` não prova êxito por si só.
3. Verificar `GET /api/v1/instagram/meta/status` **com sessão autenticada**: `status=connected`, `credential_available=true` e perfil correspondente a `@testefacep`, se exibido. Sem sessão, HTTP 401 continua correto.
4. Validar no banco somente **contagem/estado** da conexão do workspace correto e ciphertext existente; **não consultar nem registrar token em texto puro**. Conferir que não houve conexão cruzada entre workspaces.
5. Caso falhe, usar exclusivamente o evento sanitizado `instagram_oauth_failed` (fases `consent_denied`, `exchange`, `extend`, `identity`, `vault`, `connection_conflict`; status HTTP numérico quando conhecido). Esses eventos só aparecem em **novas tentativas na imagem atualizada**; o histórico `failed` não permite inferir retroativamente a fase.
6. Revalidar cadastro, login/logout, CRM, configuração do negócio, HTTPS e frontend mobile. Documentar somente status, versões e resultados sem informações pessoais ou segredos.

## Política de parada e rollback

- Interromper se CI não estiver verde no SHA final, se a configuração privada divergir, se falhar a restauração de backup, se os flags de publicação/ingresso/envio estiverem habilitados inesperadamente, se surgir 401 com sessão válida, ou se houver regressão no login/CRM.
- Rollback deve restaurar **somente** as imagens/configurações anteriores dos serviços autorizados, mantendo keyring e volumes. Não apagar bancos, estados OAuth, mídia, filas nem workflows. Não executar `compose down --volumes`, `prune`, reset de migrações ou rollback destrutivo.
- Não publicar imagem, Stories/Reels nem Direct no piloto. Publicação (migrações 027/028) e ingress/webhook+n8n são fases independentes posteriores, com nova autorização, testes de assinatura/deduplicação e definição de um único respondedor.

**Referência operacional complementar:** [INSTAGRAM-REAL-RELEASE.md](INSTAGRAM-REAL-RELEASE.md). A análise da VPS e a autorização real com Meta permanecem pendentes.
