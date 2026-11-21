# Premium v6.9 — R2 revertida; bloqueio no smoke do navegador

**Última operação:** o plano R2 de48 arquivos foi autorizado, aplicado e **revertido** porque o smoke público voltou a apresentar timeout de leitura. Imagem premium anterior, mounts, CRM233 e API restaurados e conferidos; outros contêineres permaneceram iguais. Nenhuma carga comercial, migration, alteração de canal ou worker foi executada. Não há v6.9 publicada.

[Evidência da tentativa R2 e reversão](evidence/20261120-premium-v69-r2-publication-rollback.json).

**Não reutilizar o plano R2 nem sua autorização.** O recibo está encerrado como `rolled_back` e a identidade do gateway mudou pela reversão. Não haverá outra tentativa enquanto a falha da jornada completa não estiver reproduzida e corrigida com evidência.

## Bloqueio atual e próximo diagnóstico

- CI da fonte `7d6dcf3`: [aprovada](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/44835981381). Hashes dos48 arquivos confirmados contra esse commit; preflight R2, dependências, rollback e saúde inicial passaram.
- A candidata no navegador isolado com API real passou; o smoke do site publicado falhou. Assim o teste com sobreposição de arquivos não é prova suficiente de homologação pública.
- A nova telemetria identificou `request_timeout` em `/reporting/overview` na jornada de navegador. Consulta isolada no mesmo ambiente: Brilho60 em189ms e Bella61 em163ms. Dez leituras autenticadas em paralelo também passaram em menos de2s. Não há evidência para atribuir a falha à SQL desse relatório ou à simples concorrência de arquivos.
- O navegador também mostrou recursos com carregamento acima de25s na versão restaurada. A comparação com limite de dois scripts não eliminou o timeout; a alteração de loader ficou somente em experimento ignorado, fora da candidata e da produção.
- `tools/premium-smoke-diagnostics.cjs` acompanha cada request por identidade, registra abortos sem headers/corpos/query strings, identifica a leitura que falhou e exige documento novo, backend e painel prontos após troca. Cinco testes garantem privacidade, ausência de retries e preservação da falha de timeout. O timeout de autenticação continua em12s.
- Próximo: correlacionar `requestfailed` e os tempos de envio/resposta do navegador para a leitura exata, mantendo a versão restaurada. Não repetir a publicação como experimento. Recibos e resultados detalhados permanecem privados.

O plano privado da carga fictícia60/61 foi conferido novamente, com IDs e datas preservados, sem `--apply`. Continua exigindo autorização separada.

## Histórico da preparação R2 — executada e revertida

**Produção atual:** gateway premium anterior restaurado. A tentativa autorizada de46 arquivos foi aplicada, mas o smoke autenticado encontrou timeouts de leitura e duas dependências ausentes. O rollback congelado foi executado e validado: imagem, mounts, CRM233 e API preservados, HTTPS200, demais contêineres sem mudanças. A v6.9 **não está publicada**. Evidência: [publicação e reversão](evidence/20261120-premium-v69-publication-rollback.json).

## Candidata corretiva R2 — registro histórico

- **48 arquivos**, incluindo as dependências ausentes `frontend/scripts/v22-whatsapp-management.js` e `frontend/styles/v22-inbox-layout.css`.
- Bootstrap preserva os complementos instalados de horários, Central de Conexões, assistente da Caixa e acesso da conta. Sem alterações no Hero ou na identidade visual.
- Preflight verifica referências HTML/JS/CSS contra a sobreposição candidata e os arquivos reais do gateway; dependências ausentes bloqueiam antes da escrita. O rollback utiliza a mesma imagem premium por ID imutável, também aceito como origem somente quando coincide exatamente com o ID revisado.
- Novo plano: `465bead7b3a35e29d6d600b1d9d509fa5ae09912bc4b08e656fac524ea4790bd`. Pacote inativo e backups preparados; somente `team-gateway` poderá ser recriado. Configuração privada em `%LOCALAPPDATA%\SocialMEI-Privado\premium-v69-r2-final-preflight.json`.
- Dez testes do preflight e dois do bootstrap aprovados. Prévia local com API/PostgreSQL reais: alternância, recarga e seis estados de Caixa/Agenda/Integrações em390/1440px aprovados. A comparação somente leitura das dependências com a AWS não encontrou arquivos ausentes.
- O timeout observado no smoke produtivo ainda exige homologação da candidata corrigida; teste local não comprova a jornada na AWS. Antes de nova execução: CI final aprovada, autorização específica dos48 arquivos, `--verify` fresco com o hash R2 e rollback íntegro. Se o smoke voltar a falhar, reverter somente o gateway.

Não reutilizar a autorização ou o recibo da tentativa de46 arquivos. Não aplicar dados demonstrativos, migrations, canais ou workers. O próximo plano privado da carga60/61 está preparado, sem `--apply` executado.

## Plano anterior de46 arquivos — histórico, não reutilizar

**Mudança única proposta:** servir os **46 arquivos revisados da Premium v6.9** por binds readonly, recriando somente `team-gateway`. Manter a imagem personalizada `socialmei-premium-gateway:v6.5.1-cadastro-claro-1`, o `config.js` produtivo, o `auth-store.js`, o CRM233, Caddy, credenciais e os demais mounts. Sem reiniciar API, banco, WhatsApp, Instagram, n8n ou workers; sem migrations ou dados comerciais.

**Reversão:** recriar somente `team-gateway` com `rollback-compose.json` congelado, que referencia a imagem premium atual por ID imutável e restaura os mounts anteriores. Arquivos anteriores, Compose original/resolvido e arquivos privados montados foram copiados para backup privado. Os arquivos ativos não foram sobrescritos.

## Preflight concluído

- Fonte visual: `7eaf796d9938c91437f9d8315ccf2ce39f9fbb9d`, PR #236; [CI completa aprovada](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/44789663990).
- API preservada: `sha256:6cf2bc60fec3f31e5e0cc24d4e276a7ba43911e94343e1439dce75d84a5673f8`.
- Premium preservada: `sha256:b93aeac93d11ea0e88dd2c44961bc8f13df9bcb928d960b3562563e68b6cc8ec`.
- Plano autorizado, executado e revertido: `a846c5a6335dfa5f7af73e4dc09cf3a6157e12bbad3e70979409a991e0d237f5`. Sua identidade inicial de contêiner foi substituída pelo rollback e não corresponde mais ao runtime.
- Cadeia Compose real conferida com os mesmos privilégios de leitura da publicação anterior: os arquivos privados exigem `sudo -n`. Nenhuma proteção foi removida ou arquivo ausente substituído.
- Configuração renderizada mantém ambiente, imagem, redes, portas, recursos, comandos, opções de segurança e todos os serviços; somente os binds dos 46 arquivos variam.
- Pacote já enviado para pasta privada inativa na AWS; nenhum build, carregamento de imagem ou serviço novo necessário.
- Backup/rollback e verificação fresca `--verify` concluídos; serviços produtivos não modificados.

O caminho do pacote e o plano completo estão exclusivamente em `%LOCALAPPDATA%\SocialMEI-Privado\premium-v69-final-preflight-20261120.json`. O código revisável está em `tools/prepare-premium-v69-release.py`; o CLI só prepara/inspeciona, não publica. Cinco testes focados verificam limites do delta, caminhos reservados, integridade do plano e do rollback.

## Procedimento histórico da tentativa anterior

1. Revalidar o pacote com `sudo -n python3 <pacote>/prepare-premium-v69-release.py --package <pacote> --verify`. Exigir exatamente o hash acima; qualquer diferença interrompe a execução.
2. Usar o `candidate-compose.json` privado, o diretório de trabalho original registrado no plano e o projeto `socialmei-team`. A única recriação permitida é `up -d --no-deps --no-build --pull never --force-recreate team-gateway`. Não executar outro serviço nem `down`.
3. Conferir imagem premium, mounts e hashes de todos os arquivos; confirmar API/DB/site, login da conta34, Brilho60 → Bella61 → Brilho60, recarga e Caixa em celular/desktop. Leituras e sessões apenas: não associar cliente real nem gerar mensagens como smoke.
4. Em falha crítica, usar o Compose de rollback congelado e a mesma seleção exclusiva do gateway; verificar os hashes protegidos e a saúde novamente. Não restaurar banco nem históricos.

Essa aprovação é independente da aplicação dos manifestos fictícios, de concessões ao professor e de qualquer canal/worker. Esses itens não fazem parte desta publicação.
