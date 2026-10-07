# Acessos e permissões — SocialMEI.IA

> Objetivo: permitir que a equipe trabalhe no projeto sem depender do computador ou das credenciais pessoais de um único integrante.

## Modelo de acesso

| Recurso | Quem deve acessar | Como | Regra |
|---|---|---|---|
| GitHub | equipe de desenvolvimento | conta individual | branch + Pull Request |
| Dashboard | equipe / demonstração | navegador | público pelo GitHub Pages |
| n8n | integrantes autorizados | conta individual | separar Produção, Testes e Revisar |
| pgAdmin | quem precisa consultar/manter dados | login individual | nunca compartilhar senha |
| PostgreSQL | aplicações e responsáveis pelo banco | roles separadas | porta 5432 não pública |
| VPS / SSH | responsáveis por infraestrutura | usuário Linux + chave própria | acesso sob demanda |
| Docker | responsáveis por infraestrutura | acesso pela VPS | alto privilégio |
| AWS | quem administra infraestrutura | IAM/Identity Center individual | nunca compartilhar root |

## Princípio principal

A equipe não precisa ter o mesmo nível de acesso.

```text
Desenvolvedor comum
├─ GitHub
├─ Dashboard
├─ n8n, se necessário
└─ pgAdmin, se necessário

Responsável de infraestrutura
├─ tudo acima
├─ SSH na VPS
├─ Docker
└─ AWS IAM, se necessário
```

Acesso administrativo deve ser concedido somente quando houver necessidade real.

## Novo acesso à VPS

Cada pessoa usa uma chave SSH própria. Nunca copie a chave privada de outro integrante.

### 1. Criar o usuário

```bash
sudo adduser --disabled-password --gecos "" nomeusuario
```

### 2. A pessoa gera a própria chave

No computador dela:

```powershell
ssh-keygen -t ed25519 -C "nome-socialmei"
```

Ela compartilha somente `id_ed25519.pub`. O arquivo `id_ed25519` sem `.pub` é privado.

### 3. Autorizar a chave pública

```bash
sudo install -d -m 700 -o nomeusuario -g nomeusuario /home/nomeusuario/.ssh
sudo nano /home/nomeusuario/.ssh/authorized_keys
sudo chown nomeusuario:nomeusuario /home/nomeusuario/.ssh/authorized_keys
sudo chmod 600 /home/nomeusuario/.ssh/authorized_keys
```

Cole apenas a chave pública e teste o login antes de conceder privilégios extras.

## Acesso ao Docker

> Entrar no grupo `docker` oferece poder administrativo elevado na VPS.

Somente conceda quando a pessoa realmente precisar operar containers:

```bash
sudo usermod -aG docker nomeusuario
```

Depois ela deve sair e entrar novamente na sessão SSH.

## Banco e pgAdmin

O caminho preferido para pessoas é o pgAdmin via HTTPS:

`https://db.54-94-213-7.sslip.io`

- PostgreSQL continua sem publicar 5432 na internet.
- Crie logins individuais conforme a necessidade.
- Automações usam a role técnica `socialmei_app`.
- Administração estrutural usa uma role separada.
- Senhas nunca entram no GitHub.

## n8n

Acesso web atual:

`https://socialmei.54-94-213-7.sslip.io/home/workflows`

Organização recomendada:

```text
SocialMEI.IA
├── 01 · Produção
├── 02 · Testes
└── 03 · Revisar
```

Teste ideias fora de Produção sempre que possível.

## AWS

Não compartilhe a conta root. Quando alguém precisar administrar a EC2, crie acesso individual pelo AWS IAM / IAM Identity Center e aplique o menor conjunto de permissões necessário.

Quem trabalha apenas em frontend, n8n ou banco não precisa de acesso ao painel AWS.

## Quando alguém quiser instalar um novo programa

A pessoa não precisa ter SSH para preparar a mudança.

```text
ideia → branch GitHub → compose.yaml / arquivos
     → Pull Request → revisão → responsável pela VPS
     → docker compose config → aplica serviço → teste
```

Veja também [DOCKER.md](./DOCKER.md).

## Revogar acesso

Quando alguém não precisar mais de acesso administrativo:

- remova sua chave pública de `authorized_keys`;
- remova acesso ao grupo `docker`, se aplicável;
- desative a conta no n8n/pgAdmin;
- revogue o acesso AWS individual;
- revise tokens vinculados àquela conta.

## Checklist

- [ ] cada pessoa usa uma conta própria;
- [ ] chave privada nunca é enviada por chat ou GitHub;
- [ ] `.env` permanece fora do repositório;
- [ ] Docker fica restrito;
- [ ] PostgreSQL não expõe 5432;
- [ ] AWS root não é compartilhado;
- [ ] mudanças de infraestrutura passam por PR;
- [ ] permissões são removidas quando deixam de ser necessárias.
