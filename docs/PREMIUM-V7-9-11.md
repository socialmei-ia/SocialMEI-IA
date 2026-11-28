# Premium v7.9.11

O pacote original tem SHA-256 `463daca04427c86ffa90c02eb7905d8a268de8d29d8c53e6fd369f75ad840929`. O manifesto em `deploy/premium-v7911/schema046-manifest.json` identifica os 133 recursos integrados para o gateway atual.

```powershell
python tools/build-premium-v7911.py <diretorio-novo> --profile schema046
```

A versão integra as telas do ZIP, com o código nativo e o CSS base externalizados. Os controladores mantêm a configuração real da API e os contratos de sessão, Caixa, Agenda e relatórios. O perfil `schema046` usa as adaptações dos contratos já publicados. O perfil `candidate` e o build de gateway com `--gateway-fixes` incorporam os módulos da 8.0, sujeitos aos respectivos gates.

O gateway monta o diretório da release somente para leitura e mantém o mount do `config.js` efetivo. O mount avulso do script da Caixa sai do Compose da candidata porque o mesmo contrato já está incorporado ao diretório integrado. A publicação recria somente `team-gateway` com a mesma imagem, redes, configuração Caddy e política de cache.

O driver `tools/publish-premium-v7911.py` valida o manifesto, congela as duas composições e ensaia os mounts em um contêiner sem rede externa. A publicação valida os arquivos servidos por HTTPS, a configuração, a saúde do banco e as identidades dos demais contêineres. O rollback restaura exclusivamente a composição anterior do gateway. O backup privado contém a árvore efetivamente servida e o inventário do contêiner.

A regressão do ZIP e o teste autenticado podem ser executados separadamente. O teste autenticado usa uma conta autorizada e bloqueia escritas comerciais e automações externas. Requer `SOCIALMEI_TEST_ACCOUNT` com o caminho de um arquivo privado e usa `SOCIALMEI_PREMIUM_STAGE` quando deve servir os arquivos locais antes do corte.
