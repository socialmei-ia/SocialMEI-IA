# Instagram real — candidata da PR #113

## Estado verificável

Base conferida no GitHub: #112 `650ee5e901db8237449460f27d1fcd4dfd9f5c82`; #113 iniciou em `32e761b265e5b700dee26dfef4c5a8dc95a88bb1` (CI anterior aprovado). A branch mantém essa ancestralidade. A AWS em `650ee5e` e as proteções privadas são informações fornecidas pelo operador; esta execução não tem SSH nem credenciais Meta/n8n. Nenhuma implantação ou chamada real foi realizada. A Issue #114 continua aberta até comprovar foto e Direct reais.

## O que foi completado

- Divulgação mantém a tela V22. Seu controle Instagram abre seleção de arquivo, prévia, legenda e confirmação do perfil consultado na Meta. Não reutiliza o toggle demonstrativo como prova de conexão.
- Upload autenticado JSON/base64, limite de 2 MiB por arquivo (fica abaixo do limite existente de 3 MB do gateway), JPEG/PNG/WebP estáticos. Pillow decodifica, limita pixels/proporção e produz JPEG novo sem EXIF/GPS. HEIC, animações e vídeos ficam indisponíveis neste primeiro corte.
- Migration **028** adiciona armazenamento temporário `bytea`, limite de 20 arquivos vivos por negócio (até 40 MiB), vínculo com criador e expiração de uma hora. Migration **027** mantém as intenções de publicação. Nenhuma migration anterior foi editada.
- A Meta busca o JPEG por uma chave aleatória de 256 bits; apenas esse caminho GET é público. Expirado retorna 404. Cookie/Authorization não são encaminhados nessa rota. Não existe listagem pública. O operador deve tratar quem recebe o link como alguém capaz de ver a foto até expirar.
- Limpeza limitada de expirados em cada upload; limpeza adicional no container da API: `python instagram_media_cleanup.py` inspeciona, `python instagram_media_cleanup.py --apply` remove apenas mídia expirada. Preparar execução periódica após implantação. Expiração de acesso não significa expurgo imediato dos backups.
- Publicação: sessão/CSRF, owner/admin revalidado no banco, conexão vinculada ao negócio e comparação da conexão confirmada. Claim persistido antes do primeiro POST, trava por operação e fingerprint; chamadas simultâneas não criam dois containers.
- Consulta `status_code` antes de `/media_publish`; `IN_PROGRESS` permanece pendente. Continuação autorizada por POST, no máximo uma consulta por minuto. `ERROR`/`EXPIRED` não publicam; timeout/resultados desconhecidos não repetem o envio. Sucesso exige ID válido retornado por `/media_publish`.
- A interface guarda apenas o identificador da tentativa em sessionStorage com escopo de usuário/negócio. Reabrir/recarregar consulta o recibo, sem novo POST de publicação. Nova tentativa incerta exige aviso explícito. Nenhum token é entregue ao navegador.
- Caixa remota recebe atualização pelo polling existente de seis segundos sem recarregar documento ou trocar a conversa aberta. Mudança de identidade/capacidade invalida respostas antigas, remove conversas de demonstração e informa corretamente que o envio permanece indisponível.
- Logs: Caddy protegido deve ser preservado. A API também mascara o caminho-capacidade antes do access log do Uvicorn; teste com servidor real e canário confirma a redação.

## Contrato e documentação do provedor

Referências oficiais consultadas em 26/10/2026: [coleção Meta Instagram](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-894be833-d0b6-4877-859e-c61ae6474d64) e [guia Instagram Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/). A coleção confirma as etapas container/processamento/publicação e permissão `instagram_business_content_publish`; o guia completo não ficou acessível nesta sessão. Não afirmar homologação de uma versão Graph: o código usa **a versão explicitamente configurada no servidor**, sem substituir automaticamente v22/v23 dos workflows. Compatibilidade final depende de respostas reais da Meta. Testes automatizados usam transport sintético.

## Operação segura no team

1. Confirmar CI **no novo HEAD** e executar `tools/instagram-release-preflight.py --target team --inspect` na VPS. Saída restrita a revisões/health/flags, contagens OAuth/migrations, estrutura de rotas e metadados n8n. O padrão sem `--inspect` não consulta o runtime.
2. Confirmar OAuth pelo próprio SocialMEI, como responsável, e comparar o perfil confirmado com `@testefacep`. Contagem de conexão criptografada no banco não comprova validade do token na Meta.
3. Inspecionar Compose efetivo de **cada** serviço separadamente e configuração ativa dos proxies. Preservar `.env.team`, keyring, origens, redes, volumes, cookies, proteção de logs e overlays persistentes. Checkout `6f4c8e1` não identifica a imagem instalada. Não usar somente o Compose antigo nem o workflow genérico de produção.
4. Executar backup documentado e validar dump/índice; salvar imagens atuais e config de execução com checksum em pasta 0700 fora do Git. Registrar IDs/revisões atuais e caminho do rollback. Não expor `docker inspect`, `.env` ou Caddyfile completos.
5. Preparar imagens API/gateway a partir do SHA da candidata e validar fora do ar. Usar a configuração **ativa protegida** como base para o gateway; acrescentar somente `/media/instagram/*` GET (sem Cookie/Authorization) e `/webhooks/instagram` GET/POST para a API. Comparar JSON adaptado preservando todo o restante. Os Caddyfiles do repositório são referências, não substitutos do overlay privado.
6. Pelo runner documentado, aplicar **somente 027 e 028 ausentes**, transacionalmente, após backup. Não reaplicar 019–026. Preparar flag `SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED=true` somente para API e somente após confirmar a conta/rotas/CI. Ingress e Direct send continuam false inicialmente.
7. Recriar apenas API e gateway, `--no-deps --no-build --pull never`, usando os arquivos Compose efetivos e overlays privados revisados. Aguardar health API, HTTP do gateway e HTTPS antes de marcar sucesso. Nunca recriar banco/n8n/Caddy público/WAHA para esta atualização.
8. Conferir cadastro/login/CRM com sessão e respostas anônimas 401/404, landing conforme baseline aprovado, CSS/JS, downloads de mídia e isolamento. O operador confirma uma foto específica antes do único teste real; registrar somente ID de mídia/estado, sem tokens ou conteúdo privado.

### Rollback

Desabilitar publicação/ingress/send e restaurar somente imagens/configuração anterior da API/gateway, incluindo overlay protegido e mesma keyring. Não apagar banco, mídia ou recibos; 027/028 são aditivas e podem permanecer. Não reenviar intenções `uncertain`. Conferir HTTPS, sessão e demais containers após rollback. Não usar down, prune, reset de volumes ou down migrations. O rollback anterior `compose.instagram-rollback.yaml` só pode ser usado após revalidar que representa o baseline atual.

## Direct e convivência n8n

Workflows existentes: Direct `LHlqroY2xzvpYAmD`, publicação `A0EcNxcRvfWnMwKI`. Nenhum foi executado/modificado. O segundo usa Form Trigger, não é um endpoint autenticado do CRM. Publicação nativa nova chama Meta diretamente com o token do workspace; não dispara o Form, evitando dois publicadores para a mesma operação.

A API já verifica GET challenge, POST HMAC do corpo bruto, conta→workspace, deduplicação e persistência na Caixa. **Ainda falta decidir e validar a entrega real**: manter callback n8n e encaminhar os bytes originais/assinatura, ou cutover coordenado após homologação. Nunca reserializar JSON e inventar assinatura Meta, nem redirecionar o callback existente sem conhecer seu contrato. A inspeção nova mostra método, modo de resposta, rawBody e hash do caminho; não revela URLs privadas.

Ingress só deve ser ativado após confirmar assinatura/assinatura de eventos, inscrição `messages` da conta e entrega sem perda ao n8n. Testar um Direct externo entrando na Caixa do negócio correto. Contas externas ao time podem exigir aprovação/Advanced Access; CI não confirma permissões do painel.

Resposta humana depende de definir um único remetente e sua convivência com IA n8n. A outbox preparada permanece sem dispatch automático; não habilitar dois respondedores. Reels/Stories/carrossel/agendamento ficam para depois do primeiro ciclo real homologado.

## Verificação local desta continuação

- `npm test`: 337 aprovados; `npm run format:check` aprovado.
- Python completo com PostgreSQL 16 criado exclusivamente para o ensaio: 443 aprovados, incluindo sessões reais, dois negócios, ingress e Direct outbox; provider sempre sintético.
- Operações: 100 testes, 13 opt-in não executados nessa chamada. Execuções dedicadas adicionais: 11 testes de gateway real e 18 de privacidade Caddy aprovados.
- Browser V22: 286 estados/11 larguras/2 temas, fluxos de entrada, teclado e movimento reduzido; publicação local em 1440/390 claro/escuro, consulta de perfil atrasada, clique duplicado e recibo após reload; polling preservando a conversa em desktop/mobile. Zero erro JS nas suítes.
- Fixtures de privacidade em containers `--network none` limpam somente proxies desses próprios containers, para que o wget acesse o loopback. A proteção/asserção 502 e os canários permanecem completos.
- Em desktop, o shell V22 aplica CSS zoom; o tradutor CDP de cliques em iframe não inclui esse zoom ancestral. O helper de teste calcula pixels de viewport e confirma hit-test do controle e iframe antes do clique real. Não usa `force`, dispatch de clique ou alteração de estilos para passar a navegação.
- Capturas: `test-results/instagram-publisher/{1440,390}-{light,dark}.png`. São interface real com respostas controladas, não provas de postagem na Meta. CI remoto precisa confirmar o novo HEAD; ver checks da PR #113.

## Preparador operacional (sem implantação)

`tools/instagram-release-prepare.py --target team` não consulta Docker nem servidor. A opção `--prepare` exige SHA completo, imagens de baseline explícitas e diretório novo diretamente em `/home/ubuntu/socialmei-backups`. Só deve ser executada quando o operador estiver na VPS e após conferir a inspeção.

O preparador lê separadamente os arquivos Compose dos labels de API/gateway, confere ambiente/redes/mounts/imagens e bloqueia checkout sujo, API sem saúde, runtime divergente, integrações de envio/ingresso/publicação já habilitadas ou migrations fora de 027/028. Aceita OAuth em modo de conexão e mantém keyring/credenciais existentes, sem sobrescrevê-los.

Prepara overlays que mudam somente imagem e `SOCIALMEI_RELEASE_SHA` da API. Confere novamente o resultado do Compose com esses overlays. Para o gateway exige bind privado persistente, compara Caddyfile com JSON ativo e acrescenta somente os handlers de mídia/webhook ausentes; filtros, autenticação e demais rotas são preservados. O teste em Caddy real comprova que o arquivo e a configuração ativa permanecem intactos. Nomes internos `groupN` podem ser renumerados pelo adaptador: a comparação preserva rigorosamente a igualdade entre grupos, recusando divisão/fusão.

Os arquivos gerados são **privados** (pasta0700/arquivos0600), pois contêm configuração de execução. Não os envie ao GitHub ou ao chat. O recibo registra SHA, IDs imutáveis, checksums e migrations ausentes. Preparar não significa executar backup, construir imagem, aplicar SQL, recriar serviço, recarregar Caddy ou ativar OAuth/publicação/webhook.

Antes de aplicar será necessária nova conferência de drift e backup verificável, seguida do procedimento controlado acima. **Não use `docker compose build` com o checkout antigo**: construir as imagens com o código do SHA candidato num diretório separado; Compose efetivo é usado somente para preservar o runtime. O publicador V22 antigo não deve ser utilizado automaticamente num ambiente com OAuth/overlays protegidos: seus gates foram projetados para integrações desligadas e Caddy da imagem, e não foram relaxados nesta preparação.

O preparador também recusa qualquer handler HTTP de autenticação no gateway, mesmo quando as rotas aparentam estar presentes. É uma restrição conservadora: se existir Basic Auth apenas numa rota privada, ainda será necessária revisão específica; o script não tenta remover ou reinterpretar a proteção. Os testes cobrem recusa por autenticação anterior aos handlers. Passar a inspeção estrutural não comprova entrega HTTP: respostas anônimas e fluxo completo continuam obrigatórios antes da ativação.
