# Instagram receive-only: gates para a candidata #212 (10/11/2026)

> **Preparação técnica, não autorização de deploy.** O WhatsApp WEBJS deve permanecer intacto. Não publicar/mesclar automaticamente nem trocar o worker, webhook GOWS ou o banco.

## Estado do servidor observado por auditorias de leitura

- API: `sha256:cd88dcbbb9f3d4a6d998eccd18b664d34507989bb47fe1f17602c1faecf4d5a2`, label `a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510`; API saudável.
- Gateway: `sha256:78691bf1c19d0dcd7416986cc3f36adc6f07614f27a49f24b6659c6854441d50`, mesmo label.
- 38 migrations no banco `socialmei_team`; 1 OAuth IG cadastrado com token criptografado e prazo não expirado. Isso **não confirma** permissões/inscrição junto à Meta.
- API: `SOCIALMEI_INSTAGRAM_RUNTIME_MODE=connect`, ingresso true, send/publish false, privacy reviewed true.
- n8n: workflow IG principal ativo, 17 nós salvos, 1 webhook POST, `responseMode=onReceived`, `rawBody=false`. O grafo salvo ainda alcança quatro nós classificados como IA e duas requisições HTTP. Não comprova envio real, mas **não é receive-only**.
- Banco: zero `ig_meta_ingress_events` e zero mensagens com `origin=instagram`. Nenhuma recepção real foi comprovada.
- Gateway interno Caddy: configurações **ativas** exibiram rota GET/POST do webhook, mídia GET e mascaramento de URI/headers em logs. Public proxy Caddy também tem filtro de logs; sua inspeção retornou `routes=false` para conexão **direta** ao `team-api`. Isso **não prova falha**: o proxy público normalmente encaminha ao gateway intermediário. A cadeia real até o gateway permanece um gate.
- WEBJS WORKING com 1 webhook, worker apontado para WEBJS. GOWS FAILED com 0 webhooks.

## Identidade imutável da candidata

- Aplicação [PR #212](https://github.com/socialmei-ia/SocialMEI-IA/pull/212): `345a074310673640084c7634e3da75dd72491813`, 38 migrations.
- Bundle 13414736091 com SHA256 `0ff6d5364e54f003016c70c2408412006e981fe3bf30831f44eb5c4970e1767a`. A evidência de laboratório reporta API image id `sha256:db132bb3ba656388ef093654821cad7d37291ddc7c2f328e50eadbfd8b38f628`; não presumir identidade só por tag.
- A candidata introduz **a rota autenticada POST `/webhooks/instagram/n8n` no backend e a regra correspondente no `deploy/team/Caddyfile`**. São componentes acoplados, não publicar apenas a API ou apenas o gateway.
- A API protege esse relay com credencial própria, assinatura Meta original e binding explícito para workspace; o modo de recepção n8n exige configuração privada dedicada. O ingresso geral do Instagram habilitado hoje **não significa** que esse relay novo também esteja habilitado.
- O preparador `tools/prepare-instagram-persistence.mjs` gera alteração do workflow de 17 para 23 nós com `rawBody=true`, resposta após persistência, e `resumeLegacy=false` por padrão. O preparador **não publica** o workflow.
- Verificador estrutural offline: `tools/instagram212-source-gate.py` nesta PR de pré-voo; apenas valida contrato versionado, não entrega do provedor.

## Bloqueios até a autorização operacional

1. **Contexto real:** fixar IDs de imagem, labels, configuração Compose efetiva, overlays privados (incluindo GOWS dual) e suas origens para API e gateway. Detectar mudanças desde a coleta. A label do checkout `a472` não comprova que a imagem não tenha adaptações locais.
2. **Candidato/binário:** obter o bundle exato, validar SHA256, hashes internos e imagens OCI. Não recompilar de `latest` nem substituir arquivos de produção por `git pull`.
3. **Backup/restore:** validar backup consistente do PostgreSQL038 e ensaiar restore em destino isolado. Preservar imagens, overlays privados, n8n, Caddy e credenciais sem publicar arquivos.
4. **Operador apropriado:** criar e ensaiar operador *exclusivo para #212*, preservando API/gateway, WAHA/worker, n8n e Compose atual. O operador da [PR #211](https://github.com/socialmei-ia/SocialMEI-IA/pull/211) está pinado à #210 `7ba3d632` e **não pode aplicar #212**. Sua validação de baseline também pressupõe overlay que pode não corresponder ao atual `gows-dual-live-20261109`.
5. **Roteamento:** verificar que o domínio público chega ao gateway ativo, e o novo POST autenticado segue somente até a API, sem expor credenciais nos logs. O fato de `public_proxy_privacy.routes=false` para `team-api` direto não é por si só uma falha.
6. **Workflow publicado:** exportar snapshot privado **da revisão efetivamente publicada** do workflow n8n e seu hash; conferir ID do webhook e conexões. Gerar diff de 17→23 nós, sem editar nós existentes; `resumeLegacy=false`, resposta somente após persistência e 503 em falha. Importar/publicar só após revisão/rollback e autorização.
7. **Meta:** conferir callback realmente inscrito, verify token, HMAC, escopos, validade real do token OAuth e os dois perfis autorizados, sem imprimir segredos. Uma conexão no banco não prova essa inscrição.
8. **Teste controlado:** evento real de cada perfil, sem IA/envio legado, aparece uma vez na Caixa do workspace certo; replay não duplica; API indisponível não recebe ACK de sucesso. Incluir evidência de proteção cross-workspace e confirmar que WEBJS continua recebendo/enviando normalmente.

## Critérios NO-GO imediatos

- Qualquer divergência de imagem/overlay/configuração sem operador validado.
- O workflow continuar alcançando IA após o corte.
- Ausência de backup restaurável em destino isolado.
- Duas rotas de entrada ativas com respostas concorrentes ou repetição de mensagem com recibo incerto.
- Candidato API sem a rota do gateway ou vice-versa.
- Falta de validação de assinatura Meta, OAuth e binding de workspace.

**Estado atual: preparação offline do contrato API+gateway+workflow, sem GO de produção.**
Fontes: [plano P0 #216](https://github.com/socialmei-ia/SocialMEI-IA/issues/216), [PR #212](https://github.com/socialmei-ia/SocialMEI-IA/pull/212), [ensaio isolado #213](https://github.com/socialmei-ia/SocialMEI-IA/pull/213).