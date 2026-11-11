# Demonstração do professor Valter

Usar somente o preview HTTPS descartável em `https://127.0.0.1:8443`.

```powershell
npm.cmd run demo:valter
npm.cmd run test:valter
```

O preview precisa estar iniciado com autenticação e análise `stub`. O preparador recusa outros ambientes e não faz deploy, não conecta provedores e não envia mensagens. Reexecutar preserva os identificadores e não duplica vendas nem movimentações de estoque.

- Login: abrir `/frontend/entrada.html#/entrar`. Credenciais fictícias em `.preview/valter-demo-account.json`, ignorado pelo Git.
- Negócio: **Ateliê Escola — MEI FICTÍCIO**, 3 clientes, 2 produtos e 1 serviço. Horário de funcionamento editável em Configurações.
- Agenda: um lembrete fictício vinculado ao cliente. Criar, concluir e cancelar mantém persistência por empresa. Não envia avisos externos.
- Vendas: uma paga e uma pendente. Kit com estoque 10 após vender 2 unidades; serviço sem estoque. Financeiro: recebimento, despesa e valor em aberto.
- Caixa: 3 conversas **SIMULADAS** persistidas, com análise determinística identificada. Não representam WhatsApp/Instagram recebidos de verdade nem IA externa.
- Integrações: prévia WhatsApp 0–5 usa o catálogo desse negócio, sem envio.
- Relatórios: selecionar período em **Dados do seu negócio**, conferir vendas/financeiro/recebimentos de mensagens por origem, exportar CSV e usar **Salvar PDF / imprimir**. No diálogo de impressão, escolher PDF.
- Evidências locais: `test-results/valter-demo/` contém CSV, PDF e capturas. Nenhum dado real de clientes é utilizado.

Pendências externas: homologação WAHA/n8n/Meta, SMTP e IA real; imagens não são analisadas por este fluxo. Agendamento automático de relatórios ainda requer definição do destino e executor. Não simular essas capacidades como concluídas.

A Agenda requer a migration aditiva `034_workspace_agenda.sql`. Foi validada somente em bancos descartáveis locais; a publicação exige backup/rollback e revisão das ferramentas de release históricas que limitam o schema a 033. Não aplicar em produção automaticamente.
