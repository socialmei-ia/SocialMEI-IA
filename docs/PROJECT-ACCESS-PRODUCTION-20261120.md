# Acesso multiempresa concluído na AWS

Autorização específica: cadastro oficial da conta do projeto, perfil da Bella e concessão aditiva de proprietário no Brilho. Nenhuma autorização de carga comercial, publicação visual ou transferência de canal foi utilizada.

- Conta `servermeiiafacepe@gmail.com`: usuário **34**, credencial ativa, sem administração global.
- **Brilho&Limpeza Service — workspace 60:** proprietários **33 e 34**. Conta, credencial e sessões do usuário 33 permaneceram iguais na comparação antes/depois.
- **Bella Store — workspace 61:** workspace gerado pelo cadastro normal, reaproveitado como autorizado; proprietário **34**, perfil comercial `fashion` persistido.
- API segue `17cfd1956416c2d4c8431fec11800f73254bde12`; banco efetivo PostgreSQL realocado/schema040. Sem migrations ou reinícios.

## Evidência real

Navegador autenticado na AWS: Brilho → Bella → Brilho sem novo login; recarga preservando o contexto; clientes, catálogo, conversas e relatórios consultados no contexto selecionado; troca maliciosa para workspace 1 recusada com **403**. Zero erros de página e zero gravações comerciais.

Concessão por `workspace_access.py`, com administrador ativo 1, identidade exata, estado esperado, hash aprovado e recibo durável. Backup privado local e na AWS. O comando de rollback foi validado **somente em inspeção**; não foi executada revogação. Ele remove exclusivamente o vínculo adicionado 34/60, preservando proprietário 33 e históricos. A conta nova e Bella não são apagadas automaticamente.

O cadastro teve um PATCH de perfil recusado com 422 por ausência de `schema_version`; o cadastro não foi repetido. O perfil foi reconciliado com `schema_version:1` validado pelo contrato existente.

## Dry-runs produtivos aprovados — aplicação não executada

Manifestos e inventários completos estão apenas em `%LOCALAPPDATA%\SocialMEI-Privado`:

- `project-brilho-target.json` e `project-brilho-dry-run-20261120.json`.
- `project-bella-target.json` e `project-bella-dry-run-20261120.json`.

O manifesto rastreado antigo com usuário 33 é histórico; não representa a nova conta do projeto. Não enviar credenciais ou inventários privados pelo chat/Git.

| Registros previstos           | Brilho/60 | Bella/61 |
| ----------------------------- | --------: | -------: |
| Clientes fictícios            |         4 |        4 |
| Serviços / produtos fictícios |         3 |        3 |
| Recursos                      |         2 |        0 |
| Reservas                      |         4 |        0 |
| Vendas                        |         2 |        2 |
| Financeiro                    |         3 |        3 |
| Oportunidades                 |         2 |        2 |
| Lembretes internos            |         2 |        2 |

Ambos os destinos estão sem registros comerciais. Previews de importação aprovados, sem conflitos detectados; snapshots anteriores/posteriores iguais. Bella preservará o perfil existente. Brilho receberá perfil e política de horários inicialmente desabilitada. Históricos em 17/18 e pendentes em 23/24 de novembro de 2026; data-base 19/11 e IDs de operação preservados. Revalidar datas e estado antes de qualquer aplicação aprovada.

## Pendências específicas

| Prioridade | Item                                      | Estado                                                                                                                                                        |
| ---------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0         | Acesso multiempresa produtivo             | Concluído e testado no navegador AWS                                                                                                                          |
| P0         | Aplicação dos dois manifestos             | Dry-runs aprovados; exige aprovação própria de escrita comercial                                                                                              |
| P0         | Premium v6.9                              | PR #236, local/CI aprovados; publicação ainda não autorizada                                                                                                  |
| P0         | WhatsApp no Brilho                        | Canal/registry ainda 1/1, GOWS01; 1 rascunho humano pendente; falta operação segura de aposentadoria/transferência e autorização do piloto fora do workspace1 |
| P0         | Instagram das duas empresas               | 60/61 sem conexões; conexão histórica permanece no1; worker legado ainda Prisma; exclusividade com n8n e OAuth/homologação pendentes                          |
| P1         | Professor                                 | Conta local testada; identidade/e-mail produtivo e concessão específica ainda necessários                                                                     |
| P1         | Backups externos/acesso de leitura/e-mail | Pendências anteriores preservadas; nenhuma alteração nesta operação                                                                                           |

Nenhuma mensagem histórica foi movida; nenhum sender foi habilitado. A restrição de sessão `UNIQUE(provedor,instancia,sessao)` e as FKs históricas impedem transferir o canal por simples troca de registry ou `workspace_id`. Não renomear instância/sessão para contornar essa proteção. Preparar e testar o contrato de transição antes de pedir aprovação de corte.

Resumo público verificável: [20261120-project-access-production.json](evidence/20261120-project-access-production.json). Os recibos privados permitem retomar a operação sem recadastrar a conta nem repetir a concessão.
