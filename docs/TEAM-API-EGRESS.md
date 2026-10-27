# Saída HTTPS da API team

O Compose base conecta a API somente a redes internas (database e api). Isso preserva o isolamento inicial, mas não fornece saída para OAuth da Meta ou SMTP. Uma falha HTTPS isolada não confirma a causa: conferir Internal das redes efetivas, resolução DNS e tipo da exceção TLS/proxy antes de alterar produção.

compose.team.egress.yaml é um overlay opcional, desativado no Compose base. Adiciona exclusivamente a rede socialmei_team_egress à API. Não publica portas, não conecta o PostgreSQL à internet e preserva as redes internas e o gateway. Não restringe a saída por domínio; o transporte Meta mantém sua allowlist HTTPS.

## Aplicação controlada

1. Inspecionar redes efetivas e confirmar que a API só tem redes internas.
2. Guardar o comando Compose efetivo da API, todos os arquivos privados utilizados, imagens e configuração atual. Não usar apenas o Compose base antigo.
3. Renderizar o Compose atual e a candidata com esse overlay acrescentado ao final. Recusar qualquer diferença além da nova rede na API e sua definição.
4. Obter autorização específica para a mudança de rede na AWS.
5. Recriar somente team-api, com --no-deps --no-build --pull never. Não recriar gateway, PostgreSQL, n8n ou WAHA e não habilitar envios.
6. Validar saúde, login, HTTPS anônimo 401/404 e conectividade TLS com os dois hosts Meta, sem credenciais. Iniciar uma autorização NOVA pelo site; códigos anteriores são de uso único e expiram.

Rollback: reaplicar o comando Compose anterior, sem esse overlay, recriando apenas a API. Validar saúde/HTTPS. Não excluir redes preexistentes nem restaurar o banco. Não usar docker network connect como configuração definitiva: a mudança precisa permanecer no Compose efetivo.

## Evidência

Teste sintético renderiza ambos os modelos com Docker Compose e confirma que a única diferença são a rede de saída e sua associação à API. Não executa nenhuma alteração de rede ou container. Não comprova conectividade na AWS.
