# Staging — SocialMEI.IA

**Proposta, não inventário de ambiente instalado.** O workflow existe no Git, mas host, banco, volumes, GitHub Environment, secrets e execução remota de staging são **NÃO CONFIRMADOS**. O piloto team já existe e é outro alvo; consulte [ENVIRONMENTS.md](ENVIRONMENTS.md). Os passos abaixo só se aplicam após definição/autorização da infraestrutura própria de staging.

O objetivo do staging é permitir testes compartilhados antes de qualquer mudança chegar à produção.

## Regra principal

Staging não deve compartilhar com produção:

- banco PostgreSQL;
- volumes Docker;
- credenciais;
- chave de criptografia do n8n;
- sessão WAHA;
- domínio/subdomínio;
- arquivo `.env`.

## Recomendação para a fase atual

A opção mais simples e segura é um host separado da produção.

```text
GitHub
  ├─ GitHub Pages -> demonstração pública
  ├─ staging host -> testes da equipe
  └─ production EC2 -> serviços reais atuais
```

O Compose de produção atual usa portas 80/443 e nomes explícitos de containers. Por isso, rodar staging no mesmo host agora aumentaria bastante a complexidade e o risco de conflito.

Para o projeto escolar, um segundo host pequeno é tecnicamente mais simples de entender e manter.

## Environment no GitHub

Crie em:

**Settings → Environments → New environment → staging**

Cadastre os mesmos nomes de secrets usados em produção, porém com valores exclusivos de staging:

| Secret               | Valor                              |
| -------------------- | ---------------------------------- |
| `DEPLOY_HOST`        | host/IP do staging                 |
| `DEPLOY_USER`        | usuário Linux de deploy            |
| `DEPLOY_PATH`        | diretório do projeto no staging    |
| `DEPLOY_SSH_KEY`     | chave privada exclusiva do staging |
| `DEPLOY_KNOWN_HOSTS` | host key validada do staging       |

Nunca reutilize a chave privada da produção.

## Preparar o servidor

No host de staging:

1. instale Git, Docker Engine e Docker Compose;
2. crie um usuário de deploy dedicado;
3. clone o repositório no diretório definido em `DEPLOY_PATH`;
4. crie o `.env` de staging fora do Git;
5. use domínios/subdomínios exclusivos;
6. valide `docker compose config --quiet`;
7. suba a pilha e teste antes de ligar qualquer canal externo.

## Banco

Staging deve ter PostgreSQL próprio.

As migrations podem ser testadas primeiro no ambiente local de cada desenvolvedor. Depois de revisadas, a aplicação em staging deve ser controlada.

Neste momento, o executor `npm run db:migrate` foi feito apenas para o Compose local. Não use esse comando diretamente na produção.

## WAHA

O mais seguro inicialmente é deixar WAHA desabilitado no staging, ou usar uma sessão de teste separada.

Nunca reutilize a sessão real de WhatsApp da produção em staging.

## Como publicar

Depois de configurar o environment:

**Actions → Manual staging deploy → Run workflow**

Selecione `main` e digite:

```text
STAGING
```

O workflow atualiza o checkout do staging com `git pull --ff-only`, valida o Compose e sobe os serviços.

## Evolução futura

Quando staging estiver estável:

```text
Pull Request
  -> CI
  -> merge main
  -> staging automático
  -> smoke tests
  -> aprovação
  -> produção manual
```

Produção deve continuar exigindo aprovação humana até a equipe ter confiança no processo.
