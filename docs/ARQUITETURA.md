# Arquitetura — SocialMEI.IA

## Visão geral

```mermaid
flowchart LR
    U["👤 Usuário / equipe"] --> P["🌐 GitHub Pages<br/>Dashboard"]
    P -->|HTTPS / GET| C["🔐 Caddy"]
    C --> N["⚙️ n8n"]
    N --> DB[("🐘 PostgreSQL")]
    N --> API["🐍 FastAPI"]
    A["🧑‍💻 Equipe autorizada"] -->|HTTPS| PG["🗄️ pgAdmin"]
    PG --> DB
```

## Caixa Unificada — fluxo validado na Sprint 3

```mermaid
sequenceDiagram
    participant O as Origem / teste
    participant N as n8n
    participant DB as PostgreSQL
    participant D as Dashboard

    O->>N: POST mensagem
    N->>N: normaliza payload
    N->>DB: salva cliente, conversa e mensagem
    DB-->>N: registro persistido
    D->>N: GET mensagens
    N->>DB: consulta histórico
    DB-->>N: mensagens
    N-->>D: JSON
    D->>D: renderiza WhatsApp + Instagram
```

## Camadas

| Camada | Tecnologia | Papel |
|---|---|---|
| Interface | HTML, CSS, JavaScript | Dashboard e Caixa Unificada |
| Publicação | GitHub Pages | entrega do frontend |
| Automação | n8n | webhooks e orquestração |
| Dados | PostgreSQL | histórico persistente |
| Administração do banco | pgAdmin | interface web autenticada |
| API auxiliar | FastAPI | serviços Python |
| Proxy / HTTPS | Caddy | roteamento e TLS |
| Infraestrutura | Docker Compose | containers e rede |
| Colaboração | GitHub | código, revisão e documentação |

## Segurança por desenho

- PostgreSQL não publica 5432.
- Caddy é o ponto de entrada HTTPS.
- n8n usa uma role técnica para os dados funcionais.
- credenciais reais ficam fora do GitHub;
- SSH e Docker são concedidos individualmente e sob demanda;
- infraestrutura deve ser reproduzível a partir do repositório.

## Limite atual

A Caixa Unificada já demonstra e persiste mensagens de WhatsApp e Instagram recebidas pelo fluxo do n8n. A integração oficial completa com APIs dos canais, especialmente envio externo de respostas, continua como evolução futura.
