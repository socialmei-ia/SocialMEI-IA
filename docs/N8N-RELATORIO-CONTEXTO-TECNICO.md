# Relatório agregado do SocialMei-ia para o n8n

## O que já funciona no código

O n8n tem um contrato **somente leitura** para obter o resumo real do workspace da equipe:

`GET /api/v1/integracoes/relatorio?days=30`

Autenticação: `Authorization: Bearer <SOCIALMEI_N8N_READ_TOKEN>`, configurado exclusivamente no servidor/cofre n8n. A API exige `SOCIALMEI_SHARED_DATA_ENABLED=true`, `SOCIALMEI_WORKSPACE_SLUG=team` e um token técnico com pelo menos 32 caracteres. O token nunca deve ficar no frontend, em nós de workflow exportados ou em capturas de tela.

Parâmetro `days`: inteiro de 1 a 366, padrão 30. A resposta contém somente agregações do negócio `team`:

- `workspace: "team"` e `acesso: "leitura"`;
- `period_days`, `as_of`;
- `totals`: contagem de clientes, produtos ativos e estoque baixo;
- `sales_by_status`: quantidade e valor de vendas por situação;
- `finance_by_type_and_status`: quantidade e valor de lançamentos por tipo/situação;
- `attendance`: contagens por canal e origem, quando houver dados de mensagens.

Os valores monetários vêm como strings decimais. A rota não retorna nomes, telefones, textos de conversas, fotos, e-mails, senhas nem dados de outro workspace. `Cache-Control: no-store` impede cache compartilhado. Todas as consultas são parametrizadas e realizadas numa transação read-only com fuso horário do negócio.

### Exemplo de contrato de resposta (dados fictícios, não comprovam produção)

```json
{
  "workspace": "team",
  "acesso": "leitura",
  "period_days": 30,
  "as_of": "2026-11-01",
  "totals": {"clientes": 3, "itens_ativos": 2, "estoque_baixo": 0},
  "sales_by_status": {"Pago": {"quantidade": 1, "valor": "50.00"}},
  "finance_by_type_and_status": [],
  "attendance": [],
  "attendance_description": "Mensagens recebidas persistidas por canal e origem. Dados de laboratório não comprovam tráfego real; entrega e resolução não são medidas.",
  "description": "Vendas por data de venda; lançamentos por vencimento, sem duplicar saldos."
}
```

## Como adaptar o workflow já feito pelo colega

1. **Faça um export/backup privado do workflow original antes de editar.** Não o ative enquanto os passos seguintes não forem validados.
2. Remova do caminho de geração as consultas SQL legadas e substitua por um nó **HTTP Request** ao endpoint interno acima, usando a credencial técnica existente no cofre do n8n; nunca passe `workspace_id` enviado pelo navegador.
3. Converta os campos agregados para o modelo de texto, gráfico ou documento esperado pelo workflow. Não presuma que `attendance` é sempre uma lista: pode ser `null` se a tabela não existir no ambiente.
4. Antes de liberar entrega externa, separe a **geração do relatório para download** de qualquer nó de **envio de e-mail ou WhatsApp**. Mantenha estes últimos desativados até uma autorização explícita, destinos revisados e política de privacidade.
5. Teste com o MEI fictício e outra empresa em banco descartável: os dados da segunda empresa não podem aparecer. Verifique também token inválido, período fora do intervalo e rota GET sem escrita.
6. Depois de aprovada a release e feita a configuração de rede e credenciais, teste o fluxo publicado sem envios externos. Só então conecte um botão do dashboard ao disparo autenticado da automação.

## Limitação deliberada

Esta rota de integração acessa **apenas o workspace `team`**, seguindo o contrato técnico já existente. Ela não é uma autorização geral para o n8n consultar qualquer MEI. Para produtos multiempresa, é necessário desenhar consentimento, autenticação de cada empresa e um contrato específico, sem confiar em IDs fornecidos pelo cliente.

O dashboard já gera CSV e oferece impressão/PDF dos dados da sessão pelo endpoint `/api/v1/reporting/overview`. Este novo endpoint **não ativa o workflow**, **não envia relatórios** e **não implanta nada na AWS**. A integração operacional continuará pendente até o fluxo n8n existente ser corrigido e homologado.
