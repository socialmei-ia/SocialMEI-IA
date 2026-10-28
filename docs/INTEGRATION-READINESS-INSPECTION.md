# Inspeção de integrações — somente leitura

`tools/integration-readiness-inspect.py` reúne os sinais necessários para planejar
os próximos testes de Instagram e WhatsApp no piloto da equipe. Não conecta
contas, não pareia telefone, não executa workflows e não faz publicação/deploy.

## Execução autorizada no Ubuntu

O operador deve executar uma cópia conferida do arquivo, proveniente do SHA
revisado, no servidor que já hospeda os containers da equipe:

```bash
python3 /caminho/privado/integration-readiness-inspect.py --target team
```

Sem `--target team`, o comando para antes de executar qualquer consulta. Argumentos inválidos também são omitidos das mensagens de erro. Não
existe opção `--apply`, alvo genérico, escolha de container ou comando arbitrário.
O cliente Docker usa explicitamente `/var/run/docker.sock`; seletores herdados
para outro daemon são removidos somente do processo de consulta. Não é necessário
atualizar o checkout antigo da VPS ou recriar serviços para executar a inspeção.

## O que o relatório contém

- Imagens/digests e saúde dos containers conhecidos. Tags fora dos formatos
  reconhecidos não são reproduzidas; o digest validado continua disponível.
- Flags da API como booleanos/modos conhecidos; valores inesperados são marcados
  como `invalid`, sem repetir a configuração fornecida.
- Presença da variável do registry WAHA, sem caminho ou conteúdo do arquivo.
- Nomes conhecidos das migrations instaladas; versões desconhecidas são apenas
  sinalizadas, sem impressão do valor arbitrário.
- Quantidade agregada de conexões Instagram válidas e de canais WAHA cadastrados,
  ativos e provisionados. Não há IDs de contas, números, usuários ou workspaces.
- Engine WAHA somente quando há valor conhecido na configuração do container.
- Metadados salvos dos workflows existentes `LHlqroY2xzvpYAmD` e
  `A0EcNxcRvfWnMwKI`: estado ativo, igualdade entre IDs de versão salva/ativa,
  contagem de webhooks e de nós HTTP que podem enviar mensagens/publicações.

As contagens de nós são calculadas no PostgreSQL do n8n. URLs, corpos, parâmetros,
credenciais e exports completos não saem do banco. O contrato da versão publicada
continua explicitamente `not_verified`: metadados não substituem a revisão do
workflow ativo, de suas credenciais e da conta de destino.

## Limites importantes

A ferramenta executa exclusivamente comandos `docker inspect` conhecidos e duas
consultas `docker exec` de formato fixo. Não há chamadas HTTP ao WAHA, Meta ou
outros endpoints; `session_status` permanece `not_verified`. Isso evita procurar
ou utilizar uma API key privada para declarar uma conexão que não foi testada.

As consultas funcionais rodam **dentro da API** e iniciam transação somente leitura
com timeout de 5 segundos. O banco do n8n usa `default_transaction_read_only=on`
e o mesmo limite. Cada subprocesso tem limite de 30 segundos; falhas recebem
mensagens genéricas, sem stdout/stderr bruto, caminhos ou configurações privadas.

- Flag configurada não é capacidade homologada.
- Rede de egress anexada não comprova HTTPS externo.
- Registry configurado não comprova arquivo montado/válido nem recepção habilitada.
- Conexão OAuth válida não comprova Direct ou publicação real.
- Canal provisionado não comprova telefone conectado.
- Workflow marcado ativo não comprova execução ou ausência de respostas duplicadas.

Não interpretar o relatório como autorização para ativar flags, alterar webhook
ou trocar o remetente. Primeiro confirmar backup/rollback, versão efetiva,
isolamento e responsabilidade de cada envio com o operador.

## Privacidade e verificação

Os testes usam fixtures sintéticas com segredos, e-mail e URLs inseridos em campos
que precisam ser descartados. Conferem allowlists, credenciais não refletidas,
alvo obrigatório, recusa de comandos mutadores/arbitrários, Docker local fixado,
SQL somente leitura e falhas sanitizadas. Não executam Docker, SSH ou consultas
contra serviços reais.

A saída foi projetada para compartilhar somente esse resumo. Nunca anexar o
`docker inspect` completo, o `.env`, QR, tokens, o JSON do registry ou exports de
workflows. A reversão da ferramenta não exige ação no servidor: nenhuma
configuração, imagem, tabela, arquivo ou processo é alterado por sua execução.
