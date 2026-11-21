# Publicação CRM233 preservando o gateway premium

Publicação autorizada e concluída em20/11/2026, com o mesmo plano do preflight
aprovado. API em17cfd1956416c2d4c8431fec11800f73254bde12; premium preservado.
API/DB200, siteHTTPS200, navegador sem erros e consulta de clientes protegida
por401 sem sessão. Dos171 arquivos do frontend, somente o JS autorizado mudou;
os outros15 contêineres mantiveram IDs, imagens e configurações.
Evidência: `docs/evidence/20261120-crm233-publication.json`.

## Causa e correção preparada

O instalador privado existente renderizava API e gateway com os11 arquivos
Compose da API, depois exigia que esse resultado contivesse o premium atual.
O gateway real usa outra cadeia, com7 arquivos. A condição
`COMPOSE_PREMIUM_DIVERGENTE` impediu a publicação antes da troca dos serviços.
O instalador presente no pacote AWS ainda contém essa lógica antiga.

`tools/prepare-crm233-release.py` obtém a cadeia de cada contêiner pelos labels,
renderiza separadamente, compara o ambiente/mounts/comando/redes/portas/restart,
usuário/segurança/limites com o runtime, e admite somente:

- `team-api`: troca da imagem d4618e8 para17cfd19.
- `team-gateway`: um bind somente leitura de `v22-inbox-customer.js`.

Não troca a imagem premium, configurações, Caddyfile ou demais arquivos do site.
Não há mudança em workers, DB, canal, registry, migrações, permissões ou n8n.
O script só consulta Docker/Compose/health/db; não escreve overlays nem importa
imagens. O SHA do pacote e o recibo/imageID já carregado são conferidos.

## Artefatos existentes confirmados

Pacote `/home/ubuntu/.socialmei-release040-import/crm-17cfd19/` com
`images.zip`, `v22-inbox-customer.js`, `publicar-servidor.py` antigo.
Não baixar/reconstruir/importar novamente.

| Item                        | Identidade                                                              |
| --------------------------- | ----------------------------------------------------------------------- |
| API anterior para rollback  | sha256:4397c7882dbadbc135d95c6cc7893ed3c384ba4c03310670da546f448ddedad5 |
| API publicada               | sha256:6cf2bc60fec3f31e5e0cc24d4e276a7ba43911e94343e1439dce75d84a5673f8 |
| Premium preservado          | sha256:b93aeac93d11ea0e88dd2c44961bc8f13df9bcb928d960b3562563e68b6cc8ec |
| JavaScript candidato        | b50ce7dc0a29c7da8d2d972a31ab252d5cfb90778fc28f0c511d9e0322c87a85        |
| Plano aprovado tecnicamente | 0ef8cf6b6223e0775d7b8011c29caf159ae73a5edc807b3debc13066cb7e051e        |

## Aplicação após aprovação explícita

1. Copiar apenas os dois novos scripts de preparo/publicação para pasta privada
   na AWS, sem substituir o instalador antigo ou qualquer configuração ativa.
2. Rodar `prepare-crm233-release.py --package CAMINHO_DO_PACOTE`; exigir plano
   idêntico. Qualquer divergência exige revisão, sem contornar o bloqueio.
3. Executar `publish-crm233.py --package CAMINHO_DO_PACOTE --approved-plan SHA_DO_PLANO --apply`
   somente sob aprovação operacional desse escopo.
4. Conferir IDs das imagens, readiness200, hash do JS servido e fluxo autenticado
   da Caixa. Testar cadastro e associação com contato autorizado por ação humana;
   não enviar mensagem nem criar cliente produtivo automaticamente como smoke.
5. Conferir que trabalhadores/canais/Caddy/n8n não foram recriados.

O publicador salva inspect e cópias das configurações com permissão0600,
além de baseline Compose totalmente resolvido com imagem antiga fixada por ID.
Recria somente o serviço indicado com `--no-deps --no-build --pull never`.
Não executa migrador. O bind do JS mantém source durável no pacote privado;
essa pasta passa a ser dependência operacional e não pode ser removida.

Rollback usa a configuração congelada, nunca os arquivos de origem mutáveis,
em ordem gateway→API. `rollback.private.json` guarda comandos e IDs esperados.
Falha de rollback informa necessidade de intervenção; não é reportada como
publicação bem-sucedida. Não restaurar banco: esse incremento não altera schema.

Testes puros cobrem mudanças indevidas, drift de tag/rede/recursos, alteração dos
Compose originais durante aplicação e falha de rollback. Não equivalem a deploy
ou homologação real. O backup externo atual ainda precisa de preparação própria;
o backup deste incremento protege configuração e imagens, não substitui DR.

## Resultado operacional de20/11/2026

Backup/rollback congelado em pasta privada `approved-release-20261120T123408Z`
dentro do pacote. Scripts revisados preservados em `reviewed235-ab647b7`.
Nenhuma migration, carga de dados, transferência de canal ou alteração de worker
foi executada. A ação de cadastro/associação está disponível; criação real de
cliente e associação não foram exercitadas, conforme o escopo autorizado.

Workspace60/proprietário33 revalidado somente leitura, nome exato e conta ativa.
O dry-run autenticado aguarda arquivo privado da conta, sem redefinição de senha.
