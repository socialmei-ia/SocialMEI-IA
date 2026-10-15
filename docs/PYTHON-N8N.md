# Python e n8n: padrão de execução

Decisão de 15/10/2026. Lógica reutilizável do produto roda na API Python versionada; n8n orquestra por HTTP. Transformações pequenas sem dependências podem permanecer em JavaScript no n8n. Um Code node Python é outro mecanismo e exige seu próprio executor.

## O que aconteceu

| Evidência                                                                                                        | Conclusão                                                                                                                |
| ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Responsável executou `n8n --version` na AWS: `2.40.5`; imagem referenciada como `docker.n8n.io/n8nio/n8n:latest` | Versão observada naquela coleta; tag flutuante não identifica uma versão permanentemente                                 |
| n8n em `socialmei_default`, volume `socialmei_n8n_data`; API `socialmei-python` separada                         | Python instalado na API ou no notebook não fornece um executor ao Code node                                              |
| Relato de Python indisponível no nó de código                                                                    | Compatível com falta de executor/configuração; mensagem exata, tipo/versão do nó e execução original **NÃO CONFIRMADOS** |
| Foto do HTTP POST em `http://python-api:8000/processar` retornando “Campo obrigatório”                           | O serviço foi alcançado; houve erro de contrato, não falta de Python. O contrato exige `texto`                           |
| PR #44 aberto, executor externo 2.40.5; backups preparados pelo responsável                                      | Preparação não comprova aplicação, registro do runner ou execução de nó Python                                           |
| PR #45 aberto, API de pedidos em planilha                                                                        | `/mensagem`, `/estoque` e `/saude` não estão na baseline `db775dc`; não publicar essas URLs como disponíveis             |

Esta rodada testa localmente o contrato HTTP e prepara reprodução. Não houve conexão SSH, acesso ao editor n8n nem chamada a workflow vivo. A resolução ponta a ponta na AWS está **BLOQUEADA pela conferência/execução autorizada no servidor**.

## Comparação das opções

| Opção                         | Usar quando                                                     | Decisão                                                                                                                                      |
| ----------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| JavaScript no Code node       | Mapear campos, validar envelope e transformar texto simples     | Adequado; não duplicar regra comercial da API                                                                                                |
| Runner Python oficial externo | Exercícios/código Python que realmente precisam do Code node    | Opcional; exige versão compatível e teste real do nó. Revisar o [PR #44](https://github.com/socialmei-ia/SocialMEI-IA/pull/44) separadamente |
| Imagem n8n customizada        | Dependência sem alternativa suportada, justificada e homologada | Não necessária para `/processar`; instalar Python sozinho não configura task runner                                                          |
| API Python por HTTP           | Estoque, pedidos e lógica de domínio com dependências e testes  | Padrão escolhido para o produto; aproveitar FastAPI existente                                                                                |
| Worker Python novo            | Trabalho assíncrono/demorado com fila e retries definidos       | Adiar; não existe requisito que justifique outra infraestrutura                                                                              |

## Primeiro teste, sem planilha ou clientes reais

No n8n ligado à mesma rede Docker da API auxiliar:

1. Importe `n8n-workflows/examples/process-text.json` em área de teste, sem ativação.
2. Confira o nó **Process text in Python API**: POST, `http://python-api:8000/processar`, JSON e timeout de 15 segundos.
3. Execute manualmente. Corpo e resposta esperada:

```json
{ "texto": "Ola SocialME" }
```

```json
{
  "original": "Ola SocialME",
  "maiusculo": "OLA SOCIALME",
  "quantidade_caracteres": 12
}
```

O teste automatizado calcula o comprimento a partir do payload, além de conferir a resposta HTTP do export versionado.

No chat do n8n, o corpo pode ser uma expressão que devolve um objeto:

```javascript
{{ { texto: $json.chatInput } }}
```

`python-api` é DNS interno do Compose, não endereço para o navegador. `127.0.0.1` dentro do n8n identifica o próprio container. A API `team-api` tem outra rede/finalidade e não deve ser ligada ao n8n apenas para contornar um erro de URL. Não abrir porta pública ou encaminhar credenciais team ao exemplo.

O exemplo `/processar` não executa código enviado pelo usuário: executa uma função fixa da aplicação. Não criar endpoint de `eval`/`exec`, comando arbitrário ou upload de scripts.

## Dependências e entrega

Pacotes diretos em `python-service/requirements.txt`; versões transitivas em `requirements.lock`. O constraint file é lido pela instalação normal. Dockerfile copia os dois e roda `pip check`. São versões do ambiente de testes, não uma coleta de pacotes da AWS; a troca de imagem requer validação e autorização próprias.

Para uma dependência nova: explicar finalidade/serviço, atualizar os dois arquivos em Python 3.12 limpo, instalar, rodar `pip check`, testes da regra/HTTP/SQL e CI; construir imagem pelo SHA e publicar só o serviço aprovado. Nunca usar `pip install` dentro do container vivo como solução permanente. Bibliotecas nativas podem exigir pacote de sistema no Dockerfile; documentar o motivo. Imagens base ainda usam tags não imutáveis: digest/homologação permanece pendente.

## Conferência de runtime

`tools/runtime-inventory.py --root CAMINHO_DO_CHECKOUT` lê SHA, limpeza do Git, imagem/ID, running, health, redes, volumes nomeados, versão n8n e presença das rotas auxiliares. Não lê `.env`, não imprime `docker inspect` bruto, não mostra logs, não chama workflows e não escreve arquivos. Interrompe se o checkout estiver sujo. Não confundir seu resultado no ambiente de testes deste chat com AWS.

Depois de conferir a AWS, registrar: versão n8n, imagem por digest, tipo e versão do nó, horário/resultado da execução fictícia e versão do export. Só uma execução efetiva confirma o caminho n8n → API. Runner em execução não comprova Code node funcionando. Nunca reenviar backups, payloads de clientes ou credenciais no chat.

Referências técnicas: [task runners n8n](https://docs.n8n.io/hosting/configuration/task-runners/), [Code node](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.code/), [HTTP Request](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/). São referências de contrato; a disponibilidade de opções depende da versão instalada.
