# Recuperação Prisma: janela de 24 horas ainda não ativada

## Evidências e limites

Prisma continua oficial: `db.prisma.io:5432`, banco `postgres`. Não substituir DATABASE_URL pela reserva AWS. Nenhuma liberação, contratação ou alteração em produção foi feita.

O healthcheck efetivo chama `/health/db` a cada 15s. Foram observadas 214 chamadas na última hora, sem conversas ou claims nessa amostra. Nos workflows marcados ativos consultados não há gatilhos Schedule/Cron; isso não exclui consumidores externos. A amostra durante bloqueio não mede o consumo anterior faturado.

Cada validação completa autenticada executa 25 SELECTs e duas instruções SET. Projeção por processo: 144.000 SELECTs/dia antes; 40.320 após o cache de 60s (menos 72%). Transações e SET não entram nessa conta. É uma amplificação confirmada, mas a atribuição do esgotamento exige métricas Prisma.

A redução ainda pode ultrapassar a franquia mensal. A página pública anuncia 200 mil operações/mês: https://www.prisma.io/pricing. Confirmar o plano efetivo e dimensionar a frequência de readiness sem retirar verificações de banco do deploy. Não prometer operação contínua gratuita com esta otimização isolada.

## Código preparado

- Cache apenas do esquema bem-sucedido por 60s, configurável entre 0 e 300s. Cada chamada verifica disponibilidade real; falha invalida o cache. Verificações operacionais explícitas continuam completas. Mudanças de esquema podem levar até 60s para aparecer no healthcheck.
- Caixa usa recuo de 12s até 5min após falhas; sucesso e troca de sessão reiniciam o recuo. Consulta manual permanece disponível; aba oculta não faz polling.
- Nenhuma alteração em migrations, dados, credenciais, IA, envios ou workflows.

## Preparação antes da confirmação

1. Registrar SHA, CI aprovado e imagens correspondentes à candidata. Não promover antes disso.
2. Conferir no painel Prisma cota, período, consumidores e elegibilidade. Não acionar Restore access ainda.
3. Reconciliar offline os seis overlays históricos ausentes com o snapshot privado de configuração efetiva. Preservar env, mounts, redes, imagens e Caddy. Não recriar serviços com Compose incompleto.
4. Preparar ferramentas pg_dump/pg_restore compatíveis, armazenamento privado, hashes e destino descartável. Dumps fora de Git/OneDrive.
5. Rollback por imagens/configuração de API/gateway anteriores, mantendo Prisma. Não restaurar dump integral como rollback de código.
6. Obter autorização específica para aplicar a otimização mínima e para iniciar a janela. Preservar WhatsApp, n8n e PostgreSQL; não reiniciar serviços sem necessidade.

## Execução após confirmação

1. **0–30min:** ativar a liberação autorizada; registrar início/fim UTC e consumo inicial; confirmar identidade do banco e saúde da API sem testes em loop.
2. **30–90min:** backup consistente Prisma; hash; restauração isolada; validar migrations, tabelas e contagens. Comparar reserva AWS em leitura, usando o mesmo critério. Não sincronizar diferenças automaticamente. Os históricos 477 e 481 registros ainda não são comparáveis.
3. **90–150min:** medir taxa de operações e disponibilidade após a otimização. Se permanecer alta, localizar consumidores usando métricas antes de novas ações.
4. **2,5–5h:** correlacionar Direct autorizado com Caddy/API, assinatura, persistência e Caixa. Distinguir ausência de POST, rejeição e falha SQL. Exigir evento/mensagem únicos no workspace correto. IA e envios continuam desativados.
5. **5–7h:** verificar Caixa e histórico WhatsApp, sem mudar respondedor ou disparar mensagens. Envio real exige autorização específica.
6. **Tempo restante:** corrigir bloqueios comprovados, guardar evidências e backup final. Definir continuidade antes de expirar: reset gratuito ou plano pago apenas autorizado. A janela não repõe a franquia permanentemente.

## Bloqueios de execução

CI/imagens da nova SHA; reconciliação dos overlays privados; painel Prisma para cota e ativação autorizada. Backup Prisma e restauração dependem da volta do acesso e ainda não estão certificados. A instância física PostgreSQL17 socialmei-db não foi identificada; não equipará-la ao Prisma nem à reserva PG16 sem evidência.
