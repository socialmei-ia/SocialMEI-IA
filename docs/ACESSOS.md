# Acessos e permissões — SocialMEI.IA

Os endereços deste guia são referências registradas pela equipe; disponibilidade e contas ativas não foram verificadas nesta revisão. O login local do app não concede acesso a n8n, WAHA, banco ou VPS. Veja [DEPLOYMENT.md](../DEPLOYMENT.md) para a configuração atual.

> Objetivo: permitir que a equipe trabalhe no projeto sem depender do computador ou das credenciais pessoais de um único integrante.

## Modelo de acesso

| Recurso        | Quem deve acessar                    | Como                                    | Regra                                                     |
| -------------- | ------------------------------------ | --------------------------------------- | --------------------------------------------------------- |
| GitHub         | equipe de desenvolvimento            | conta individual                        | branch + Pull Request                                     |
| Dashboard      | MEIs/equipe ou demonstração          | conta individual no team; demo no Pages | Basic + sessão no team; Pages não prova acesso ao runtime |
| n8n            | integrantes autorizados              | conta individual                        | separar Produção, Testes e Revisar                        |
| pgAdmin        | quem precisa consultar/manter dados  | login individual                        | nunca compartilhar senha                                  |
| PostgreSQL     | aplicações e responsáveis pelo banco | roles separadas                         | porta 5432 não pública                                    |
| VPS / SSH      | responsáveis por infraestrutura      | usuário Linux + chave própria           | acesso sob demanda                                        |
| Docker         | responsáveis por infraestrutura      | acesso pela VPS                         | alto privilégio                                           |
| AWS            | quem administra infraestrutura       | IAM/Identity Center individual          | nunca compartilhar root                                   |
| WAHA Dashboard | integrantes autorizados do projeto   | HTTPS + login do WAHA                   | não compartilhar a API key                                |
| FastAPI        | desenvolvimento e integração         | HTTPS                                   | proteger endpoints sensíveis antes de produção            |

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
- `socialmei_app` é referência técnica do banco legado/n8n; não aplicar seus grants ao banco team por suposição.
- O perfil de consulta team preparado nesta estabilização está em [TEAM-DATABASE-ACCESS.md](TEAM-DATABASE-ACCESS.md); logins reais e caminho de rede exigem conferência e autorização individual.
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

## WAHA

Acesso web atual:

`https://waha.54-94-213-7.sslip.io/dashboard`

Compartilhe somente o endereço; conceda acesso individual quando suportado pela instalação ou mantenha a operação restrita aos responsáveis. Não distribuir uma credencial administrativa comum como procedimento padrão. A `WAHA_API_KEY` é credencial técnica e deve permanecer no servidor/n8n, nunca no frontend ou em chats da equipe.

## API Python

Acesso web atual:

- `https://api.54-94-213-7.sslip.io/health`
- `https://api.54-94-213-7.sslip.io/docs`

Essas URLs são históricas; disponibilidade e autorização atuais NÃO CONFIRMADAS nesta rodada. A API team é consumida na mesma origem protegida do aplicativo; o gateway não publica Swagger indiscriminadamente.
