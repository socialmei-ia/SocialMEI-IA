# Identificacao de remetente no piloto WhatsApp

O ingresso WEBJS preserva o LID opaco como referencia da conversa. O nome inicial
generico evitava tratar esse identificador como telefone. Na sessao real do piloto,
o WAHA possui mapeamento LID para numero; a Caixa ainda exibia o rotulo generico.

`tools/team-whatsapp-contact-number.py` resolve somente uma conversa explicitamente
selecionada do workspace 1, canal provisionado e conta autorizada. Confere a sessao
WORKING/WEBJS, consulta o numero por LID e verifica o caminho inverso. Rejeita numero
invalido, conta propria, LID diferente, sessao trocada ou mapeamento ausente. As
consultas seguem o [contrato oficial de contatos WAHA](https://waha.devlike.pro/docs/how-to/contacts/#api---lids).

Referencias que ja chegaram como telefone `@c.us` pelo ingresso assinado usam esse
numero, depois da mesma verificacao da sessao/conta. Um LID numerico nunca e tratado
como telefone. Nao sao consultados contatos ou mensagens fora do piloto.

Por padrao apenas inspeciona. `--apply --confirm TEAM-1` substitui exclusivamente o
rotulo `Contato do WhatsApp` pelo numero confirmado em formato internacional e
incrementa a revisao da conversa. Essa revisao permite a atualizacao automatica da
Caixa sem mensagem adicional ou recarga. Um nome editado por humano e preservado.
Repetir a ferramenta para uma conversa ja identificada nao escreve novamente.

Nao altera LID, conta, canal, IDs, mensagens, deduplicacao, credenciais, estoque ou
workflows. Nao cria cliente nem une identidades. Nao aplica migrations, atualiza
imagens, reinicia servicos ou envia mensagens. A API/gateway instalados continuam
na versao funcional existente. O rotulo aparece na lista e no cabecalho da conversa;
isso nao cadastra automaticamente um telefone na ficha de um cliente do CRM.

Antes da escrita, cria snapshot privado com checksum em
`/var/lib/socialmei-wa-pilot/contact-number-TIMESTAMP-ID`. Somente o nome/revisao sao
alterados numa transacao, apos reconferir o vinculo e a revisao original. Uma mensagem
concorrente cancela a mudanca para permitir nova inspecao. O numero e os identificadores
permanecem no banco e no snapshot privado; nao sao impressos em logs/relatorios.

`--rollback SNAPSHOT --confirm TEAM-1` restaura somente o rotulo anterior se ele ainda
corresponde ao que a ferramenta escreveu. Incrementa novamente a revisao, preservando
mensagens que chegaram depois. Nunca restaura o banco completo nem retrocede a revisao.
Exige checksum, permissoes privadas e a mesma conta/canal/conversa.

Validacao: fixtures sinteticas para mapeamento divergente e ida/volta, nome humano,
idempotencia, isolamento de workspace e preservacao de mensagens/referencias/revisoes
em PostgreSQL descartavel. O navegador verifica alteracao apenas de rotulo/revisao
sem recarregar, em desktop e celular. Dados de producao nao entram nesses testes.

## Identificacao periodica

`tools/team-whatsapp-contact-refresh.py --source-sha SHA` inspeciona ate 200 IDs
de conversas genericas do canal provisionado do piloto. Nao resolve numeros nem
escreve por padrao. `--apply --confirm TEAM-1` resolve no maximo tres contatos por
execucao, reutilizando as verificacoes e snapshots individuais acima. Falhas sao
adiadas por cinco minutos, com espera exponencial ate 24 horas. O estado privado
guarda somente IDs, quantidade de falhas e horario da proxima tentativa. Nomes
humanos e contatos ja identificados nao entram na selecao.

`tools/team-whatsapp-contact-schedule.py --source-sha SHA` inspeciona exclusivamente
o job dedicado. `--install --confirm TEAM-1` instala uma execucao por minuto em
`/etc/cron.d/socialmei-whatsapp-contact-refresh`, somente a partir de checkout
limpo e SHA fixado em `/home/ubuntu/socialmei-backups/ETAPA/source`. Exige cron
ativo, API saudavel, autenticacao e modo de recebimento do piloto; nao reinicia
servicos. O lock compartilhado impede execucoes simultaneas. Um arquivo de cron
preexistente com conteudo diferente e preservado e bloqueia a instalacao.

Antes de instalar, verificar CI Linux, backup fresco de banco/config e inspecao
sem escrita. O agendamento cria snapshot privado com checksum e relatorio sem
numeros. O log e privado em `/var/lib/socialmei-wa-pilot/contact-refresh.log`;
monitorar tamanho e rotacionar conforme a retencao operacional.

Rollback: executar o mesmo `team-whatsapp-contact-schedule.py --source-sha SHA
--remove --confirm TEAM-1` antes de restaurar rotulos individuais. A remocao confere
o conteudo exato do job e nao toca em outros agendamentos. Depois usar o helper
individual com `--conversation-id ID --source-sha SHA --rollback SNAPSHOT
--confirm TEAM-1`. Os snapshots individuais ficam sob o diretorio privado do
piloto. Nao restaurar o banco completo, reiniciar WAHA ou alterar webhooks.

O agendamento identifica novos remetentes quando o WAHA consegue comprovar seu
numero. Mapeamento indisponivel permanece pendente; nao ha inferencia de telefone.
