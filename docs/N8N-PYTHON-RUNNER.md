# Executor Python do n8n legado

O Code node Python usa um task runner do próprio n8n, separado da API FastAPI do SocialMEI. O helper `tools/n8n-python-runner.py` atende exclusivamente a pilha auditada: n8n 2.40.5, projeto `socialmei`, container `socialmei-n8n`, arquivo `/home/ubuntu/socialmei/compose.yaml` e volume `socialmei_n8n_data`.

A imagem oficial `n8nio/runners:2.40.5` foi conferida no registro e fixada pelo digest. Referência: [task runners externos](https://docs.n8n.io/hosting/configuration/task-runners/). Não se trata de instalar Python no notebook ou de alterar a API.

## Operação autorizada

O script não deve ser executado pelo CI contra produção. Importar o módulo ou usar `--help` não aplica mudanças. A execução exige `--apply` e um backup privado recém-conferido, criado conforme o procedimento acompanhado na operação. Não presume acesso SSH nem descobre credenciais.

Antes de aplicar, exige a mesma identidade de container/imagem e o mesmo conjunto de containers do backup. Compara os arquivos locais com seu arquivo tar privado, as variáveis efetivas do Compose com o runtime e as opções resolvidas do n8n antes/depois. Divergências interrompem a operação; não há `git pull`, descarte de mudanças locais, atualização de versão ou sobrescrita dos arquivos originais.

A aplicação recria somente o n8n e inicia `socialmei-python-runners`, com `--no-deps`, `--no-build` e `--pull never`. O executor precisa já estar baixado. A imagem do n8n é preservada pelo ID local; o broker não ganha porta pública. Uma rede interna própria conecta os dois containers. A interrupção do painel ocorre durante a recriação do n8n; workflows ativos podem retomar sua operação normal após a subida.

## Arquivos privados e recuperação

- `/home/ubuntu/.config/socialmei/n8n-python/compose.python-runners.json`: configuração ativa e token compartilhado, gerado no servidor. Diretório privado e arquivo protegido; fora do Git e da retenção de backups.
- Pasta de backup indicada por `--backup`: snapshot privado da configuração nova, configuração anterior e comando `rollback.sh` preparado. Nenhum rollback ou restore é automático.
- Os arquivos privados não devem ser publicados, copiados para o chat ou acrescentados ao repositório.

Atualizações futuras desse n8n precisam considerar a configuração ativa; um `compose up` genérico somente com o arquivo base pode removê-la. O backup recorrente deve cobrir também esse diretório privado. O helper não instala cron nem altera a rotina de backup existente.

## Validação e limites

O helper confere saúde local do n8n, imagem/volume/ambiente preservados, executor em execução e identidade/horário de início dos demais containers. Isso não comprova registro do executor nem execução de código: depois da aplicação é necessário testar um workflow manual isolado com um Code node em Python, sem credenciais ou integrações externas.

Nenhum workflow é acionado manualmente pelo helper; a versão do n8n não muda e nenhuma migration ou restauração é solicitada. O índice e os hashes do dump não substituem um ensaio de restore em destino isolado. O helper não habilita bibliotecas extras, permissões amplas de imports, envio de mensagens ou acesso público ao broker.
