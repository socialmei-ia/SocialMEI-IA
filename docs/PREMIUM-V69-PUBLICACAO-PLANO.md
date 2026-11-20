# Publicação incremental v6.9 — aguardando aprovação

**Mudança única proposta:** servir os **46 arquivos revisados da Premium v6.9** por binds readonly, recriando somente `team-gateway`. Manter a imagem personalizada `socialmei-premium-gateway:v6.5.1-cadastro-claro-1`, o `config.js` produtivo, o `auth-store.js`, o CRM233, Caddy, credenciais e os demais mounts. Sem reiniciar API, banco, WhatsApp, Instagram, n8n ou workers; sem migrations ou dados comerciais.

**Reversão:** recriar somente `team-gateway` com `rollback-compose.json` congelado, que referencia a imagem premium atual por ID imutável e restaura os mounts anteriores. Arquivos anteriores, Compose original/resolvido e arquivos privados montados foram copiados para backup privado. Os arquivos ativos não foram sobrescritos.

## Preflight concluído

- Fonte visual: `7eaf796d9938c91437f9d8315ccf2ce39f9fbb9d`, PR #236; [CI completa aprovada](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/44789663990).
- API preservada: `sha256:6cf2bc60fec3f31e5e0cc24d4e276a7ba43911e94343e1439dce75d84a5673f8`.
- Premium preservada: `sha256:b93aeac93d11ea0e88dd2c44961bc8f13df9bcb928d960b3562563e68b6cc8ec`.
- Plano aprovado tecnicamente, **ainda sem autorização de execução**: `a846c5a6335dfa5f7af73e4dc09cf3a6157e12bbad3e70979409a991e0d237f5`.
- Cadeia Compose real conferida com os mesmos privilégios de leitura da publicação anterior: os arquivos privados exigem `sudo -n`. Nenhuma proteção foi removida ou arquivo ausente substituído.
- Configuração renderizada mantém ambiente, imagem, redes, portas, recursos, comandos, opções de segurança e todos os serviços; somente os binds dos 46 arquivos variam.
- Pacote já enviado para pasta privada inativa na AWS; nenhum build, carregamento de imagem ou serviço novo necessário.
- Backup/rollback e verificação fresca `--verify` concluídos; serviços produtivos não modificados.

O caminho do pacote e o plano completo estão exclusivamente em `%LOCALAPPDATA%\SocialMEI-Privado\premium-v69-final-preflight-20261120.json`. O código revisável está em `tools/prepare-premium-v69-release.py`; o CLI só prepara/inspeciona, não publica. Cinco testes focados verificam limites do delta, caminhos reservados, integridade do plano e do rollback.

## Execução somente depois da aprovação específica

1. Revalidar o pacote com `sudo -n python3 <pacote>/prepare-premium-v69-release.py --package <pacote> --verify`. Exigir exatamente o hash acima; qualquer diferença interrompe a execução.
2. Usar o `candidate-compose.json` privado, o diretório de trabalho original registrado no plano e o projeto `socialmei-team`. A única recriação permitida é `up -d --no-deps --no-build --pull never --force-recreate team-gateway`. Não executar outro serviço nem `down`.
3. Conferir imagem premium, mounts e hashes de todos os arquivos; confirmar API/DB/site, login da conta34, Brilho60 → Bella61 → Brilho60, recarga e Caixa em celular/desktop. Leituras e sessões apenas: não associar cliente real nem gerar mensagens como smoke.
4. Em falha crítica, usar o Compose de rollback congelado e a mesma seleção exclusiva do gateway; verificar os hashes protegidos e a saúde novamente. Não restaurar banco nem históricos.

Essa aprovação é independente da aplicação dos manifestos fictícios, de concessões ao professor e de qualquer canal/worker. Esses itens não fazem parte desta publicação.
