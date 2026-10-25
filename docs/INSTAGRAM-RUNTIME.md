# Configuração de backend Instagram — opcional e desligada por padrão

Reutiliza adaptador, vault, OAuth persistente, ingress durável e outbox anteriores. Não reconstrói o atendimento/IA ou publicação n8n da equipe e não ativa conta, webhook, envio ou post nesta entrega.

## Comportamento

Sem configuração, as rotas de provedor retornam503 e a gestão continua funcionando. Configuração inválida não derruba cadastro/login/CRM. GET `/api/v1/integrations/readiness` exige sessão e informa indisponibilidade, sem ecoar segredos. Configuração não equivale a conexão de uma conta.

Com configuração homologada e schema disponível:

1. POST `/api/v1/instagram/meta/oauth/start` com sessão/Origin/CSRF fornece URL de autorização e state de uso único ligado à sessão/usuário/negócio.
2. O navegador visita a URL oficial; a Meta retorna a GET `/api/v1/instagram/meta/oauth/return`, que exige a sessão original e usa o mesmo consumidor persistente de state.
3. O backend troca o código, consulta identidade e guarda token criptografado pelo vault existente. Falha não é declarada como conexão; timeout não reabre código consumido.
4. O retorno303 usa somente `/frontend/socialmei-app.html#instagram=connected` ou `failed`, sem código/state/token. O frontend deve consultar GET `/api/v1/instagram/meta/status` para a situação atual.
5. GET/POST `/webhooks/instagram` reutilizam assinatura/limites/ledger da #107. A conta é resolvida pelas conexões OAuth autorizadas, sem workspace arbitrário.
6. A outbox existente pode preparar/revisar respostas quando a configuração de mensagens está pronta. Despacho continua bloqueado sem liberação separada e sem a aprovação humana já exigida pelo serviço.

A presença das migrations necessárias e de todas as tabelas dependentes é verificada antes de liberar serviços. Não executar migrations no request. Sem migrations019/020/021 compatíveis, as respectivas capacidades não são reportadas como disponíveis.

## Configuração exclusivamente de servidor

Valores são lidos por settings.py no início do processo, nunca pelo frontend. Não usar exemplos como credenciais reais.

| Variável                                                          | Conteúdo                                                                                                                |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| SOCIALMEI_INSTAGRAM_RUNTIME_MODE                                  | `disabled` por padrão; `connect` somente após configuração/homologação autorizadas                                      |
| SOCIALMEI_AUTH_ENABLED / SOCIALMEI_SHARED_DATA_ENABLED            | Precisam estar habilitados; preservar a origem HTTPS do SocialMEI                                                       |
| SOCIALMEI_INSTAGRAM_CLIENT_ID / SOCIALMEI_INSTAGRAM_CLIENT_SECRET | Aplicativo autorizado para Instagram Login; segredo somente no servidor                                                 |
| SOCIALMEI_INSTAGRAM_GRAPH_VERSION                                 | Versão explicitamente homologada; nenhuma versão real é escolhida automaticamente                                       |
| SOCIALMEI_INSTAGRAM_SCOPES                                        | Escopos exatos aprovados, separados por vírgula; incluir instagram_business_basic, mensagens apenas quando necessárias  |
| SOCIALMEI_INSTAGRAM_AUTHORIZATION_EMBED                           | URL oficial do painel, callback exatamente igual à origem configurada + caminho de retorno acima e escopos coincidentes |
| SOCIALMEI_INSTAGRAM_TOKEN_KEYRING                                 | JSON com1–16 chaves AES-256 em base64url; geradas/armazenadas por processo seguro, sem valor padrão                     |
| SOCIALMEI_INSTAGRAM_TOKEN_ACTIVE_KEY_ID                           | Identificador da chave ativa existente no keyring; preservar antigas até rotação/revisão                                |
| SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED                       | `false` por padrão; `true` somente para recebimento homologado                                                          |
| SOCIALMEI_INSTAGRAM_WEBHOOK_VERIFY_TOKEN                          | Segredo independente para challenge, mínimo32 caracteres; não reutilizar token administrativo n8n                       |
| SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED                          | `false` por padrão; não alterar sem autorização para envio e sem política conjunta com n8n                              |
| SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED                        | `true` é reconhecimento operacional de revisão dos logs/proxies, não uma prova automática de que a revisão ocorreu      |

**Preservar o aplicativo já usado pelo n8n.** Não trocar o callback/webhook Meta do colega pela nova rota sem confirmar produto Login, app, conta, namespace de IDs e estratégia de encaminhamento. Uma integração que recebe a assinatura Meta original precisa preservar os bytes originais; reserializar o JSON invalida a assinatura. Um evento transformado pelo n8n exige contrato de serviço próprio, ainda pendente de conferência. Não importar tokens do n8n nem ativar um segundo respondedor por suposição.

O processo não consulta o provedor no startup. Flags não importam credenciais do n8n, não selecionam conta fixa e não configuram o Meta Dashboard. Nenhum OAuth acontece antes de ação autenticada do responsável. Mudança de configuração requer reinício/revisão controlados; não há reload automático de segredos.

## Privacidade e HTTP

O middleware externo remove query sensível de OAuth/webhook do scope ASGI antes de autenticação, erros e CORS; todas essas respostas usam no-store/nosniff/no-referrer. Isso não configura os proxies a montante. Revisar obrigatoriamente Caddy público/interno, logs de erro/acesso e qualquer observabilidade antes de autorizar callbacks reais. Não registrar URL completa, cabeçalhos, chaves, tokens ou corpo de mensagem.

O transporte só aceita HTTPS com TLS validado, hosts e operações Instagram previstos, sem redirects/repetição automática. Tem limites de resposta/tempo e suprime logs HTTP sensíveis no contexto da chamada, mantendo logs comuns fora dele. Não há upload, publicação de mídia ou worker periódico instalado. Autorização incerta exige novo fluxo; não alegar exatamente-uma-vez no provedor.

Renovação automática/revogação remota/worker e publicação de Feed/Story/Reel continuam fora desta unidade. Status verifica expiração e exige reconexão quando necessária; desconectar remove o token local sem afirmar revogação na Meta. O n8n pode continuar sendo o executor escolhido, desde que seus contratos e vínculos sejam homologados separadamente.

## Testes e homologação

Testes novos usam httpx.MockTransport ou serviços sintéticos, além de PostgreSQL descartável com contas/sessões reais. Cobrem defaults, configuração inválida, privacidade, callback/replay, ligação de conta/negócio, criptografia, webhook/deduplicação e despacho bloqueado. Nenhum teste usa conta, número, token ou mensagem real.

Referências primárias: [coleção oficial Meta](https://www.postman.com/meta/instagram/folder/6raa77c/instagram-api-with-instagram-login) e [Instagram Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login). O acesso direto à página Meta retornou429 nesta rodada; não foi declarada homologação atual do aplicativo/versão/conta e os contratos previamente validados foram preservados. A configuração real depende da equipe responsável.
