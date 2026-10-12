# Operação da equipe e integração de leitura

O servidor confirmado é `54.94.213.7`, com site em
`https://socialmei-ia.54-94-213-7.sslip.io/`. A senha do navegador continua ativa.
A decisão de contas/acesso público segue pendente com o dono do projeto.

## Manutenção

Em `/home/ubuntu/socialmei-team`:

```bash
python3 tools/team-maintenance.py doctor
python3 tools/team-maintenance.py backup
python3 tools/team-maintenance.py enable-backup
```

O backup usa `pg_dump -Fc` do banco **socialmei_team**, verifica o índice com
`pg_restore --list`, guarda `.env.team` e toda a pasta privada, calcula SHA-256 e
marca sucesso somente com `concluido.json`. Não interrompe serviços. Arquivos
ficam privados em `/home/ubuntu/socialmei-backups/team-auto-*`, fora da raiz web.
Falhas não são marcadas como concluídas; logs não contêm valores de credenciais.
Há lock para impedir manutenção/backup simultâneos. O índice verifica o formato;
o CI também restaura um dump em banco isolado e confere um registro. Isso não
substitui ensaiar a recuperação dos backups reais e das configurações do servidor.

O cron faz backup às 02:30 no horário do servidor, preserva outros agendamentos e
não duplica a própria entrada. `disable-backup` remove somente essa entrada.
Confira `team-backup.log` e o espaço livre. Não há exclusão automática de backups.
Essas cópias ainda estão na instância: copie-as para armazenamento privado externo
antes de considerá-las proteção contra perda da AWS. Não envie arquivos pelo chat.

## Preparar e instalar a conexão do n8n

Depois do merge, faça backup antes de atualizar o código da equipe. Após conferir
o worktree, prepare o token e reconstrua API/gateway:

```bash
python3 tools/team-maintenance.py prepare-n8n
COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file .env.team -f compose.team.yaml up -d --build --wait --wait-timeout 180
python3 tools/team-maintenance.py check-n8n
python3 tools/team-maintenance.py import-n8n
```

O token técnico é aleatório, permanece em `.env.team`/arquivos privados e não muda
contas humanas. O gateway permite Bearer somente nos cinco caminhos GET listados
abaixo; outros caminhos ou métodos continuam exigindo Basic auth. A API valida o token,
exige workspace `team` e oferece apenas GET. Se não configurada, falha fechada.
POST/PATCH/DELETE não existem nessa interface; a chave não permite escrever no
CRM nem abrir o site. Rotas humanas não aceitam o token técnico.

`import-n8n` confere os containers existentes do projeto `socialmei`, testa HTTPS,
faz backup do PostgreSQL antigo e da configuração do n8n e importa uma credencial
e **um novo fluxo inativo** com IDs aleatórios exclusivos. O CLI usa o proprietário
padrão do n8n. Fluxos existentes não são ativados, desativados ou reimportados.
Após sucesso, repetição não sobrescreve o fluxo, mesmo se ele tiver sido editado.
Falha parcial preserva a identidade para repetir; não apague a instalação para
forçar outra importação. Arquivos temporários no container são removidos e a cópia
local da credencial em texto é apagada após sucesso. Backups/configurações privadas
podem conter segredos e devem continuar protegidos.

Se a versão instalada do n8n recusar a importação, o comando para sem reiniciar
o n8n ou alterar outros fluxos. Confira a versão e permissões pelo terminal;
os logs da automação não reproduzem saídas que possam conter segredos.

Abra o editor n8n, atualize a lista e execute manualmente
**SocialMEI equipe — conferir conexão**. Deve retornar workspace `team`, acesso
`leitura` e contagens dos quatro módulos. Esse fluxo não recebe webhooks, não tem
agendamento e não envia mensagens. A confirmação HTTPS no servidor é separada da
execução efetiva dentro do n8n, que precisa ser conferida no editor.

## API técnica

- `GET /api/v1/integracoes/resumo`: saúde e contagens, sem dados pessoais.
- `GET /api/v1/integracoes/clientes`, `/produtos`, `/vendas`, `/financeiro`: páginas
  do mesmo banco da equipe; vendas/financeiro excluídos não aparecem.
- Listas aceitam `limit` (1–500, padrão 100) e `offset` (padrão 0), retornando
  `itens`, `limit`, `offset` e `proximo_offset`. Continue até este último ser `null`.
  São páginas independentes; encerre alterações para exportar consistentemente.

Todas as consultas usam transação READ ONLY: não criam workspace, não mudam versão,
não baixam estoque nem registram pagamentos. Respostas usam `Cache-Control: no-store`.
A credencial tem leitura dos quatro módulos; não a use em webhooks públicos que
devolvam dados pessoais. A futura escrita de automações exige outro contrato e
identidades de operação; não dê acesso ao banco diretamente como atalho.

Para desligar a integração, esvazie apenas `TEAM_N8N_READ_TOKEN` e recrie `team-api`.
Rotacionar exige atualizar a credencial do n8n também; o instalador recusa troca
silenciosa depois da importação. Para rollback do código, preserve arquivos
privados e volte ao commit anterior; não restaure o banco de produção automaticamente.

## Ainda dependem de ação humana

- Decisão de contas/acesso público com o dono do projeto.
- Automatizar a cópia privada dos novos backups fora da instância; a cópia inicial no notebook já foi conferida.
- Chip dedicado, QR/sessão WhatsApp e regras de resposta/envio de mensagens.
- Ensaiar recuperação dos backups reais em um destino separado.

Em 12/10/2026, o acesso SSH pelo notebook, dois backups externos com SHA-256 e a
execução manual do fluxo de leitura no n8n foram confirmados. Isso não comprova
recebimento/envio de WhatsApp nem escrita por automações. A sessão WAHA ainda não
foi conectada a um número dedicado.

Assistente, Relatórios e Caixa Unificada não são declarados completos por esta
mudança. O site GitHub Pages continua demonstrativo/local; os dados compartilhados
ficam no site protegido da AWS.
