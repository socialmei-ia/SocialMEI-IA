# Acesso do projeto aos dois negócios

**Atualização produtiva:** cadastro e vínculo autorizados foram concluídos. Usuário34 administra Brilho/60 e Bella/61, preservando proprietário33. [Estado atual, dry-runs e recibos](PROJECT-ACCESS-PRODUCTION-20261120.md). As seções de preparação abaixo descrevem o estado anterior à execução.

## Estado confirmado em 20/11/2026

- Brilho&Limpeza Service: workspace 60, proprietário 33 preservado.
- O e-mail do projeto ainda não possui usuário no banco efetivo da API. O arquivo privado corresponde ao e-mail do projeto, não ao usuário 33.
- Bella Store não encontrada nesse banco. Referências históricas de Instagram não representam um workspace existente.
- Cadastro normal habilitado; nenhum cadastro, vínculo ou canal foi alterado nesta preparação.

## Operação produtiva proposta — exige aprovação específica

1. Revalidar ausência do cadastro exato e de Bella no banco efetivo. Preservar inventário privado anterior à operação.
2. Cadastrar a conta pelo contrato existente `POST /api/v1/auth/register`, utilizando o arquivo privado exclusivamente em memória. Se o resultado for incerto, reconciliar por consulta antes de repetir.
3. Utilizar o workspace criado pelo cadastro como Bella Store através de `/auth/profile`; não criar workspace adicional por conveniência. Registrar os IDs retornados.
4. Inspecionar `workspace_access.py` com identidade exata, administrador ativo 1, workspace 60 e conjunto de proprietários `[33]`. Revisar o hash do plano.
5. Conceder somente `owner` nesse workspace, com UUID da operação e recibo privado durável. Preservar o proprietário 33, credenciais e privilégios globais.
6. Validar `/auth/workspaces`, troca, leitura de perfil e autorização dos dois negócios. Nenhum canal ou dado demonstrativo incluído nessa operação.

O módulo privado não adiciona rota HTTP. Usa transação, bloqueios, auditoria existente e plano com estado esperado; divergências interrompem a concessão. O CLI é somente leitura por padrão. `--apply` exige `--approved-plan`, `--grant-id` e `--receipt`. Arquivos de requisição contêm identidade e devem permanecer fora do Git, em diretório privado.

## Reversão

`--rollback-receipt` sem `--apply` produz o plano de remoção apenas do vínculo introduzido. A remoção exige aprovação do novo hash, identidade preservada e auditoria íntegra; revoga sessões/preferências dependentes desse vínculo. Não remove o proprietário 33, contas, históricos ou registros comerciais. Em resultado incerto, reconciliar o UUID e o recibo antes de tentar novamente.

O cadastro novo e Bella permanecem identificáveis e sem dados/canais. Desativação ou remoção posterior requer decisão específica; não apagar automaticamente a conta como rollback.

## Integração do frontend

O frontend existente usa `/auth/workspaces` e `/auth/workspaces/switch`. A sessão autenticada define o workspace e o backend valida a associação; o cliente não escolhe livremente `workspace_id`. Não é necessário substituir a autenticação nem falsificar proprietário no provisionador. Atualizar os manifestos somente após conhecer os IDs reais e comprovar `owner` para a conta autorizada.

## Evidência local

`test_workspace_access`: 12 testes aprovados em PostgreSQL 17 descartável, incluindo concessão e repetição, duas empresas por login, IDs cruzados, rollback, conta inativa/sem credencial, mudança do plano e falha de gravação do recibo. A CI exige opt-in e banco descartável para repetir esses testes. Nenhuma migration ou escrita produtiva.
