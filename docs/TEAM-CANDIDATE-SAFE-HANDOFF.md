# Handoff seguro da candidata integrada para AWS — SocialMEI Team

**Estado:** ferramentas de preparação e importação de imagens Docker atualizadas em código. Nenhum acesso à VPS ou n8n foi utilizado aqui. Nenhum merge, deploy, migração real, reinicialização ou envio a clientes foi realizado.

## Objetivo

A candidata das PRs #159–#169 inclui o bot de WhatsApp em modo prévia, controle de recebimento, recuperação por link, renovação de token Instagram e classificação de sentimento inativa. O código pode ser testado antes de publicar no site. O repositório já tem `tools/team-v33-stage.py` e `tools/team-v33-import-images.py`, além de `tools/team-v33-runtime-audit.py`: esta etapa amplia **esses mesmos scripts**, sem inventar outro Compose ou instalador.

### Condições obrigatórias

- Confirmar na PR de integração a **SHA completa** exata, checks verdes (`Repository checks` e construção das imagens `Team v33 candidate images`), revisão da cadeia de PRs e ausência de alterações locais conflitantes. **Não** usar SHA de run antigo nem presumir que uma branch aberta foi publicada na VPS.
- Ter acesso autorizado como operador ao Ubuntu `/home/ubuntu/socialmei-team`, `/home/ubuntu/socialmei-backups`, Docker local, GitHub e aos backups. O checkout ativo pode conter Caddyfile hotfix e arquivos privados; não executar `git reset`, `git clean`, `git stash`, `git pull` no checkout ativo nem `docker compose down` na stack em produção.
- Conferir por leitura o digest atual dos containers, volumes/bind mounts/redes, configurações privadas, `schema_migrations` e backup **restaurado e verificado**. Não exibir conteúdo das variáveis secretas.
- O caminho abaixo apenas **prepara código e verifica/importa imagens locais**. Recriar containers com mounts privados e preservar o gateway/hotfix é **outra etapa**, só após revisão por operador.

## 1. Preparar uma versão imutável sem alterar checkout ativo

Usar a versão revisada do script `tools/team-v33-stage.py` desta mesma candidata (ex.: arquivo obtido do commit exato, não da branch móvel) e o Git remoto já configurado no checkout original. Confirmar o hash local do script antes de usá-lo. O comando é executado **no host Ubuntu**, nunca dentro de um container:

```bash
CANDIDATE_SHA='<SHA_COMPLETA_DE_40_CARACTERES_VALIDADA_NO_CI>'
python3 /tmp/team-v33-stage-reviewed.py --target team --stage \
  --candidate-sha "$CANDIDATE_SHA" \
  --candidate-branch feat/team-release-candidate-stage-20261030
```

O script só aceita branches revisadas, confere que `origin` é o repositório oficial, faz fetch de objetos Git e _refs remotas_, exige que o SHA seja o HEAD remoto exato, verifica que é descendente da release e que `database/migrations/` não divergiu, registra checkout original limpo/sujo **sem revelar caminhos sensíveis** e cria worktree privado `/home/ubuntu/socialmei-backups/team-v33-<12_DIGITOS_SHA>/source` com recibo `stage-receipt.json`.

A indicação `candidate_workflow_ci_verified:false` no recibo é deliberada: o preparador **não consulta o GitHub Actions** e não deve alegar aprovação apenas com base na branch. O operador deve validar os checks por fora, antes de prosseguir.

## 2. Conferir bundle de imagens da mesma SHA

Baixar o artefato ZIP **SocialMEI-Team-<SHA_COMPLETA>** da execução de CI aprovada, usando a UI autenticada do GitHub Actions. Guardar o ZIP apenas em `/home/ubuntu/socialmei-backups/`, com permissões privadas. Não copiar credenciais ou arquivos `.env` para o pacote.

```bash
CANDIDATE_SHA='<SHA_COMPLETA_VALIDADA_NO_CI>'
BUNDLE='/home/ubuntu/socialmei-backups/ci-team-images.zip'
STAGE="/home/ubuntu/socialmei-backups/team-v33-${CANDIDATE_SHA:0:12}/source"
python3 "$STAGE/tools/team-v33-import-images.py" \
  --target team --source-sha "$CANDIDATE_SHA" --bundle "$BUNDLE" --inspect
```

O importador verifica ZIP, `SHA256SUMS`, identidade do manifesto, digest dos arquivos de configuração de Docker, rótulo da revisão para os **dois** serviços API e gateway, fonte Git limpa e `stage-receipt.json` correspondente à mesma SHA. Rejeita ZIP de outra versão, recibo alterado e imagem local adulterada.

Uma importação opcional posterior, **sem tocar containers**, exige trocar apenas `--inspect` por `--apply`, após revisar espaço em disco/RAM e autorizar o operador. Isso executa `docker image load`, **não** altera serviços em execução, dados, gateways, WhatsApp ou Meta.

## 3. Instalação funcional (etapa separada, ainda pendente)

**Não aplicar Compose novo por cima do existente automaticamente.** Antes de liberar a versão do site: conferir o Caddyfile privado, `config.js`, mount de registro WAHA/HMAC, rede de saída Meta, saúde da API, proteção HTTP, variáveis atuais e backups com restauração. Mapear explicitamente os containers antigos e novos, o plano de rollback e a evidência de que apenas API/gateway seriam recriados mantendo bind mounts e redes originais. Se alguma dessas condições falhar, **parar** sem mudar produção.

Após deploy autorizado e verificado: confirmar login/cadastro, tela Integracões, prévia do menu WhatsApp no workspace 1, catálogo real, ingressos HMAC, WhatsApp com bot ainda desligado, Instagram OAuth, Direct e mensagens na Caixa. Não ativar envios/provedores sem fluxo único, destinatário de teste permitido e comprovação de que n8n/WAHA usam versão publicada correta.

## Estado e reversão

- Preparação Git: escreve somente novo worktree em pasta privada e refs remotas de Git, não altera arquivos do checkout ativo.
- `--inspect`: lê código/artefato e metadados locais, não faz importação, deploy, migração ou envio.
- `--apply` de imagens: muda só o estoque de imagens Docker locais, sem recriar containers; imagens anteriores permanecem. A reversão exige simplesmente não implantar a imagem até que um operador aprove.
- Nenhum procedimento desta entrega altera o banco AWS, Meta, n8n, WAHA ou SMTP.
