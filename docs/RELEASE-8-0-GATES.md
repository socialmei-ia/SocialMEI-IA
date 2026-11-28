# Candidata 8.0

A referência de produção disponível é a Missão 07 com schema 046. A candidata precisa do aceite manual dessa versão, da homologação integrada e das autorizações de publicação. A execução local usa dados sintéticos e mantém os envios externos desativados.

## Preparar as imagens

```powershell
python tools/build-production-overlay.py --build api --inbox-fixes --editorial --commercial --management
python tools/build-production-overlay.py --build gateway --gateway-fixes --editorial --commercial --management
```

Use os IDs base do manifesto congelado. Registre o SHA do Git, os IDs das imagens prontas, os hashes dos mounts e as referências atuais de rollback. A opção editorial inclui o worker de fotos, com ativação separada. As candidatas de mídia dos canais exigem ensaio próprio, partindo dos workers efetivos.

## Gates para produção

1. Confirmar em produção o aceite manual da Missão 07, o ledger, a saúde e os mounts efetivos.
2. Validar backup fresco com restauração isolada. Verificar instalação limpa e atualização de 046 até 054 com as permissões do papel da API. Conferir leitura da view de caixa e escrita restrita das tabelas novas.
3. Aprovar separadamente as migrations, o corte de API e gateway e qualquer ativação externa. Revalidar CI, uso de memória, isolamento, idempotência e journaling.
4. Ensaiar reversão de API e gateway juntos com os mounts equivalentes. Antes de aceitar escritas da candidata, usar as imagens e configurações congeladas se houver regressão. Após escritas de parcelas e recebíveis, congelar as operações afetadas e manter o ledger. A versão anterior desconhece os vínculos e poderia aceitar baixas conflitantes. Corrigir na versão compatível ou manter Financeiro e Vendas indisponíveis até a recuperação.
5. Testar HTTPS, autenticação, troca de empresa e as jornadas abaixo. Testar provedores somente com contas autorizadas e aprovação do envio. Preservar WAHA e n8n durante o corte da aplicação.

## Roteiro do responsável e do professor

| Área            | Ação e resultado esperado                                                                                                                                                                                                              |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sessão          | Alternar entre Brilho e Bella e recarregar. Cada empresa mostra somente seus próprios registros.                                                                                                                                       |
| Caixa           | Na versão publicada, testar leitura, arquivo, recuperação, fixação, adiamento, respostas rápidas e o controle de automação. Registrar o aceite da Missão 07.                                                                           |
| Agenda e CRM    | Registrar e cancelar um agendamento no ambiente de teste. Conferir o histórico do cliente, os filtros e a liberação do horário.                                                                                                        |
| Venda e estoque | Converter uma oportunidade em venda. Uma repetição do mesmo pedido mantém uma venda e uma baixa de estoque.                                                                                                                            |
| Financeiro      | Criar um recebível para a venda em ambiente de teste, registrar uma parcela e conferir caixa e saldo aberto. Quitar o restante, consultar a venda e estornar uma parcela com motivo. A venda volta a pendente e o caixa é recalculado. |
| Negócio e DAS   | Conferir o corte do faturamento anterior. Declarar um DAS fictício no ambiente de teste, consultar a revisão e revogar a declaração. O registro é interno.                                                                             |
| Divulgação      | Salvar, recarregar, editar, duplicar e arquivar um rascunho de texto. Conferir o agendamento de foto sem ativar a publicação externa.                                                                                                  |
| Professor       | Usar a conta individual autorizada. Conferir os relatórios permitidos e a troca de empresa. Operações de escrita exigem papel próprio e autorização.                                                                                   |

## Pendências de liberação

- Aceite manual da Missão 07, CI do commit de release e rollback conjunto com mounts equivalentes.
- Homologação e autorizações para áudio/mídias, Meta e Brevo. Lembretes, presença e agendamento público exigem seus próprios testes e autorizações.
- Manter no backlog relatórios, notificações, histórico de estoque e formatos de mídia/publicação ainda incompletos. O rascunho de texto salvo no servidor mantém a mídia no editor local. Dados legados de navegador continuam no navegador.
