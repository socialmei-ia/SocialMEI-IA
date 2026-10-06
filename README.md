# SocialMEI.IA

Projeto acadêmico para desenvolver uma solução de gestão e atendimento inteligente para microempreendedores individuais (MEIs).

## Estado atual

O projeto já possui uma infraestrutura funcional em Docker e um frontend de demonstração do SocialMEI.IA.

### Frontend

O dashboard atual está em:

`frontend/socialmei-dashboard.html`

Principais áreas disponíveis:

- Visão Geral
- Financeiro
- Vendas
- Clientes
- Produtos e Serviços
- Caixa Unificada
- Relatórios
- Configurações
- tema claro/escuro
- layout responsivo para desktop e mobile

### Caixa Unificada

A Caixa Unificada centraliza conversas de WhatsApp e Instagram em uma única interface.

O fluxo de entrada já foi validado:

```text
Mensagem de teste
      ↓
n8n
      ↓
Webhook SocialMEI
      ↓
Endpoint de mensagens
      ↓
Dashboard / Caixa Unificada
```

As mensagens recebidas pelo n8n aparecem no dashboard.

> Importante: as respostas digitadas no dashboard ainda são uma simulação local. O envio real para WhatsApp/Instagram não está implementado nesta etapa.

## Tecnologias

- HTML
- CSS
- JavaScript
- n8n
- PostgreSQL
- Caddy
- Python 3.12
- FastAPI
- Docker
- Docker Compose
- AWS

## Arquitetura atual

```text
Internet
   ↓
Caddy
   ↓
n8n ─────→ Python API
   │
   └──────→ PostgreSQL

Dashboard
   ↓
Webhook / endpoint n8n
```

## Python

O serviço Python roda em um container separado.

Endpoints atuais:

- `GET /health`
- `POST /processar`

O n8n acessa o Python internamente em:

`http://python-api:8000`

## Estrutura principal

- `compose.yaml`
- `compose.override.yaml`
- `Caddyfile`
- `backup.sh`
- `.env.example`
- `.gitignore`
- `python-service/`
- `n8n-workflows/`
- `frontend/socialmei-dashboard.html`

## Segurança

Nunca enviar para o GitHub:

- `.env`
- arquivos `.pem`
- senhas
- tokens
- credenciais de API
- backups
- dumps do PostgreSQL

## Status

- n8n funcionando
- PostgreSQL funcionando
- HTTPS funcionando
- Python funcionando
- comunicação n8n → Python validada
- backup do PostgreSQL testado por restauração
- webhook da Caixa Unificada validado
- mensagens do n8n aparecendo no dashboard
- frontend SocialMEI.IA V4 adicionado ao repositório
