# Mike DevHub

O **Mike DevHub** é uma ferramenta pessoal de apoio técnico criada para reduzir a dependência de memória, mensagens antigas e instruções espalhadas durante o desenvolvimento do SocialMEI.IA.

Ele não substitui GitHub, n8n, PostgreSQL, Docker ou AWS. A proposta é funcionar como um **painel operacional de consulta rápida**: o usuário descreve o que quer fazer e recebe links, comandos e receitas passo a passo.

## Proposta

Problemas comuns durante o projeto:

- "Como eu entro na VPS?"
- "Como eu instalo Python no servidor?"
- "Como adiciono um dado no banco?"
- "Como crio uma tabela ou coluna?"
- "Como vejo se a VPS está atualizada com o GitHub?"
- "O n8n caiu; por onde começo?"
- "Como atualizo uma imagem Docker?"
- "Como descubro se o servidor está sem memória ou disco?"

O DevHub centraliza essas respostas em um único HTML portátil.

## Acesso

- **GitHub Pages:** https://socialmei-ia.github.io/SocialMEI-IA/tools/mike-devhub.html
- **Arquivo versionado:** `tools/mike-devhub.html`

O arquivo também pode ser baixado e aberto localmente no navegador.

## O que existe na versão atual

A versão atual reúne:

- **121 comandos**
- **32 receitas guiadas**
- **33 links rápidos**
- busca por intenção em linguagem natural;
- Command Constellation na Home;
- sidebar no estilo **Command Rail**;
- grupos recolhíveis e modo compacto;
- favoritos, fixados e recentes;
- atalhos de teclado;
- temas claro e escuro;
- modo pessoal e compartilhável;
- configurações locais em `localStorage`;
- avisos de risco antes de comandos que alteram servidor, banco ou arquivos;
- ajuda contextual indicando onde e quando executar cada comando.

## Exemplos de perguntas

A busca aceita frases como:

```text
como acessar a vps?
como instalar python no servidor?
como adicionar dado no banco?
como criar tabela no banco?
como adicionar uma coluna?
servidor ta lento
n8n caiu
como saber se a vps ta igual ao github?
como atualizar as imagens docker?
```

Quando existe uma rotina completa, a busca prioriza uma **receita** em vez de apenas exibir um comando isolado.

## Áreas cobertas

| Área | Exemplos |
| --- | --- |
| PowerShell | clone, navegação local, servidor HTTP, ferramentas |
| SSH | acesso à VPS, chave PEM, permissões |
| Git/GitHub | status, branch, commit, push, pull, remote e histórico |
| Linux/VPS | disco, memória, uptime, arquivos e pacotes |
| Docker | containers, logs, inspect, stats e diagnóstico |
| Docker Compose | validação, pull, up, restart e serviços |
| n8n | abertura, logs, restart, workflows e testes |
| PostgreSQL | psql, tabelas, schema, INSERT, migrations, backup/restore |
| Python/FastAPI | instalação, venv, dependências, API e healthcheck |
| Caddy | validação, reload e logs |
| Deploy | comparação com origin/main e atualização controlada |
| Dashboard | publicação, comparação e teste HTTP |
| AWS | EC2, IP, Security Group e acesso ao servidor |

## Segurança

O DevHub **não armazena senhas, tokens, conteúdo de chaves privadas ou valores de `.env`**.

Comandos sensíveis são classificados com avisos. Alterações de infraestrutura, banco ou arquivos devem continuar seguindo o fluxo da equipe:

```text
branch -> Pull Request -> revisão -> aplicação por responsável autorizado
```

O DevHub também não executa comandos remotamente e não deve ser interpretado como monitoramento real. Indicadores como **READY** significam apenas que a interface carregou.

## Relação com a Sprint 3 / US-018

A US-018 teve como foco a conexão do Dashboard aos webhooks, persistência PostgreSQL e visualização de conversas em uma tela única.

O Mike DevHub entra como **ferramenta complementar de continuidade e colaboração**. Ele documenta de forma interativa como operar e manter as peças usadas na Sprint 3: VPS, Docker, n8n, PostgreSQL, pgAdmin, GitHub e deploy.

Isso ajuda novos integrantes a reproduzir tarefas comuns sem depender de uma única pessoa para lembrar comandos ou explicar o ambiente manualmente.

## Links do projeto

- Dashboard: https://socialmei-ia.github.io/SocialMEI-IA/
- GitHub: https://github.com/socialmei-ia/SocialMEI-IA
- n8n: https://socialmei.54-94-213-7.sslip.io/home/workflows
- pgAdmin: https://db.54-94-213-7.sslip.io
- Workflow PostgreSQL: https://github.com/socialmei-ia/SocialMEI-IA/blob/main/n8n-workflows/producao/01-caixa-unificada-api-postgresql.json

> Credenciais não são documentadas neste arquivo.
