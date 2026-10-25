# Conferência da ponte SocialMEI–n8n — 25/10/2026

## Confirmado pelo proprietário

O colega opera o atendimento Instagram com IA e um formulário/site que publica Reels/Stories na instância `https://socialmei.54-94-213-7.sslip.io`. O objetivo é reutilizar os workflows, não refazê-los ou substituí-los silenciosamente.

## Limite da leitura nesta conversa

O estado observado do ambiente informa política de rede enforced sem o domínio do n8n, nenhum segredo de rede e nenhuma identidade de saída. Não há ferramenta autenticada n8n nesta sessão. Não foi feita chamada autenticada, execução, alteração, importação, publicação ou consulta de dados privados do servidor. A conexão de uma conversa anterior não comprova acesso neste ambiente.

Para auditoria pela API: liberar o domínio e vincular N8N_API_KEY como segredo de rede ao cabeçalho X-N8N-API-KEY. Não imprimir/ler diretamente o segredo como variável nem enviar seu conteúdo pelo chat. Consultar primeiro GET `/api/v1/workflows?limit=1`; depois limit10 e cursores. Interromper se houver bloqueio do proxy. Não solicitar pinData, dados de execuções ou credenciais; saída apenas de metadados/topologia sanitizados.

## Referências do Git, não prova do runtime

| Arquivo/referência                              | Estrutura observada                                             | Limite                                                                                                           |
| ----------------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| experimental/instagram-agent.json               | 7 nós: webhook, resposta, agente/Gemini, memória, switch e HTTP | Export sanitizado inativo; não identifica a versão viva nem suas credenciais                                     |
| experimental/instagram-webhook-challenge.json   | 7 nós de agente/HTTP/webhook/resposta                           | Também sanitizado e inativo                                                                                      |
| structure/03-instagram.json                     | 8 nós, incluindo Sheets                                         | Todos desabilitados; é template, não automação pronta                                                            |
| structure/02-atendimento.json                   | 7 nós: chat, Groq, memória e três ferramentas/subworkflows      | Template desabilitado; não comprova integração com o catálogo PostgreSQL                                         |
| producao/01-caixa-unificada-api-postgresql.json | 8 nós de webhooks/SQL/normalização/respostas                    | Export legado inativo; não promover automaticamente a multi-MEI                                                  |
| Auditoria histórica Publicar post no Instagram  | 40 nós, Form Trigger/binário, hospedagem, Wait e Graph API      | Não é API autenticada do app; conta fixa, status/idempotência e instância precisavam de conferência naquela data |

Os achados históricos de conta fixa, URLs de outro n8n e parâmetros de mídia precisam ser conferidos na versão publicada atual. Não são apresentados como defeitos atuais confirmados no workflow do colega.

## Contrato que falta conferir para conectar o site

- Identificador/versão de cada workflow vivo, responsável e destino de testes aprovado.
- Entrada HTTP suportada, formato de mídia e autenticação específica de serviço. Formulário público não equivale a endpoint interno seguro.
- Vínculo autorizado entre conta externa e workspace; proibir perfil fixo compartilhado para cadastros de outros negócios.
- Operação/job persistido, chave idempotente, confirmação externa/status consultável e quarentena de resultados incertos.
- Eventos recebidos com IDs de conta/contato/conversa/mensagem estáveis; evitar fusão por nome e duplicação de resposta entre n8n e outbox.
- Consulta do catálogo do negócio correto; rotas técnicas de workspace fixo e planilhas legadas não são autorização multi-MEI.
- Segurança dos callbacks/logs, tratamento de revogação, limites de mídia e proprietário do armazenamento.

Enquanto isso, o núcleo API/SQL continua testável. `/api/v1/integrations/readiness` declara revisão n8n pendente e não afirma conhecer a saúde do servidor nem que a ponte esteja conectada. A alternativa Meta opcional permanece desligada. Nenhum endpoint/ID/credencial de workflow real foi inventado.
