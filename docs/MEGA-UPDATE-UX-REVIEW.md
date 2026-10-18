# Revisão de experiência — evidências e decisões

Inspeção no Chromium, somente dados fictícios e API simulada. Não é auditoria de
produção, certificação em dispositivo físico ou teste manual de leitor de tela.

Foram capturadas landing, login/cadastro e 12 áreas da aplicação em desktop 1440
e mobile 390, claro/escuro: Home, Caixa, Oportunidades, Resumo, Vendas, Clientes,
Produtos, Financeiro, Automações, Assistente, Relatórios e Configurações.
São 48 estados de módulos mais as telas de entrada, sem overflow ou pageerror.
O onboarding e fluxos completos usam a suíte de regressão existente, com perfis
sintéticos e matrizes próprias; não foi repetida pesquisa de referências.

## Problemas comprovados e correções

| Evidência / efeito                                                                       | Mudança                                                             | Verificação                                                                                           |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| clearAnalysis instalava click/keydown novamente, criando 16 registros após oito chamadas | Eventos apenas na inicialização                                     | Teste reproduziu falha antes; zero registros na limpeza depois; ciclos de demo/resolução no navegador |
| Cards de análise ocupavam a largura inteira no desktop                                   | Duas colunas, alinhadas pelo topo, uma coluna abaixo de 1000 px     | 12 layouts; evidências P0 antes/depois preservadas                                                    |
| Análise avulsa sempre expandida competia com o fluxo de clientes                         | Recurso complementar recolhível                                     | Acesso ao formulário, validação, foco e análise preservados                                           |
| Cinco abas de Negócio parcialmente cortadas no mobile, sobretudo Financeiro              | Grade 3+2 com alvos de 44 px e rótulos de 14 px                     | Teste verifica geometria das cinco abas e abre Financeiro pelo botão real em 320/390                  |
| Falta de ferramenta de preparação de divulgação                                          | Estúdio em Ferramentas com editor/prévia, sem sobrecarregar sidebar | Três formatos, mídia local, rascunhos, validação e testes dedicados                                   |

A navegação de Negócio mantém o indicador deslizante desktop. No celular, o fundo
ativo de cada botão fornece seleção/feedback, sem posicionar o indicador na linha
errada. Oportunidades mantém indicador animado, teclado e preferências de movimento.

## Mantido após inspeção

Landing/onboarding, hierarquia da Home, Caixa lista → conversa, estados vazios do
Assistente, organização de Automações, Relatórios e Configurações foram preservados.
Espaço de um estado vazio que orienta uma ação é intencional; não foi preenchido
com métricas, registros ou cards inventados. Não foram alteradas regras financeiras.

A primeira tentativa do CI P0 falhou numa medição de altura monetária em Financeiro
1600/dark. A suíte visual específica passou localmente sem mudar Financeiro. O job
foi repetido uma vez; o resultado final fica registrado na PR, sem remover a asserção.
