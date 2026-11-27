# Produção AWS — Missão 07

## Lista para testar no site

- Na Agenda, selecione um período vazio e clique em **Consultar agenda**. A lista deve exibir o estado vazio. Ao registrar um lembrete autorizado, o formulário oferece recuperação da mesma operação se perder a resposta.
- Em Negócio, entre com uma conta conectada. Os cartões demonstrativos de faturamento e DAS devem ficar ocultos.

## Publicação de 27/11/2026

A etapa publicada aplica somente três arquivos de Agenda e Negócio, derivados de `024516b4bb8f932041d0f6029040bf84f138b44d`. O Compose recriou apenas `team-gateway`. API, banco, workers e canais permaneceram ativos na configuração anterior.

- Imagem ativa `sha256:fb6f827912e370e67c4df4481699b86b5ef8dabd7df06cab769cd182ab26c1cc`
- Imagem de reversão `sha256:32b2a9a17da444a2511e956b7f23fdc6490d5f27bb4f4113777dbc6831d88eda`
- SHA-256 do plano congelado `21caa80c303f0cb3729c8613b00b3919bdcec34a506c5383f0c43a3b57d4605a`
- Backup consistente anterior à etapa `sha256:2c7321074798108f5ccff9ccf29b3b3ba9cf90946019f0f296dcf9b0f285385e`. Restauração isolada com contagens iguais nas 82 tabelas.
- HTTPS devolveu os três hashes previstos. A sessão real acessou Brilho60 e Bella61. A leitura de Agenda respondeu HTTP 200 em ambas.
- Migrations aplicadas em produção nesta etapa: nenhuma. As migrations 042–047 passaram na restauração isolada do backup 041, com as permissões de aplicação verificadas para as novas tabelas.

A reversão da etapa publicada recompõe os arquivos que já estavam efetivos no gateway. O comando abaixo usa o material privado congelado e valida a identidade dos serviços antes de recriar somente o gateway. Use o SSH autorizado para executar no servidor.

```sh
release=/var/lib/socialmei/production-consolidation-m07/preflight-bfvgu3zz/gateway-stage1
sudo -n python3 "$release/publish-r2.py" rollback "$release" \
  --plan-sha256 21caa80c303f0cb3729c8613b00b3919bdcec34a506c5383f0c43a3b57d4605a
```

## Preparação do corte principal

A rotina automática que usa a base da API ficou no perfil 040 após o banco atingir 041. O backup pontual verificado cobriu a primeira etapa. O corte principal exigiu alinhar a rotina automática, fixar o plano da API e do gateway e autorizar 042–046. A candidata preserva os cinco arquivos privados da API por binds somente leitura e mantém o alias `socialmei-ig-api`. As migrations são mantidas durante rollback da aplicação. A 047 e as ativações de mídia ficam para uma etapa própria após a homologação real necessária.

O ensaio integrado percorreu a dupla anterior, a candidata e a reversão sobre um PostgreSQL 17 descartável com a estrutura até 046. A API respondeu por HTTP, consultou o banco e manteve cinco redes, o alias privado do Instagram e sete mounts equivalentes. O gateway serviu o app nos três estados. O ensaio usou credenciais sintéticas e redes internas.

As imagens e composições da etapa seguinte já estão congeladas na AWS. O plano privado `core-release-046.private.json` registra o hash `94c52c116bae9de5a6db1711a66b73dfd3800fb94547b71da2e8277e85dd3be7`. Ele fixa o SQL, o backup e os dois pares de Compose. O SQL rejeitou banco incorreto e reaplicação em laboratório. A reversão mantém a etapa de Agenda e Negócio já publicada.

Os testes do backup em Linux passaram. Os helpers de exportação e recuperação também foram homologados com backups sintéticos completos nos perfis 046 e 047. O ciclo automático passou na 041 antes do corte. Em 046, o exportador produziu o dump e a primeira verificação de retenção identificou que o novo perfil precisava ser reconhecido. A execução retomou após a correção da retenção, sem reaplicar migrations. O timer histórico e os dumps existentes foram preservados.

## Corte principal publicado

O plano `94c52c116bae9de5a6db1711a66b73dfd3800fb94547b71da2e8277e85dd3be7` foi executado. A transação aplicou 042–046 à base produtiva. O Compose recriou exclusivamente `team-api` e `team-gateway`, com preservação dos mounts privados e do alias do Instagram. A 047 ficou fora do ledger. Os flags novos de mídia permanecem desligados.

- API ativa `sha256:1f998d8099b19f3cc2f525c093f24a55fd71c896d26bd7a23de76ef249ae72e2`
- Gateway ativo `sha256:3921e407de7a8cba97896062048114a2c9e38a9560fe46a97a58f28a4ec8a8dc`
- Backup automático na 046 `sha256:5edef0fab908e99835c29252c13c8e39c033403ab08656c47b079c11eb433d38`. Timer ativo e dump restaurado em PostgreSQL 17 isolado, com comparação de conteúdo nas 83 tabelas.
- O exportador usa a identidade administrativa do contêiner PostgreSQL aprovado sem ampliar grants da API. A tarefa de retenção é somente de inventário e não apagou dumps. A rotina histórica foi preservada.
- API saudável, conexão ao banco produtivo, HTTPS e identidade dos cinco arquivos da candidata confirmados. WAHA, menu WhatsApp, worker Instagram e n8n continuaram nos mesmos contêineres. O journal WhatsApp estava ativo e sem operação em andamento. A validação não enviou mensagens.

- O navegador autenticado abriu as listas de ocultas e arquivadas nos workspaces 60 e 61. O login, a troca de empresa, a leitura de Agenda e as consultas de respostas rápidas responderam. Os IDs retornados nas listas da Caixa ficaram separados por workspace.

### Checklist da Caixa

- [ ] Abrir uma conversa e alternar **Marcar como lida** e **Marcar como não lida**. Conferir o indicador e a lista **Não lidas**.
- [ ] Usar **Selecionar conversas**, arquivar, abrir **Conversas arquivadas** e desarquivar.
- [ ] Ocultar uma conversa de teste e recuperá-la em **Conversas ocultas**.
- [ ] Fixar, desafixar, adiar e reativar um atendimento. Conferir o estado após recarregar.
- [ ] Adicionar uma resposta rápida do negócio e inseri-la no rascunho. Conferir o seletor nas duas empresas.
- [ ] Pausar e retomar a automação em uma conversa de teste com o canal e o papel habilitados.
- [ ] Consultar a Agenda e conferir a ausência dos cartões demonstrativos em Negócio após trocar de empresa.

Para reverter o corte principal, use o comando abaixo no servidor. Ele retorna à API anterior e à etapa de Agenda e Negócio, preservando o ledger 046 e os registros produzidos.

```sh
release=/var/lib/socialmei/production-consolidation-m07/preflight-bfvgu3zz
sudo -n python3 "$release/publish-core046.py" rollback \
  --approved-plan 94c52c116bae9de5a6db1711a66b73dfd3800fb94547b71da2e8277e85dd3be7
```
