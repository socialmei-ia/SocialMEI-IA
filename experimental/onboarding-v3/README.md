# Rodada atual — composição da etapa Negócio

A composição vertical desta rodada foi aprovada e integrada ao onboarding oficial na branch de desenvolvimento. Veja [a integração e os testes nativos](../../docs/ONBOARDING-BUSINESS-NATIVE.md). **Publicação ainda depende de autorização específica.** Esta pasta e o ZIP permanecem como registro da avaliação do protótipo.

Consulte [BUSINESS-LAYOUT.md](BUSINESS-LAYOUT.md) para o diagnóstico, capturas, testes e limites desta proposta. A URL local continua `/experimental/onboarding-v3/`: use **Usar exemplo → Continuar** para chegar à etapa Negócio. Os dados ficam em memória.

A documentação abaixo registra a entrega anterior do protótipo V3. Seus estados de PR/aprovação e capturas são históricos; a PR #57 já foi incorporada à main antes desta rodada.

---

# Onboarding V3 — avaliação visual e interativa

Protótipo isolado conforme `docs/PROJECT-STRUCTURE.md`, na mesma branch experimental `feat/socialmei-native-integration` (PR #57, Draft). Base oficial inspecionada: `7a9d73a`. **Não substitui o onboarding de `frontend/socialmei-app.html`. Aguarda aprovação visual explícita antes de qualquer integração.**

## Abrir a prévia

Na raiz do repositório, sem build ou instalação adicional:

```sh
python3 -m http.server 5500 --bind 127.0.0.1
```

Abra **http://127.0.0.1:5500/experimental/onboarding-v3/**. Acesse pelo servidor, não por `file://`, para carregar corretamente os recursos compartilhados. O endereço é local; não foi publicado um site.

Clique em **Usar exemplo** na primeira etapa para preencher nome/e-mail demonstrativos. Escolha uma atividade, combine produtos e serviços, experimente as preferências e revise. O botão de tema alterna claro/escuro; **Reiniciar** pede confirmação e limpa somente esta demonstração.

## O que mudou em cada etapa

| Etapa       | Antes, no diagnóstico da interface oficial                                   | V3 isolada                                                                                                                                      |
| ----------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Você        | Avisos repetidos e ação principal distante no celular                        | Introdução editorial, campos enxutos, feedback contextual e ação visível no rodapé                                                              |
| Negócio     | Detalhes opcionais competiam com a atividade principal                       | Seis áreas visuais, 23 especialidades do catálogo existente, busca e seleção progressiva; detalhes recolhidos                                   |
| Ofertas     | Seleção pouco diferenciada e inclusão manual por texto separado por vírgulas | Serviços e categorias de produtos separados, seleção múltipla e inclusão individual com Enter ou botão                                          |
| Rotina      | Nove escolhas com tratamento visual repetitivo                               | Grupos de atendimentos, pedidos/entregas e estrutura; perguntas condicionais preservadas                                                        |
| Ferramentas | Muitas opções pré-selecionadas, incluindo futuras                            | Sugestões iniciais apenas de módulos disponíveis; interesses futuros separados; prévia ilustrativa sem módulos futuros apresentados como ativos |
| Revisão     | Editar exigia percorrer novamente etapas intermediárias                      | Resumo por seção, edição direta e retorno à revisão; conclusão explicitamente demonstrativa                                                     |

Não são seis cópias do mesmo formulário: entrada editorial, descoberta progressiva, seleção por grupos, listas operacionais, composição de ferramentas e resumo têm organizações próprias. Azul, amarelo, fonte Inter e tokens da aplicação foram reaproveitados. No celular, as escolhas de ferramentas aparecem **antes** da prévia.

## Demonstração dos estados

1. Tente continuar com nome/e-mail vazios: mensagem ligada ao campo e foco no primeiro erro.
2. Em Negócio, busque uma atividade inexistente: estado sem resultados e alternativa para descrever outra atividade. Apague a busca para explorar as seis áreas.
3. Escolha Barbearia e marque também produtos: Ofertas e Rotina se adaptam, sem limitar o negócio à profissão.
4. Marque serviços/categorias e adicione uma opção personalizada. Nada é cadastrado no catálogo.
5. Em Ferramentas, expanda **Para o futuro**: registrar interesse não disponibiliza Agenda, entregas ou equipe. Selecionar WhatsApp também não conecta canal.
6. Na Revisão, use **Editar**, altere uma escolha e **Aplicar e voltar à revisão**. Campos obrigatórios continuam protegidos na navegação não linear.
7. Conclua a demonstração ou abra Reiniciar. O diálogo aceita Escape, mantém foco interno e devolve o foco ao controle de origem.

O stepper distingue atual/concluídas e permite revisitar etapas. Transições direcionais usam saída de 160 ms e entrada de 180 ms, com deslocamento de 8 px; progresso usa 320 ms. A revelação de especialidades dura 180 ms e ocorre ao escolher uma área, sem repetir a animação a cada caractere da busca. `prefers-reduced-motion` elimina essas animações. O tema inicial acompanha o sistema antes da primeira pintura e pode ser alternado sem persistência.

## Dados e isolamento

- Toda resposta fica **somente na memória desta página**. Atualizar/fechar perde o preenchimento; saída com alterações não concluídas solicita a confirmação nativa do navegador quando permitida por ele.
- Não cria conta, autentica, salva perfil, cadastra produtos ou escreve em `localStorage`/`sessionStorage`.
- Reutiliza funções puras, catálogo e capacidades de `frontend/scripts/business-profile.js`; não chama seu repositório de persistência. Reutiliza validação/formatação de contato e tokens oficiais.
- Nenhum fetch/API, conexão WhatsApp ou processamento remoto. CSP bloqueia conexões e envio de formulários.
- Canais, prioridade e dados adicionais são metadados em memória para avaliação da experiência, sem novo contrato de backend.
- Exemplo preenchido é fictício. Não há preços, estoque, clientes ou vendas inventados.

## Verificação executada

```sh
CHROMIUM_EXECUTABLE=/usr/bin/chromium node tests/onboarding-v3-browser.cjs
node --test tests/business-profile.test.cjs tests/repository.test.cjs
```

- **84 estados de layout passaram:** seis etapas e conclusão, nas larguras 320/360/390/768/1024/1440, nos dois temas. Rodapé e campos finais alcançáveis, sem overflow horizontal.
- **Seis cenários passaram:** negócio misto, barbearia, perfumaria, costura, assistência de celulares e outro segmento. Incluem perguntas condicionais, opcionais, revisão, edição e conclusão.
- Exercitados teclado (radios, Space/Enter, Escape), foco na transição/erro, movimento normal/reduzido, navegação não linear, reset durante transição, limite de 30 escolhas, texto longo, conteúdo HTML tratado como texto e diálogo em viewport 320×480.
- Zero erros JavaScript, requisições externas/APIs ou gravações de perfil; marcador de armazenamento oficial preservado.
- **25 testes Node passaram** para modelo compartilhado e integridade do repositório. Sintaxe, formatação dos arquivos novos e `git diff --check` verificados.
- Revisor frontend: corrigidos desvio de validação pelo stepper, navegação após conclusão, corrida com reset, limite de seleções e divergência de formatação do Instagram. Releitura favorável.
- Revisor anti-ui-slop: **PASS** após colocar escolhas antes da prévia de ferramentas no mobile; revisão das seis etapas em desktop/mobile e nos dois temas.

Os números são da execução local com Chromium. Não equivalem a certificação WCAG, teste de leitor de tela ou dispositivos físicos. Não houve teste de backend/produção nem suíte completa da aplicação: nenhum arquivo oficial foi alterado. Integração futura deve incluir testes do fluxo oficial, persistência e sessão.

## Capturas reais

Capturas de viewport, sem composição artificial, com dados fictícios. Conteúdo abaixo da dobra continua acessível por rolagem. As colunas abrem imagens em 1440×900 ou 390×900.

| Etapa       | Desktop claro                                      | Desktop escuro                                    | Mobile claro                                      | Mobile escuro                                    |
| ----------- | -------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------ |
| Você        | [Abrir](screenshots/01-voce-1440-light.png)        | [Abrir](screenshots/01-voce-1440-dark.png)        | [Abrir](screenshots/01-voce-390-light.png)        | [Abrir](screenshots/01-voce-390-dark.png)        |
| Negócio     | [Abrir](screenshots/02-negocio-1440-light.png)     | [Abrir](screenshots/02-negocio-1440-dark.png)     | [Abrir](screenshots/02-negocio-390-light.png)     | [Abrir](screenshots/02-negocio-390-dark.png)     |
| Ofertas     | [Abrir](screenshots/03-ofertas-1440-light.png)     | [Abrir](screenshots/03-ofertas-1440-dark.png)     | [Abrir](screenshots/03-ofertas-390-light.png)     | [Abrir](screenshots/03-ofertas-390-dark.png)     |
| Rotina      | [Abrir](screenshots/04-rotina-1440-light.png)      | [Abrir](screenshots/04-rotina-1440-dark.png)      | [Abrir](screenshots/04-rotina-390-light.png)      | [Abrir](screenshots/04-rotina-390-dark.png)      |
| Ferramentas | [Abrir](screenshots/05-ferramentas-1440-light.png) | [Abrir](screenshots/05-ferramentas-1440-dark.png) | [Abrir](screenshots/05-ferramentas-390-light.png) | [Abrir](screenshots/05-ferramentas-390-dark.png) |
| Revisão     | [Abrir](screenshots/06-revisao-1440-light.png)     | [Abrir](screenshots/06-revisao-1440-dark.png)     | [Abrir](screenshots/06-revisao-390-light.png)     | [Abrir](screenshots/06-revisao-390-dark.png)     |
| Conclusão   | [Abrir](screenshots/07-concluido-1440-light.png)   | [Abrir](screenshots/07-concluido-1440-dark.png)   | [Abrir](screenshots/07-concluido-390-light.png)   | [Abrir](screenshots/07-concluido-390-dark.png)   |

Estados adicionais: [validação](screenshots/estado-validacao-390-light.png), [busca sem resultados](screenshots/estado-busca-vazia-390-dark.png), [recursos futuros](screenshots/estado-recursos-futuros-390-dark.png), [confirmação de reinício](screenshots/estado-reiniciar-320-dark.png).

## Arquivos desta entrega

Criados `experimental/onboarding-v3/index.html`, `onboarding.css`, `onboarding.js`, `theme.js`, este guia, `screenshots/*.png`, `screenshots/summary.json` e `tests/onboarding-v3-browser.cjs`. Nenhum arquivo da aplicação oficial foi modificado.

A próxima decisão é a aprovação visual deste protótipo. Migração ao onboarding oficial e conexão com sua persistência permanecem fora desta entrega.
