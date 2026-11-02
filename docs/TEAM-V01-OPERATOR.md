# Operador v0.1: base266 e banco035

Somente API/gateway; não executa migrations nem modifica overlays existentes.
Fonte da aplicação fixada em `baecbe1f7b7d2af0f3edc1f03b097f18ff5cc3ca`.
O commit das ferramentas operacionais é separado da SHA da aplicação.
Não exige merge em main e não incorpora180/181.

## Inspeção

Em uma janela com acesso autorizado, usando os helpers deste mesmo commit:

```sh
sudo python3 tools/team-v01-release.py --source "$SOURCE" --bundle "$BUNDLE"
```

SOURCE é checkout limpo da SHA fixada. BUNDLE é arquivo offline aprovado em
`/home/ubuntu/socialmei-backups`. A inspeção valida fonte/perfil035, recibo e
arquivo Docker/OCI, identidade das imagens já carregadas, runtime266 e modelo
resolvido de cada serviço. Nenhuma imagem é carregada automaticamente.
Como usa temporários e `docker save`, exige margem de disco e memória. Não
reiniciar outros serviços para liberar recursos. Não imprime configurações.

Antes de carregar uma imagem ausente, verificar o bundle com o importador deste
commit, `read_bundle(..., expected_sha=...)`. Só então executar docker load na
janela autorizada e repetir a inspeção. Não usar o execute legado que exige uma
branch antiga de stage, nem falsificar a identidade da branch. A substituição
desse gate é SHA completa fixada + checkout limpo + perfil/migrations imutáveis.

Os contextos API/gateway vêm separadamente dos labels; todas as configurações,
arquivo de ambiente e mounts privados são preservados. Apenas imagem e variável
SOCIALMEI_RELEASE_SHA da API podem mudar. Defaults de ambiente da imagem também
precisam preservar o ambiente efetivo. Egress e aliases privados são obrigatórios.

## Evidência privada de recuperação exigida

O diretório de backup deve ser filho direto de `/var/lib/socialmei-wa-pilot`,
root0700, sem links. Todos os arquivos são root0600. Não versionar seu conteúdo.
O operador NÃO fabrica evidência de restore. A ferramenta/operador de backup
precisa executar e conferir o ensaio antes de produzir estes arquivos:

- `postgres.dump`: custom dump035 fresco, verificado por pg_restore em PG16
  isolado sem rede/portas, sem migrations e com snapshot consistente na origem.
- `images-before.tar`: imagens efetivas266 por tags verificadas e identidade
  Docker/OCI validada; não apenas um arquivo com nomes de tags.
- `private-config.tar`: somente arquivos regulares com bytes/modo/UID/GID reais.
  Configs/arquivo de ambiente usam nome `config/SHA256(caminho absoluto)`.
  Arquivo de mount usa `mounts/SHA256(caminho absoluto)/__file__`; diretório usa
  o mesmo prefixo e caminho relativo POSIX de cada arquivo. Sem diretórios TAR,
  links, nomes extras ou omissões. Diretórios e permissões originais também
  ficam vinculados pelos fingerprints dos mounts no recibo.
- `restore035.json`: backup_sha256 do dump, ledger com as35 versões exatas,
  restore_verified=true, isolated=true, migrations_executed=false e
  production_runtime_changed=false. Isso deve ser resultado de execução real,
  nunca campos preenchidos só para liberar o gate.
- `v01-backup-receipt.json`: source_sha, baseline_sha, release_profile='035',
  captured_unix; sha256 dos quatro arquivos acima; runtime_fingerprints por
  serviço usando runtime_fingerprint(); mount_fingerprints por serviço usando
  mount_fingerprints(). Somente valores obtidos da captura real.

O dump e a captura devem ter menos de15min. A prova de restore deve estar ligada
ao mesmo hash. As provas locais com dados fictícios não servem para esse gate.
Se não houver recursos seguros na VPS, usar executor privado autorizado; não
contornar os limites ou interromper PostgreSQL/n8n/WAHA.

## Aplicação futura — exige aprovação específica de deploy

```sh
sudo python3 tools/team-v01-release.py --source "$SOURCE" --bundle "$BUNDLE" \
  --backup "$BACKUP" --apply
```

O comando adquire lock comum do piloto, repete o preflight, exige backup/restore
fresco e cria overlay novo dentro do backup privado. Não reescreve os overlays
anteriores. Recria somente API e depois gateway com no-deps/no-build/pull never.
Confere IDs das imagens, ambiente, segurança, mounts, ledger, arquivos HTTPS e
respostas anônimas401/404. PostgreSQL/n8n/WAHA não podem ser recriados nem
reiniciados. A variável antiga5a da API é atualizada somente nesse corte.

Em falha, tenta restaurar cada serviço alterado com seu contexto anterior. Se a
imagem anterior sumiu, verifica e carrega o arquivo de rollback antes de repetir.
Um rollback com falha em um serviço ainda tenta o outro, e nunca declara sucesso.
Não restaura banco, preservando operações novas. Depois é obrigatória a
homologação autorizada de login/logout, CRM/Caixa e sessões no site principal.

## Estado da validação

Testes focados cobrem drift de ambiente/redes/aliases/comandos, ledger exato035,
backup/restore/frescor/permissões, mounts, capacidade e rollback com falha do
gateway. Probe somente leitura no runtime real conferiu os dois serviços266.
Não houve execução de apply nem criação de backup de produção nesta rodada.
CI combinado, artefato final e gates reais da janela continuam obrigatórios.
