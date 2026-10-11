# Entrada da equipe

Este é o caminho oficial para abrir o SocialMEI em qualquer computador da equipe.

> Importante: containers do Docker são locais. Abrir o Docker Desktop em outro computador **não mostra os containers do notebook de outra pessoa**. Cada computador precisa criar o próprio ambiente local a partir do repositório GitHub.

## O que fica onde

```text
GitHub        -> código-fonte, Docker Compose, migrations e documentação
Seu PC       -> containers e volumes locais de desenvolvimento
AWS/EC2      -> serviços remotos compartilhados da infraestrutura
Navegador    -> alguns dados demonstrativos ainda ficam em localStorage
```

Se um notebook quebrar, o código versionado continua no GitHub. O que não estiver commitado ou o que existir apenas em localStorage/volumes locais precisa de backup próprio.

## 1. Pré-requisitos

Instale no computador:

- Git;
- Node.js 22 ou superior;
- Docker Desktop no Windows/macOS, ou Docker Engine + Compose no Linux;
- uma conta GitHub individual com acesso ao repositório.

Abra o Docker Desktop e espere o Engine ficar ativo antes de continuar.

## 2. Baixar o projeto

No terminal:

```bash
git clone https://github.com/socialmei-ia/SocialMEI-IA.git
cd SocialMEI-IA
npm ci
```

Se o repositório já existir:

```bash
git switch main
git pull --ff-only origin main
npm ci
```

## 3. Conferir se o computador está pronto

```bash
npm run doctor
```

O diagnóstico verifica Git, Node, Docker, Docker Compose, Docker Engine e arquivos essenciais do projeto.

## 4. Criar e subir os containers locais

```bash
npm run setup
npm run dev
npm run status
```

Depois abra:

| Serviço    | Endereço                     |
| ---------- | ---------------------------- |
| Frontend   | http://localhost:5500        |
| n8n        | http://localhost:5678        |
| FastAPI    | http://localhost:8000/health |
| PostgreSQL | localhost:5433               |

O ambiente padrão cria containers locais equivalentes para cada integrante. Eles não são os containers da AWS e não são compartilhados entre computadores.

## 5. Ferramentas opcionais

PgAdmin:

```bash
npm run dev:tools
```

WAHA:

```bash
npm run dev:waha
```

Use WAHA local apenas quando realmente precisar testar WhatsApp.

## 6. Banco local e migrations

```bash
npm run db:status
npm run db:migrate
```

Cada integrante trabalha no próprio PostgreSQL local. Não desenvolva apontando para o banco de produção.

## 7. Trabalhar em uma mudança

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/minha-tarefa
```

Depois:

```bash
git add .
git commit -m "feat: descrever a mudança"
git push -u origin feat/minha-tarefa
```

Abra um Pull Request.

## 8. Comandos úteis

```bash
npm run doctor
npm run status
npm run logs
npm run logs -- postgres
npm run stop
npm run dev:config
```

Não use `docker compose down -v` sem entender o impacto. O `-v` apaga os volumes e os dados locais.

## 9. Por que o Docker de outra pessoa aparece vazio?

Porque o Docker Desktop mostra o Docker Engine **daquele computador**.

Exemplo:

```text
Notebook do Maico
  -> socialmei-dev-postgres
  -> socialmei-dev-n8n
  -> socialmei-dev-python

Computador da escola
  -> vazio até executar npm run dev

Notebook de outro integrante
  -> vazio até executar npm run dev
```

Isso é comportamento normal.

O objetivo do `compose.dev.yaml` é justamente permitir que todos recriem o mesmo ambiente a partir do GitHub.

## 10. O que é compartilhado pela equipe

O código deve estar no GitHub. Serviços que precisam ser compartilhados por navegador devem ficar em um ambiente remoto, como staging/AWS.

Não tente usar Docker Desktop como mecanismo de sincronização entre computadores.

A arquitetura desejada é:

```text
                  GitHub
                    |
        +-----------+-----------+
        |                       |
  ambiente local           ambiente remoto
 de cada integrante       staging / produção
        |                       |
 Docker no próprio PC         AWS/EC2
```

## 11. Atenção aos dados do frontend

Clientes, vendas, financeiro, catálogo e outras partes do app ainda usam `localStorage` em vários fluxos. Isso significa que esses registros podem existir somente naquele navegador.

Para não depender de um computador específico, a próxima evolução funcional é persistir esses módulos por API/PostgreSQL e manter backup/exportação enquanto a migração não estiver pronta.

## 12. Acessos administrativos

Não é necessário SSH/AWS para desenvolver normalmente.

Acesso a AWS, VPS, banco remoto, n8n remoto e WAHA deve ser individual e concedido apenas para quem precisar. Veja [ACESSOS.md](ACESSOS.md).

Nunca compartilhe:

- senha;
- chave privada SSH;
- token;
- API key;
- arquivo `.env`;
- credencial de banco.
