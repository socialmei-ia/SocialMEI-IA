# Tapioca Valley — demonstração supervisionada (~5 minutos)

Branch `demo/tapioca-valley`, baseada em `feat/local-purchase-intent` no commit `37655e5` da PR #55, que depende de `reports-v1-prototype` (PR #54). Alterações isoladas em protótipos, documentação e testes; V1 e serviços reais preservados. Sem merge ou deploy.

## Abrir a prévia

No checkout desta branch, na raiz do repositório:

```sh
python3 prototypes/tapioca-valley/preview.py
```

O comando usa somente a biblioteca padrão do Python 3, inicia um servidor estático em `127.0.0.1` numa porta livre e abre o hub no navegador. Clique em **Começar demonstração**. Encerre com Ctrl+C. No Windows, pode usar `py` em lugar de `python3`. Com `--no-browser`, o comando apenas imprime o endereço para abrir manualmente. Nenhuma instalação npm, Docker, credencial ou serviço é necessária para apresentar.

Alternativa: `python3 -m http.server 5500 --bind 127.0.0.1` e abrir `http://127.0.0.1:5500/prototypes/`. O endereço é local ao computador; não é publicação nem link de acesso remoto.

## Um cenário do início ao fim

**Perfumaria Aurora**, negócio fictício em Fortaleza, com três clientes já existentes na prévia #55. A Caixa ilustrativa, os exemplos da análise e a fila consomem o mesmo recorte de `opportunities/priority-scenario.js`, sem duplicar as conversas. Referência fixa: 16/10/2026, 09h em Fortaleza (12h UTC).

| Cliente       | Conversa que orienta a demonstração                      | Resultado esperado                                               |
| ------------- | -------------------------------------------------------- | ---------------------------------------------------------------- |
| Ana Ribeiro   | Preço do 212 VIP, pronta entrega e entrega hoje          | Intenção elevada provisória; acompanhar primeiro                 |
| Diego Lima    | Quer Malbec, mas não quer comprar agora e considera caro | Sinais conflitantes; esclarecer a decisão                        |
| Gabriela Melo | Comprou antes, entrega não chegou e precisa de suporte   | Sem intenção nova suficiente; atendimento fora da fila comercial |

As telas originais continuam acessíveis sem `?tour=tapioca-valley`. O roteiro fixa o perfil de perfumaria e esconde a biblioteca manual de outros contatos. Alterar capacidades do onboarding não modifica clientes nem configura uma conta. Editar a análise avulsa não altera a conversa ou a fila; para experimentar mudança de conversa, use o campo próprio em **Ver conversa**. Dados e revisões ficam em memória da página, sem sincronização entre páginas ou persistência: recarregar, sair ou reiniciar descarta mudanças. Não abra as etapas em várias abas esperando compartilhar alterações.

## Roteiro de apresentação

| Tempo     | Navegação e ação                                                                                                                                                                              | Fala sugerida                                                                                                                                                                                                       |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0:00–0:30 | Hub → **Começar demonstração**                                                                                                                                                                | “Vamos acompanhar uma perfumaria fictícia. As regras e a revisão funcionam localmente; mensagens e canais são ilustrativos.”                                                                                        |
| 0:30–1:15 | Onboarding: continuar com Perfumaria, conferir produtos/estoque e prévia → **Continuar para as conversas ilustrativas**                                                                       | “O núcleo do SocialMEI é comum; o perfil sugere uma organização. Selecionar WhatsApp não conecta nenhum canal e a prévia não cria conta.”                                                                           |
| 1:15–2:00 | Abrir as três conversas na Caixa ilustrativa                                                                                                                                                  | “Ana busca produto e entrega. Diego tem uma objeção. Gabriela precisa de atendimento, não de outra oferta.”                                                                                                         |
| 2:00–3:15 | **Analisar a mensagem de Ana** → **Analisar intenção**. Usar o seletor para Diego e Gabriela e analisar cada um                                                                               | “Os motivos vêm de trechos literais. Ana tem sinais comerciais; Diego precisa esclarecer; em Gabriela não há informação suficiente para uma nova compra. Isso não diminui a importância do suporte.”                |
| 3:15–4:00 | **Continuar para a fila e a revisão humana** → abrir Ana e Gabriela                                                                                                                           | “A lista sugere quem acompanhar comercialmente; suporte fica em outro encaminhamento. Não há porcentagem nem venda garantida. A janela de 24 horas é experimental.”                                                 |
| 4:00–5:00 | Ana → revisão **Esclarecer decisão**, motivo “Prefiro confirmar o prazo com Ana antes de avançar.” → **Aplicar revisão local** → fechar e observar Diego antes de Ana → **Reiniciar cenário** | “A recomendação original permanece visível. O empreendedor pode discordar e mudar o encaminhamento. Nada foi enviado ao cliente. Integrar canais e histórico reais será uma etapa separada, autorizada e validada.” |

## O que apresentar como funcional, ilustrativo ou futuro

- **Funciona nesta prévia:** escolhas e JSON do onboarding; análise determinística de texto informado; evidências e limitações; fila calculada das conversas; revisão com justificativa, reordenação e restauração. As heurísticas e os riscos da [avaliação comercial](../../docs/COMMERCIAL-LOGIC-EVALUATION.md) continuam válidos.
- **Ilustrativo:** perfumaria, clientes, conteúdo e recebimento das mensagens; Caixa contextual e navegação entre módulos. É um roteiro integrado por links e cenário comum, não uma integração da Caixa/CRM reais.
- **Futuro:** aplicar perfil a uma conta, ingestão autorizada de conversas, histórico real, validação de estoque/preço/pagamento, envio por canais e configuração da janela por negócio. Nada disso é ativado por esta demonstração.

## Testes e capturas

```sh
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:tour
```

Omita a variável para usar o Chromium do Playwright. O teste percorre todo o roteiro em 320, 390 e 1440 px, claro/escuro; verifica mesmos clientes/mensagens, resultados distintos, fila, suporte, revisão/reordenação, temas nas transições, isolamento de rede e as prévias originais fora do roteiro. A suíte é chamada também pelo teste de desenvolvimento existente. Capturas completas ficam em `test-results/tapioca-valley/`.

Capturas selecionadas: [fila desktop clara](captures/queue-1440-light.png), [fila desktop escura](captures/queue-1440-dark.png), [fila mobile clara](captures/queue-390-light.png), [fila mobile escura](captures/queue-390-dark.png), [onboarding](captures/onboarding-1440-dark.png), [conversas](captures/inbox-1440-light.png), [análise](captures/intent-390-dark.png) e [revisão humana](captures/review-390-light.png).
