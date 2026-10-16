# Prévia de desenvolvimento do SocialMEI.IA

Entrada única: `prototypes/index.html`. Os protótipos estão fora de `frontend/` e da imagem do gateway. Não são destinos da navegação principal nem prova de funcionalidades publicadas.

## Abrir e experimentar

Na raiz do checkout desta branch:

```sh
python -m http.server 5500 --bind 127.0.0.1
```

No mesmo computador, abrir `http://127.0.0.1:5500/prototypes/`. Se seu Python usa o nome `python3`, substitua o comando. Esse endereço local não é um link público para a equipe. Não é necessário Docker, API, banco, chave de IA ou deploy.

| Experiência                | Caminho                               | O que experimentar                                                                                                                                                                 |
| -------------------------- | ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Aplicação experimental     | `frontend/socialmei-app.html`         | Entrar no modo demonstrativo local. Relatórios compacto, rascunhos na Caixa, edição do Assistente e clareza das simulações. A aplicação mantém seus modos local/remoto existentes. |
| Referência de Relatórios A | `prototypes/reports/index.html`       | Dois períodos fictícios, comparação, gráfico/tabela, privacidade e estados. É uma referência simplificada, não o renderer integrado.                                               |
| Oportunidades              | `prototypes/opportunities/index.html` | Analisar mensagens fictícias novas, conferir trechos e ressalvas, comparar resultados e abrir contextos fictícios. Biblioteca manual preservada.                                   |
| Onboarding adaptativo      | `prototypes/onboarding/index.html`    | Escolher um de cinco segmentos ou “Outro tipo de negócio”, ajustar produtos/serviços/estoque/agendamentos/canais/equipe/área, revisar e baixar JSON.                               |

## Decisões e limites

- **Aplicação:** cálculos, stores, APIs, filtros e exportações existentes foram preservados. Não há envio externo novo. Rascunho de conversa é memória da sessão; resposta local e nota usam a persistência local existente. O editor do Assistente salva no histórico local já existente, sem IA remota.
- **Oportunidades:** agora executa análise automática local e determinística sobre o texto informado, com classificação provisória, evidências literais, ressalvas e comparação de até três mensagens. Não é IA treinada nem calcula probabilidade de venda. Os seis exemplos anteriores continuam numa biblioteca manual independente, recolhida inicialmente. Contrato, critérios e limites: [README da análise](opportunities/README.md).
- **Contexto de oportunidade:** conversa e Cliente 360 são painéis ilustrativos dentro da própria prévia. Não abrem nem modificam o atendimento/CRM reais. Alterações de etapa e rascunhos são descartados ao recarregar ou reiniciar.
- **Onboarding:** aplica `CORE + BUSINESS PROFILE + CAPABILITIES + DEFAULTS`. O núcleo comum permanece Clientes/Vendas/Financeiro/Relatórios. O perfil sugere capacidades que o usuário pode ajustar. Trocar de segmento reaplica as sugestões iniciais. Agendamentos são identificados como planejados. O JSON tem `demo: true` e `integrationsEnabled: false`; não existe importador no cadastro real.
- **Isolamento:** as duas novidades não usam stores do aplicativo, localStorage, autenticação, APIs ou bibliotecas externas. A fonte é o asset Inter local existente.
- **Identidade:** tipografia Inter, superfícies claras/azuis escuras, ação azul, detalhe dourado; sem novo framework, efeito decorativo contínuo ou dependência.

## Testes e capturas

```sh
npm test
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:intent
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser
CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:development
npm run format:check
```

Omita a variável `CHROMIUM_EXECUTABLE` se usar o Chromium instalado pelo Playwright. No Windows, configure a variável de ambiente pelo mecanismo do seu terminal, se necessária. A nova suíte também roda no job de navegador do CI, sem permissões adicionais. O artifact `development-preview` reúne `prototypes/` e `frontend/`; extraia o ZIP e sirva a pasta extraída com o mesmo comando. O artifact `frontend-regression` contém as capturas. A disponibilidade depende de o CI dessa PR executar e publicar os artifacts.

`test-results/autonomous/` contém capturas desktop 1440/mobile 390 nos temas claro/escuro, além de detalhes de Oportunidades e revisão de onboarding. Prefixos `app-0`, `app-1`, `app-2` e `app-3` correspondem a Relatórios, Caixa, Assistente e Automações. Os dados são fictícios.

`test-results/purchase-intent/` contém as capturas da análise funcional: desktop/mobile, claro/escuro, comparação, contexto fictício e estado vazio.

A aprovação final de UX/visual e a integração em `main` continuam separadas. A autorização desta rodada cobre desenvolvimento experimental na branch. Nada neste diretório autoriza publicação ou ativação de serviços.
