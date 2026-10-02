# SocialME

Projeto acadêmico para desenvolver uma solução de atendimento inteligente para microempreendedores individuais (MEIs).

## Tecnologias

- n8n
- PostgreSQL
- Caddy
- Python 3.12
- FastAPI
- Docker
- Docker Compose
- AWS

## Arquitetura

Internet -> Caddy -> n8n -> Python API
                         |
                         -> PostgreSQL

## Python

O serviço Python roda em um container separado.

Endpoints atuais:

- GET /health
- POST /processar

O n8n acessa o Python internamente em:

http://python-api:8000

## Estrutura

- compose.yaml
- compose.override.yaml
- Caddyfile
- backup.sh
- .env.example
- .gitignore
- python-service/

## Segurança

Nunca enviar para o GitHub:

- .env
- arquivos .pem
- senhas
- tokens
- backups
- dumps do PostgreSQL

## Status

- n8n funcionando
- PostgreSQL funcionando
- HTTPS funcionando
- Python funcionando
- comunicação n8n -> Python validada
- backup do PostgreSQL testado por restauração
