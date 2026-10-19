# API experimental de estoque por planilha

Protótipo para aula: recebe mensagens do n8n, consulta uma planilha XLSX e prepara pedidos. Não usa o catálogo PostgreSQL do CRM e não envia mensagens externas. O primeiro teste usa exclusivamente dados fictícios.

A implementação usa o FastAPI existente, sem adicionar outro servidor Flask. `/health` e `/processar` continuam com os contratos anteriores. As novas rotas ficam desativadas por padrão.

## Configuração

Configurar **apenas na API Python legada**, não no serviço `team-api`:

| Variável                         | Valor/uso                                                  |
| -------------------------------- | ---------------------------------------------------------- |
| `SOCIALMEI_SHEET_ORDERS_ENABLED` | `true` para montar as novas rotas                          |
| `PLANILHA`                       | Caminho absoluto do XLSX em diretório persistente gravável |
| `API_KEY`                        | Segredo privado exigido em `X-API-Key`                     |
| `WEB_CONCURRENCY`                | `1`; iniciar o Uvicorn com somente um worker               |

A aplicação recusa a ativação junto com `SOCIALMEI_SHARED_DATA_ENABLED=true` ou `WEB_CONCURRENCY` diferente de `1`. Não existe coordenação entre processos: não usar múltiplos workers, réplicas ou dois serviços editando a mesma planilha. O diretório precisa permitir criação e substituição de arquivos; a confirmação grava um arquivo temporário e faz substituição atômica.

Não versionar XLSX com dados reais ou a chave. Cadastrar a chave privadamente no ambiente e na credencial **Header Auth** do n8n, nunca em campos de texto exportados no workflow ou no Git. Não abrir a porta 8000 publicamente.

## Teste local com dados fictícios

Em um ambiente de desenvolvimento isolado, na pasta `python-service`, instalar `requirements.txt`. Criar uma planilha nova:

```bash
python sheet_orders.py --example estoque_exemplo.xlsx
```

O comando recusa sobrescrever um arquivo existente. O exemplo inclui camisetas, bolsas, canecas e chaveiros. Para conversar pelo terminal, sem HTTP:

```bash
python sheet_orders.py --chat
```

Para HTTP, configurar as variáveis acima por mecanismo privado e iniciar o servidor existente:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
```

Em Docker, o serviço precisa escutar `0.0.0.0` internamente e montar o diretório persistente da planilha. **Não aplicar esses comandos diretamente em produção:** conferir primeiro o Compose efetivo, a imagem, os mounts e as alterações locais. Trocar o código não cria automaticamente uma planilha nem configura persistência.

## Contrato HTTP

- `GET /saude`: `{"status":"ok"}`. Confere o processo, não a integridade da planilha.
- `GET /estoque`: exige `X-API-Key`; retorna `{"produtos":[...]}`.
- `POST /mensagem`: exige `X-API-Key`; recebe mensagem e sessão.

```json
{
  "mensagem": "quero 2 canecas e 1 chaveiro",
  "sessionId": "aula-cliente-1"
}
```

Também aceita `chatInput` no lugar de `mensagem` e `sessao` no lugar de `sessionId`. A sessão é obrigatória; usar um identificador estável e distinto por conversa. A mensagem aceita até 2.000 caracteres e a sessão, até 128.

```json
{
  "resposta": "Seu pedido:\n- 2x Caneca personalizada\n- 1x Chaveiro\nTotal: R$ 59,70\n\nResponda *CONFIRMAR* para fechar ou *CANCELAR*.",
  "alerta_estoque": null,
  "pedido_pendente": true
}
```

Mandar `CONFIRMAR` com o **mesmo** `sessionId` efetiva a baixa e acrescenta linhas à aba `Pedidos`. `CANCELAR` descarta o pedido. `estoque` consulta a situação. Uma frase como `não confirmar` não confirma nada: a API pede um comando explícito.

Erros de autenticação retornam 401; chave não configurada ou planilha indisponível, 503; corpo inválido ou sessão ausente, 422. O campo de erro segue o contrato FastAPI `detail`. Erros de planilha não revelam caminhos internos.

## Nó HTTP Request do n8n

Quando n8n e `python-api` estiverem na mesma rede Docker, **após publicar e habilitar a funcionalidade**:

1. Método `POST`; URL `http://python-api:8000/mensagem`.
2. Autenticação **Generic Credential Type → Header Auth**, nome `X-API-Key`, valor cadastrado privadamente.
3. Enviar corpo, tipo JSON. No modo de expressão do corpo completo:

```javascript
{{ { mensagem: $json.chatInput, sessionId: $json.sessionId } }}
```

4. Para devolver a resposta ao chat, usar `{{ $json.resposta }}` no mecanismo de resposta escolhido no Chat Trigger. Se o trigger estiver configurado para responder pela saída do último nó, transformar a saída final em `{ "output": $json.resposta }`. Não devolver o objeto inteiro ao cliente.
5. `alerta_estoque` deve seguir somente para um ramo interno autorizado do MEI, sem envio automático nesta etapa. Não ligá-lo à resposta do cliente.

Essas URLs são internas à rede Docker, não links para abrir no navegador do notebook. Não usar `127.0.0.1` no n8n para alcançar outro container. A rota `/processar` continua recebendo `{"texto":"..."}` e não executa o atendimento de estoque.

## Limites do protótipo

- Uma planilha e um negócio por instância, sem separação de empresas ou usuários.
- Estoque e histórico confirmado persistem no XLSX somente se houver volume/diretório persistente. Pedidos pendentes ficam em memória, expiram em 30 minutos e se perdem ao reiniciar.
- Preparar pedido não reserva estoque. A confirmação confere novamente a disponibilidade e não permite baixar além do saldo.
- Confirmação repetida, sem novo pedido, não faz uma segunda baixa. Isso **não** equivale a idempotência de eventos externos ou garantia de entrega: ainda não há identificadores de evento, fila, transação de banco ou recuperação de resposta após falha de rede.
- A interpretação é por regras, sem IA remota. Quantidades são inteiras positivas; nomes ambíguos exigem novo pedido mais específico. Sugestões por semelhança nunca são aceitas automaticamente.
- Preços usam Decimal no cálculo; dados negativos, fórmulas nos valores numéricos, estoque fracionário e nomes duplicados são recusados.
- Não editar o XLSX simultaneamente no Excel ou em outro processo. Fazer backup antes de substituir uma planilha.
- Não homologado para pedidos de clientes reais, WhatsApp ou múltiplos atendentes. O protótipo não altera os workflows existentes.

## Validação

Na raiz, com as dependências Python instaladas:

```bash
python -m unittest discover -s tests -p test_sheet_orders.py -v
```

Os testes criam e removem somente planilhas temporárias. Cobrem autenticação, ativação opcional, contratos anteriores, sessões, confirmação/cancelamento, concorrência, estoque insuficiente, expiração, falha ao salvar e campos inválidos. Não precisam de AWS, n8n ou banco de produção.
