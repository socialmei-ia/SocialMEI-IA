<div align="center">

# SocialMEI.IA

### Gestão e atendimento inteligente para MEIs

**Dashboard web + Caixa Unificada + automações com n8n**

[![Status](https://img.shields.io/badge/status-em%20desenvolvimento-1E73D8)](#status-do-projeto)
[![Frontend](https://img.shields.io/badge/frontend-HTML%20%7C%20CSS%20%7C%20JS-F2B11B)](./frontend/socialmei-dashboard.html)
[![n8n](https://img.shields.io/badge/automa%C3%A7%C3%A3o-n8n-EA4B71)](./n8n-workflows)
[![Docker](https://img.shields.io/badge/infra-Docker-2496ED)](./compose.yaml)

</div>

---

## Acesso rápido

| Quero... | Abrir |
|---|---|
| Ver o dashboard atual | [`index.html`](./index.html) |
| Trabalhar no frontend | [`frontend/socialmei-dashboard.html`](./frontend/socialmei-dashboard.html) |
| Ver os workflows do n8n | [`n8n-workflows/`](./n8n-workflows) |
| Ver a API Python | [`python-service/`](./python-service) |
| Ver a infraestrutura Docker | [`compose.yaml`](./compose.yaml) |
| Configurar variáveis de ambiente | [`.env.example`](./.env.example) |
| Guia de entrada da equipe | [`docs/ONBOARDING.md`](./docs/ONBOARDING.md) |
| Banco de dados | [`docs/BANCO-DE-DADOS.md`](./docs/BANCO-DE-DADOS.md) |
| Abrir pgAdmin | https://db.54-94-213-7.sslip.io *(login necessário)* |
| Estrutura SQL | [`database/schema.sql`](./database/schema.sql) |

> O arquivo `index.html` é a mesma versão atual do dashboard e deixa o repositório pronto para publicação como site estático pelo GitHub Pages.

## O projeto

O **SocialMEI.IA** é um projeto acadêmico voltado a MEIs e pequenos negócios. A proposta é centralizar gestão, atendimento e automações em uma interface simples, com integração ao n8n.

O dashboard atual já possui identidade visual própria, responsividade, temas configuráveis e uma Caixa Unificada preparada para receber mensagens processadas pelo n8n.

## O que já funciona

- Visão Geral do negócio
- Financeiro
- Vendas
- Clientes
- Produtos e Serviços
- Caixa Unificada
- Relatórios
- Configurações
- temas claro/escuro e personalização visual
- layout responsivo
- recebimento de mensagens pelo n8n
- persistência de clientes, conversas e mensagens no PostgreSQL
- exibição das mensagens recebidas na Caixa Unificada
- infraestrutura com Docker, PostgreSQL, Caddy e FastAPI
- HTTPS no ambiente de desenvolvimento
- backup do PostgreSQL testado

### Caixa Unificada

Fluxo já validado:

```text
Mensagem / requisição de teste
          ↓
         n8n
          ↓
Webhook SocialMEI
          ↓
Endpoint de mensagens
          ↓
Caixa Unificada no dashboard
```

**Importante:** mensagens recebidas pelo n8n entram no dashboard. As respostas digitadas na interface ainda podem funcionar como demonstração local quando não há endpoint real de saída configurado.

## Teste rápido do frontend

Você pode abrir `index.html` diretamente no navegador.

Para uma execução local mais próxima de um site real:

```bash
python -m http.server 5500
```

Depois acesse:

```text
http://localhost:5500
```

<details>
<summary><strong>Como testar a Caixa Unificada</strong></summary>

1. Mantenha o workflow de recebimento do n8n ativo.
2. Abra o dashboard.
3. Entre em **Caixa Unificada**.
4. Execute o workflow de teste ou envie uma requisição para o webhook configurado.
5. Aguarde a sincronização.
6. A nova conversa/mensagem deve aparecer na lista.

</details>

<details>
<summary><strong>Como subir a infraestrutura</strong></summary>

Crie o arquivo `.env` a partir do exemplo:

```bash
cp .env.example .env
```

Preencha as variáveis localmente e execute:

```bash
docker compose up -d
```

Nunca envie o arquivo `.env` real para o repositório.

</details>

## Arquitetura

```text
                    ┌─────────────────┐
                    │   Dashboard     │
                    │ SocialMEI.IA    │
                    └────────┬────────┘
                             │
                             ▼
Internet ──► Caddy ──► n8n ─────────► Python / FastAPI
                       │
                       └─────────────► PostgreSQL
```

## Estrutura do repositório

```text
socialmei/
├── index.html
├── frontend/
│   └── socialmei-dashboard.html
├── n8n-workflows/
├── database/
│   └── schema.sql
├── docs/
│   ├── ONBOARDING.md
│   └── BANCO-DE-DADOS.md
├── python-service/
├── compose.yaml
├── compose.override.yaml
├── Caddyfile
├── backup.sh
├── .env.example
└── README.md
```

## Colaboração

Antes de começar:

```bash
git pull origin main
```

Depois das alterações:

```bash
git status
git add .
git commit -m "Descreva a alteração"
git push origin main
```

Para mudanças maiores, prefira uma branch separada e Pull Request.

<details>
<summary><strong>Convenção simples de commits</strong></summary>

- `feat:` nova funcionalidade
- `fix:` correção
- `ui:` alteração visual
- `docs:` documentação
- `chore:` manutenção

Exemplos:

```text
ui: improve unified inbox
fix: preserve conversation scroll
docs: update project setup
```

</details>

## Segurança

Não envie para o GitHub:

- `.env`
- arquivos `.pem`
- senhas
- tokens
- chaves de API
- credenciais do n8n
- backups
- dumps do PostgreSQL

O arquivo `.env.example` contém apenas valores de exemplo.

## Status do projeto

| Área | Estado |
|---|---|
| Dashboard | ✅ Em desenvolvimento ativo |
| Caixa Unificada | ✅ Protótipo funcional integrado ao n8n |
| n8n | ✅ Online no ambiente atual |
| PostgreSQL | ✅ Funcionando |
| FastAPI | ✅ Funcionando |
| Docker | ✅ Funcionando |
| WhatsApp/Instagram oficiais | 🟡 Integração completa ainda em evolução |
| Persistência das conversas no PostgreSQL | ✅ Implementada na Sprint 3 |

---

<div align="center">

**SocialMEI.IA — CRM autônomo para MEIs**

Projeto acadêmico em evolução.

</div>
