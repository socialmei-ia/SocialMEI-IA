# Prisma: orçamento sustentável e janela de recuperação

Prisma permanece oficial. Nenhuma ativação das 24h, contratação, troca de banco ou alteração de produção está autorizada por este documento.

## Código e projeção

- `/health`: liveness fresco, sem SQL, a cada 15s.
- Healthcheck do container consulta `/health/db` a cada 60s. A resposta de readiness é reaproveitada por 300s; leituras em cache executam zero SQL. Até 6min para detectar/recuperar indisponibilidade no estado do container, mais o limiar de retries Docker. Docker saudável não substitui o gate de publicação.
- Probe periódico: um SELECT 1, autocommit, conexão somente leitura e timeout. Sucesso e falha têm cache. Validação completa inicial por processo/configuração; verificações operacionais e doctor continuam completas, sem cache.
- Falha de conexão inicial não inicia varredura. Falha parcial transitória de esquema limita novas varreduras a uma por 6h; permanece indisponível até validar. Falhas estruturais exigem correção e reinício validado. Não transformar erros em sucesso.
- Caixa: carregamento em lote, no máximo quatro SELECTs de dados, além de autenticação e manutenção de jobs sintéticos. Antes havia uma consulta por conversa e por job sintético. Preservados workspace, origem, 100 mensagens por conversa, ordem e análise persistida.
- Polling visível da Caixa: 30s; capabilities: 60s, descartadas na troca de sessão ou falha. Isso apenas espaça leituras: permissões são verificadas pelo backend em cada acesso. Estado de integração pode levar até 60s para atualizar; recarregar consulta imediatamente.
- Status do atendimento WhatsApp: 60s, recuo após falhas; Atualizar/Assumir/Retomar continuam imediatos e validados no servidor. Nenhum envio ou respondedor foi alterado.

### Mês de 31 dias

Hipóteses do limite: até quatro processos de API no total, TTL 300s, até um reinício diário por processo e configuração de banco estável. O runtime observado usa um processo; os cálculos reservam quatro. Cache é por processo e não é compartilhado entre réplicas.

| Componente                                                                                                   | Projeção ou orçamento mensal |
| ------------------------------------------------------------------------------------------------------------ | ---------------------------: |
| Monitoramento normal: 4 × 31 × 288 probes + 4 × 31 × 31 instruções de inicialização                          |                       39.556 |
| Monitoramento com falhas parciais e reinício diário: 35.712 probes + 4 × 31 × 5 × 31 instruções de varredura |                       54.932 |
| Reserva adotada para monitoramento, incluindo incerteza                                                      |                       60.000 |
| Polling: até 20h agregadas de Caixa visível com conversa WhatsApp aberta; até 29 comandos/min, arredondados  |                       35.000 |
| Orçamento para mensagens, respostas autorizadas e demais operações de usuários                               |                       55.000 |
| Orçamento para outros consumidores, backups e testes controlados                                             |                       20.000 |
| Margem não comprometida                                                                                      |                       30.000 |
| Total de orçamento                                                                                           |                      200.000 |

Consumo previsto sob esse envelope: até 170 mil, com 30 mil de margem. Os 55/20 mil são verbas de capacidade, não medições nem estimativas inventadas de mensagens reais. Não é garantia sob carga arbitrária. Mais horas ativas, processos, reinícios, alterações de configuração ou mensagens exigem recalcular; não desabilitar funcionalidades automaticamente para esconder consumo. Validar contabilização de SELECT, SET e transações pelo provedor.

A inspeção anterior observou 214 healthchecks em uma hora, sem chamadas de conversas/claims nessa amostra. Isso confirma amplificação, não atribui todo o faturamento. Workflows ativos consultados não tinham gatilhos Schedule/Cron; não exclui consumidores externos.

## Overlays e rollback

Os seis overlays classificados como ausentes existem: o usuário ubuntu não tinha permissão de travessia em /var/lib. Recuperação com sudo somente leitura preservou 24 arquivos originais, hashes e ACL privada local.

Merge efetivo validado para API e gateway: zero divergências de ambiente, imagens, comandos, mounts, redes, portas, healthchecks, segurança e recursos contra inspect atual. Compose também validado offline. Recibo sanitizado: `.preview/private-overlay-reconciliation.json`; arquivos e env privados permanecem fora do Git.

Rollback privado fixado nas imagens instaladas, com pull_policy never; mantém Prisma, mounts, Caddy e todas as configurações. Delta candidato permitido somente após autorização: imagem API, imagem gateway necessária ao frontend, healthcheck da API e TTL 300. Não recriar n8n, WhatsApp ou bancos. Não executar migrations: esta PR não altera schema.

## Antes de iniciar a janela

1. CI e imagens da SHA exata aprovados; usar somente bundle/recibos correspondentes. Revisar o delta privado sobre o merge recuperado e validar Compose sem subir serviços.
2. Conferir no painel Prisma cota/consumo por workspace, período, consumidores e elegibilidade; não acionar Restore access ainda. Registrar baseline e método de cobrança.
3. Ferramentas PostgreSQL 17 já disponíveis como imagem na AWS. Preparar armazenamento privado, hashes e destino isolado de restauração; dumps fora de Git/OneDrive. Não usar ferramenta histórica limitada a schema 033 para certificar schema 038.
4. Obter autorização específica de publicação e da janela. Confirmar gates completos, comandos de rollback e serviços afetados antes de executar.

## Após confirmação

- **0–30min:** ativação autorizada, início/fim UTC, identidade Prisma, disponibilidade API e validação completa sem cache. Nenhum teste em loop.
- **30–90min:** backup Prisma consistente, hash, restauração isolada; comparar tabelas, ledger e contagens com reserva AWS pelo mesmo critério. Não sincronizar diferenças. Os históricos 477 e 481 não são diretamente comparáveis.
- **90–150min:** medir operações no painel antes/depois, descontar backup/testes e separar períodos ociosos/uso real. Projetar taxa × duração restante do mês; incluir todos os bancos do workspace e processos. Gatilhos de revisão: projeção acima de 170mil ou margem abaixo de 30mil; não contratar nem trocar banco automaticamente.
- **2,5–5h:** Direct autorizado: correlacionar Meta/Caddy/API, assinatura, evento e mensagem únicos no workspace correto, persistência antes de IA e exibição na Caixa. Distinguir POST ausente, rejeição e falha SQL. IA/envios permanecem desligados.
- **5–7h:** Caixa, histórico e controles WhatsApp sem duplicidade ou mudança de respondedor. Envios reais exigem autorização específica.
- **Restante:** corrigir bloqueios comprovados, backup final e decisão antes de expirar. A janela não renova franquia; plano pago somente autorizado.

Backup e restauração dos dados Prisma reais ainda não estão certificados, pois o serviço segue bloqueado. CI descartável não os substitui. Não ativar a janela nem publicar sem autorização.
