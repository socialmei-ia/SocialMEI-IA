# Janela de recupera??o Prisma ? preparada, n?o ativada

## Limites e evid?ncias

Prisma permanece oficial (`db.prisma.io:5432`, banco `postgres`). N?o trocar DATABASE_URL pelo PostgreSQL de reserva. `planLimitReached` bloqueia leitura/escrita; a cota exata e a elegibilidade da libera??o exigem o painel Prisma. Nenhuma libera??o, contrata??o ou mudan?a na AWS foi executada nesta prepara??o.

Inspe??o somente leitura: healthcheck efetivo /health/db a cada 15s; 214 chamadas na ?ltima hora consultada, zero chamadas de conversas/claims nessa amostra. N?o h? gatilho Schedule/Cron nos workflows marcados ativos consultados no banco n8n; isso n?o exclui chamadas externas ou outros consumidores. A amostra durante bloqueio n?o mede opera??es faturadas antes dele.

O c?digo fazia 25 SELECTs (incluindo migrations) e duas instru??es SET com autentica??o por healthcheck. S?o at? 144.000 SELECTs/dia por inst?ncia, independentemente de usu?rios. Com cache de 60s e checagens a cada 15s, a proje??o cai para aproximadamente 40.320 SELECTs/dia (72% menos); comandos de transa??o e SET n?o entram nessa conta. ? uma amplifica??o confirmada; atribuir o esgotamento exige o hist?rico de consumo do Prisma.

## Altera??es locais

- Readiness reutiliza valida??o bem-sucedida do esquema por 60s; cada chamada continua verificando conectividade real. Falhas nunca ficam saud?veis por cache. TTL configur?vel, at? 300s; zero desliga o cache.
- Caixa mant?m atualiza??o normal enquanto vis?vel; falhas usam recuo de 12s at? 5min. Troca de sess?o reinicia o recuo; atualiza??o expl?cita permanece dispon?vel.
- Sem altera??o de dados, migrations, credenciais, workflows ou pol?tica de envio.

A redu??o inicial ainda pode ultrapassar a franquia mensal: n?o basta para garantir opera??o cont?nua gratuita. Dimensionar frequ?ncia de readiness e consultas usando a franquia efetiva do workspace, sem retirar os gates de banco do deploy. A p?gina p?blica atual anuncia 200 mil opera??es/m?s, mas ? necess?rio conferir o plano deste workspace: https://www.prisma.io/pricing. N?o confundir proje??o de SELECTs com medi??o de opera??es faturadas.

## Antes de iniciar o rel?gio

1. Revisar diff/testes, registrar SHA, CI e imagens correspondentes. N?o promover c?digo sem esses resultados.
2. Conferir estat?sticas do workspace Prisma no painel: limite atingido, per?odo, consumidores e elegibilidade. N?o acionar Restore access ainda.
3. Reconstruir e validar offline Compose efetivo: h? seis overlays hist?ricos ausentes. Preservar snapshot privado de env/mounts/redes, Caddy e imagens atuais. N?o recriar servi?os usando Compose incompleto.
4. Preparar pg_dump/pg_restore compat?veis, armazenamento privado com espa?o, hashes e banco descart?vel de restaura??o. N?o guardar dumps no Git/OneDrive.
5. Registrar rollback de API/gateway para imagens e configura??es efetivas anteriores; manter Prisma como destino. N?o usar restaura??o integral como rollback de c?digo.
6. Obter autoriza??o espec?fica para aplicar a otimiza??o m?nima e para acionar a janela gratuita. Reduzir consumo antes de gastar a janela, sem reiniciar WhatsApp/n8n/PostgreSQL.

## Execu??o ap?s confirma??o

- 0?30min: ativar libera??o gratuita uma ?nica vez no painel autorizado; confirmar identidade do banco e disponibilidade API. Registrar in?cio/fim UTC e consumo inicial. N?o disparar testes em loop.
- 30?90min: gerar backup consistente Prisma; hash, pg_restore em destino isolado e validar migrations/tabelas/contagens. Comparar com reserva AWS em transa??es somente leitura e mesmo crit?rio de contagem; registrar diverg?ncias, sem sincronizar automaticamente. Dados hist?ricos 477 e reserva 481 incluem crit?rios n?o reconciliados.
- 90?150min: observar taxa de consumo e healthchecks otimizados, disponibilidade e falhas. Se consumo continuar alto, localizar consumidor com m?tricas do provedor antes de novas a??es.
- 2,5?5h: correlacionar um Direct autorizado com logs Caddy/API, assinatura e persist?ncia. Primeiro distinguir POST ausente, rejei??o e falha SQL; IA e envio continuam desligados. Confirmar evento/mensagem ?nicos, workspace e Caixa.
- 5?7h: validar Caixa e hist?rico WhatsApp sem envio autom?tico, duplicidade ou mudan?a de respondedor; envio real s? com autoriza??o espec?fica.
- Restante: corrigir apenas bloqueios comprovados, repetir backup incremental de evid?ncias e registrar limites/expira??o. A janela n?o resolve a cota permanentemente; preparar decis?o antes do prazo (reset gratuito ou plano pago somente autorizado).

## Bloqueios restantes

Painel Prisma para cota/consumo e ativa??o autorizada; CI/imagens da nova SHA; reconcilia??o dos overlays privados; backup Prisma e restaura??o s? poder?o ser certificados quando o banco voltar a aceitar conex?es. PostgreSQL17 socialmei-db ainda n?o foi identificado como inst?ncia f?sica; n?o equiparar ao Prisma nem ? reserva PG16 sem evid?ncia.
