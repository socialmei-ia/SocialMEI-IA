# Piloto Instagram nativo — @testefacep

26/10/2026. Continuação a partir do aplicativo V22 publicado em47c3ba8 e do publicador corrigidoaeba0cc. Branch `feat/instagram-native-pilot`. A PR101 permanece separada: seu HEAD atual não é ancestral desta branch. Esta base já contém os contratos/runtime utilizados na versão publicada; não mesclar ou reescrever a branch do laboratório para acrescentar controles nativos.

## Evidências fornecidas pelo proprietário

Consultas somente leitura executadas pelo proprietário na VPS identificaram:

| Uso        | Workflow           | Situação e versão                                             |
| ---------- | ------------------ | ------------------------------------------------------------- |
| Direct/IA  | `LHlqroY2xzvpYAmD` | ativo; versão salva/ativa8230a3fb-cee9-4847-8d3d-7d07b213436a |
| Publicação | `A0EcNxcRvfWnMwKI` | ativo; versão salva/ativa7cb4f667-b9f7-491b-93c5-fe7a990ab073 |

O atendimento tem webhookPOST e uma chamadaPOST a `/messages` em Graph Instagram. A publicação usa Form Trigger/formulário em etapas e criação/publicação de mídia em Graph Facebook. Ambos têm URLs com destino numérico fixo; isso ainda não identifica o perfil de destino nem atesta a validade das credenciais. Não tratar essas contas como pertencentes automaticamente ao usuário logado ou a todo workspace. Nenhuma execução ou alteração de workflow foi feita por esta implementação.

O painel mostrado pelo proprietário confirma Instagram Login no aplicativo geral1062521390004147; o Instagram Client ID é27816981071315232. São IDs públicos diferentes. O proprietário informou ter cadastrado o callback:

`https://socialmei-ia.54-94-213-7.sslip.io/api/v1/instagram/meta/oauth/return`

A URL incorporada recebida inclui `instagram_business_manage_insights`, que o contrato implementado não aceita. Para este piloto solicitar apenas `instagram_business_basic`, `instagram_business_manage_messages`, `instagram_business_content_publish`. Não alterar permissões/credenciais já utilizadas pelo n8n. Não adicionar insights apenas para aceitar a URL copiada.

## Implementação desta etapa

`frontend/scripts/v22-instagram.js` conecta os controles originais de Configurações/Integrações e Divulgação/Conexões à prontidão, status e início OAuth existentes. Não muda CSS, composição ou animações. O script é opcional: uma falha em carregá-lo não derruba a gestão.

- GET `/api/v1/integrations/readiness` decide disponibilidade; GET `/api/v1/instagram/meta/status` confirma conexão e disponibilidade do token. Não usa localStorage como prova de vínculo.
- POST `/api/v1/instagram/meta/oauth/start` usa sessão, identidade e CSRF existentes; somente responsáveis iniciam pelo frontend e o backend mantém sua autorização independente.
- URL oficial validada novamente no navegador: HTTPS, host Instagram, caminho, callback da própria origem, client/state/escopos e parâmetros únicos permitidos. State não é salvo no navegador. URLs com segredo ou permissão desconhecida são rejeitadas.
- Retorno `#instagram=connected` leva a Integrações e consulta status; o fragmento não comprova conexão. Falha não vira sucesso local.
- Clique em Instagram remoto não executa o antigo toggle demonstrativo do frame. Modo local mantém a demonstração original.
- Conexão OAuth não equivale a recebimento/publicação. UI informa explicitamente quando ingresso ou publicação ainda não estão habilitados. Não afirma que a conta conectada é @testefacep sem verificação da identidade.

## Avanço de implantação segura (26/10)

O Compose da equipe agora entrega as variáveis `SOCIALMEI_INSTAGRAM_*` à API, com todos os recursos desativados por padrão. Isso resolve um bloqueio de configuração: escrever valores em `.env.team` anteriormente não os encaminhava à aplicação. **Isso não significa conta conectada, deploy ou webhook ativo.**

A ferramenta `tools/instagram-proxy-privacy.py` prepara candidatos de Caddy para o proxy público e gateway. Ela lê a configuração ativa (API admin localhost), adapta a configuração de arquivo e recusa prosseguir se as duas diferirem. Cria uma alteração somente de codificação de logs e verifica que não muda rotas, autenticação, proxies, TLS nem outros parâmetros. Remove URI completa, cabeçalhos da requisição e cabeçalhos da resposta dos logs, preservando diagnósticos de erro. Havendo logger personalizado não protegido, bloqueia a operação. **Não escreve Caddyfiles ativos, não recarrega containers e não altera segredos.** Há testes com 502 sintético em Caddy descartável, executados pelo CI.

No servidor Ubuntu, *após revisar a PR e atualizar os scripts com controle de versão*, preparar apenas os candidatos privados:

```sh
cd /home/ubuntu/socialmei-team
umask 077
python3 tools/instagram-proxy-privacy.py prepare \\
  --output-dir /home/ubuntu/socialmei-backups/instagram-pilot-inspection
```

A saída privada é apenas para conferência. Se houver divergência entre configuração ativa e arquivo, **pare**: não copie arquivos gerados nem marque `SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED=true`. Antes de liberar callbacks, alguém com acesso operacional deve revisar Caddyfile público, gateway e qualquer outro logger upstream/downstream, aplicar os filtros por procedimento com backup e rollback, verificar um canário sintético e confirmar observabilidade sem URI/cookies/headers sensíveis.

Somente após tal revisão e com aplicação controlada das migrations do backend, preparar `.env.team` em modo privado com as configurações corretas do Meta Dashboard: Instagram Client ID (não confundir com App ID geral), App Secret, URL completa de autorização com callback registrado, Graph version oficialmente suportada, escopos `instagram_business_basic` e `instagram_business_manage_messages`, keyring de 32 bytes por chave em base64url e key ID ativo. A API exige `TEAM_AUTH_ENABLED=true`. Nunca cole segredos em issues, chat, commits, logs ou frontend.

Sequência de flags a ser aplicada em mudança operacional separada, com backup e validação:

1. Primeiro, `SOCIALMEI_INSTAGRAM_RUNTIME_MODE=connect`, `SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED=false`, `SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false`, e `SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED=true` **somente depois** dos filtros ativos e revisados. Reiniciar API de forma controlada, confirmar readiness e autorizar a conta profissional pelo botão no site.
2. Verificar pelo status real que a conta conectada é a conta pretendida e está vinculada ao negócio certo; validar expiração, desconexão e revogação de acesso.
3. Resolver estratégia de webhook com o n8n existente. Não sobrescrever o único endpoint Meta nem fazer dupla resposta. Habilitar ingress apenas depois de validar assinatura HMAC dos bytes originais e tratamento de duplicações; testar um Direct controlado na Caixa.
4. Habilitar envio de resposta somente após acordar quem é o remetente único (n8n ou outbox), com aprovação humana e garantias anti-replay. Publicação de Feed/Stories/Reels ainda exige contrato autenticado, mídia durável e idempotência; o formulário público do n8n não oferece isso automaticamente.

Nenhum passo acima deve ser confundido com implantação já realizada.

## Pendências para teste real

1. Conferir versão Graph usada/homologada e configurar Instagram App Secret somente no servidor, com keyring durável protegido. Não enviar segredo/token pelo chat, Git ou frontend.
2. Revisar redação de query/cookies nos logs de Caddy público e gateway antes de liberar callbacks reais. Não marcar `PROXY_PRIVACY_REVIEWED` sem essa revisão.
3. Habilitar inicialmente OAuth sem envio. Verificar autorização pelo responsável e identidade do @testefacep; a configuração de servidor ainda não foi alterada por esta branch.
4. Preservar o callback/webhook do n8n enquanto se prepara o encaminhamento autenticado ao SocialMEI. O fluxo ativo já responde com IA; não ativar um segundo remetente. Não usar endpoints sintéticos para mensagens reais.
5. Publicação nativa ainda requer entrada autenticada específica no n8n, vínculo de conta por negócio, mídia validada e armazenamento, job idempotente e recibo de publicação. O Form Trigger e os IDs fixos não constituem esse contrato. Não rotular esta etapa como Feed/Stories funcionais.
6. Deploy de código/configuração e mudanças em workflows vivos precisam de plano específico, backups e validação. O publicador padrão intencionalmente para se detectar integrações reais ligadas; revisar esse gate antes de futuras atualizações de um ambiente já conectado.

Meta Login e Graph Facebook usados pelo publicador têm modelos de permissão diferentes. Não reutilizar cegamente tokens/scopes de uma modalidade na outra. O backend opcional permanece disponível como alternativa; não substitui silenciosamente o executor n8n do colega.

## Verificação

Browser controlado cobre servidor desabilitado, início de autorização oficial simulado, conexão confirmada pelo servidor, membro sem gestão, callback forjado e URL maliciosa. Os testes não fazem requests reais à Meta. Capturas em390/1440, claro/escuro, ficam em `test-results/instagram-native/`; navegação/matriz V22 e preview real descartável continuam executados. Contas/tokens reais e entrega/publicação externa continuam não homologados.

## Inspeção operacional sem exposição de segredos

`python3 tools/instagram-pilot-inspect.py` pode ser executado na VPS pelo operador. Faz somente docker inspect, leitura da configuração Caddy ativa (ou arquivo claramente marcado como não confirmado) e SELECT com sessão PostgreSQL read-only nos dois workflows. Mostra versão Graph, coincidência de versões, presença de parâmetros privados e metadados limitados dos filtros de log. Não mostra valores de App Secret/keyring/webhook token, parâmetros de nós, credenciais, mensagens ou dumps. Não faz chamadas Meta nem modifica containers/configurações. O relatório não marca privacidade revisada nem habilita OAuth; serve para fechar o plano específico de configuração.
