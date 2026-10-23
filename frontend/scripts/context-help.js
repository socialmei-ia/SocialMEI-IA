/* Contextual guidance only. Reuses native navigation, dialogs and focus management. */
const SocialMEIContextHelp = (() => {
  const topics = {
    Início: {
      intro: "Escolha um próximo passo para cuidar do seu negócio.",
      sections: [
        [
          "Atalhos e prioridades",
          "A busca abre ações existentes. As prioridades e vendas recentes usam os registros disponíveis; um espaço vazio orienta o primeiro cadastro.",
        ],
        [
          "Um espaço adaptado ao seu negócio",
          "Edite seu perfil em Configurações para priorizar ferramentas e sugestões. Sugestões não são produtos ou serviços cadastrados automaticamente.",
        ],
      ],
    },
    "Caixa Unificada": {
      intro: "Encontre uma conversa, leia o contexto e prepare sua resposta.",
      sections: [
        [
          "Lista e contexto do cliente",
          "Busque, filtre ou ordene as conversas. Abra uma pessoa para ver mensagens e o painel Cliente. No celular, use Voltar para retornar à lista sem perder o rascunho.",
        ],
        [
          "Rascunho e envio são diferentes",
          "Salvar uma resposta local não envia ao WhatsApp ou Instagram. Confira a indicação junto ao compositor e o estado da integração antes de qualquer ação.",
        ],
      ],
    },
    Oportunidades: {
      intro: "Acompanhe negociações e revise o contexto antes de agir.",
      sections: [
        [
          "Lista, Quadro e Semana",
          "Use a lista para editar e consultar a auditoria. No Quadro, arraste as fichas ou use as setas para mudar o interesse. Na Semana, selecione uma pessoa e depois um dia para remarcar o retorno.",
        ],
        [
          "CRM e planejamento local",
          "Interesse, encerramento, reabertura e vínculo de venda usam o negócio autenticado. Valor estimado, anotação e retorno ficam só neste navegador e não sincronizam nem alteram vendas. Sem backend, o acompanhamento é somente leitura.",
        ],
        [
          "Atalhos e retornos",
          "Use / para buscar, N para uma nova oportunidade e Ctrl+K para comandos. Em Opções da análise você pode copiar os retornos de hoje; isso não envia mensagens.",
        ],
        [
          "Em análise, Chance de fechar e Atenção",
          "Em análise reúne necessidades indefinidas. Quente, Morno e Frio são níveis qualitativos por regras locais, não probabilidades de venda. Atenção separa suporte e situações urgentes da fila comercial.",
        ],
        [
          "Revisão humana e próximos passos",
          "Abra Ver conversa para ler os trechos literais e revisar a recomendação. A classificação manual e a resolução de alertas valem nesta sessão; não alteram o CRM nem enviam mensagens.",
        ],
      ],
    },
    "Visão Geral": {
      intro: "Confira o que merece atenção e siga para o registro correspondente.",
      sections: [
        [
          "Prioridades e indicadores",
          "As prioridades vêm dos registros disponíveis. Abrir uma venda ou cliente permite conferir os detalhes. Ausência de dados não significa faturamento ou atividade zero de uma fonte indisponível.",
        ],
      ],
    },
    Vendas: {
      intro: "Registre e acompanhe suas vendas, sem confundir pagamento com entrega.",
      sections: [
        [
          "Cadastrar, filtrar e conferir",
          "Use Nova venda e confirme os campos antes de salvar. Filtros e busca restringem a lista. O menu da linha oferece as ações compatíveis com o estado da venda.",
        ],
        [
          "Situação da venda",
          "Uma venda paga pode entrar no faturamento; isso não confirma entrega. Cancelamento e alterações de estoque seguem as regras existentes e exigem confirmação quando aplicável.",
        ],
      ],
    },
    Clientes: {
      intro: "Organize contatos e consulte o contexto de cada relacionamento.",
      sections: [
        [
          "Consultar e editar",
          "Use a busca e os filtros para encontrar uma pessoa. Abra o cadastro para consultar informações disponíveis. Mudanças só são registradas após a confirmação no formulário.",
        ],
      ],
    },
    "Produtos e Serviços": {
      intro: "Cadastre o que você vende ou oferece, com preços definidos por você.",
      sections: [
        [
          "Sugestões e catálogo",
          "Sugestões do perfil abrem o formulário nativo; nada é cadastrado automaticamente. Produto físico e serviço são tipos distintos. Estoque só se aplica quando o tipo e os dados permitem.",
        ],
      ],
    },
    Financeiro: {
      intro: "Acompanhe entradas, saídas e vencimentos registrados.",
      sections: [
        [
          "Faturamento não é movimentação financeira",
          "Vendas e lançamentos são fontes distintas. Confira recebimentos e despesas no Financeiro sem somar novamente o faturamento das vendas.",
        ],
        [
          "Saldo acumulado e período",
          "Saldo acumulado até hoje considera entradas pagas menos saídas pagas nos registros disponíveis. Não é uma consulta ao saldo bancário. Os indicadores do período respeitam o filtro selecionado.",
        ],
      ],
    },
    Relatórios: {
      intro: "Compare o resultado dos registros disponíveis e confira sua origem.",
      sections: [
        [
          "Períodos e comparações",
          "Selecione um período rápido ou um intervalo personalizado. Sem histórico anterior suficiente, a comparação fica indisponível. Vendas pagas e movimentação financeira não são somadas em duplicidade.",
        ],
        [
          "Exportações e histórico",
          "CSV e as opções de PDF/impressão usam os dados do relatório. A origem fica identificada na exportação. O histórico local é separado por identidade e negócio e não sincroniza entre dispositivos.",
        ],
      ],
    },
    Automações: {
      intro: "Organize rotinas e confira o resultado de um teste local.",
      sections: [],
    },
    Assistente: {
      intro: "Prepare um rascunho e revise antes de utilizá-lo.",
      sections: [
        [
          "Sugestão não é envio",
          "As sugestões disponíveis são locais. Inserir um rascunho na Caixa não envia uma mensagem. As indicações junto à ação mostram o que está disponível nesta sessão.",
        ],
      ],
    },
    Divulgação: {
      intro: "Prepare um conteúdo, confira o formato e organize seus rascunhos.",
      sections: [
        [
          "Story, Feed e Reel",
          "Escolha o formato e selecione uma imagem ou vídeo local para conferir o enquadramento. A prévia não edita nem incorpora o texto ao arquivo original.",
        ],
      ],
    },
    Configurações: {
      intro: "Ajuste o perfil do negócio e as preferências deste espaço.",
      sections: [
        [
          "Perfil e ferramentas",
          "Edite as respostas do onboarding sem refazer a conta. Ferramentas priorizam atalhos e sugestões; módulos essenciais continuam acessíveis. O perfil adaptativo ainda é local.",
        ],
        [
          "Dados de teste e armazenamento",
          "Usar dados de teste mostra uma amostra fictícia separada dos registros originais. Desative para voltar aos seus dados. A origem e a sincronização dos registros dependem da configuração da sessão; confira Sessão e armazenamento.",
        ],
      ],
    },
  };
  const moved = [];
  const get = (id) => document.getElementById(id);
  function render() {
    const topic = topics[currentView] || topics.Início;
    get("contextHelpTitle").textContent = "Ajuda · " + currentView;
    get("contextHelpIntro").textContent = topic.intro;
    get("contextHelpSections").replaceChildren();
    for (const [title, text] of topic.sections) {
      const details = document.createElement("details"),
        summary = document.createElement("summary"),
        paragraph = document.createElement("p");
      details.className = "help-topic";
      summary.textContent = title;
      paragraph.textContent = text;
      details.append(summary, paragraph);
      get("contextHelpSections").append(details);
    }
    moved.forEach(({ node, view }) => (node.hidden = currentView !== view));
    get("contextHelpSources").hidden = !moved.some(({ view }) => view === currentView);
  }
  function position() {
    const button = get("contextHelpButton"),
      host = get("utilityTools");
    if (currentView === "Caixa Unificada" && innerWidth > 900) {
      const heading = document.querySelector(".inbox-title-line");
      if (button.parentElement !== heading) heading.append(button);
    } else if (button.parentElement !== host.parentElement) host.before(button);
  }
  document.addEventListener("DOMContentLoaded", () => {
    for (const [view, selector] of [
      ["Início", ".home-source-help"],
      ["Oportunidades", ".native-opportunity-criteria"],
      ["Divulgação", ".content-local-note"],
      ["Automações", "#automationsView > .management-stack > .context-help"],
    ]) {
      const node = document.querySelector(selector);
      if (node) {
        get("contextHelpSources").append(node);
        moved.push({ view, node });
      }
    }
    position();
    document.addEventListener("click", (event) => {
      if (event.target.closest("#contextHelpButton")) {
        render();
        get("utilityTools").open = false;
        document
          .querySelectorAll("#viewDemoControl[open],.opportunity-options[open]")
          .forEach((details) => (details.open = false));
        openModal("contextHelpModal");
      }
    });
    document.addEventListener("socialmei-view-change", () => {
      position();
      if (get("contextHelpModal").classList.contains("open")) render();
    });
    window.addEventListener("resize", position, { passive: true });
  });
  return Object.freeze({ render });
})();
