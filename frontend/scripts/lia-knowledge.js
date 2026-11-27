/* SocialMEI-IA · v7.7 · Lia — catálogo de telas, formulários e guias do aplicativo.
   Só descreve o que existe em socialmei-app.html (rotas #/…, openAction e telas de Configurações). Nada é inventado:
   cada entrada aponta para uma rota ou ação já existente. Textos de passo a passo são orientações, não confirmações. */
(() => {
  "use strict";
  if (window.SocialMEILiaKB) return;
  const nvLink = (r) => `aside a.nv[href="#/${r}"]`;
  const screens = [
    { id: "inicio", title: "Início · Meu dia", path: "/inicio", hint: "Pendências e prioridades do dia", kw: ["inicio", "meu dia", "painel", "home", "hoje", "pagina inicial", "tela inicial", "resumo do dia"], where: [nvLink("inicio")] },
    { id: "caixa", title: "Caixa Unificada", path: "/caixa", hint: "Conversas de WhatsApp e Instagram", kw: ["caixa", "caixa unificada", "conversas", "mensagens", "atendimento", "responder cliente", "inbox", "direct", "chat"], where: [nvLink("caixa")] },
    { id: "oport", title: "Oportunidades", path: "/oport", hint: "Quem pode virar venda", kw: ["oportunidades", "oportunidade", "leads", "interessados", "fechar venda", "quem pode comprar", "funil"], where: [nvLink("oport")] },
    { id: "divul", title: "Divulgação", path: "/divul", hint: "Preparar divulgações", kw: ["divulgacao", "divulgar", "postagem", "post", "campanha", "promocao", "anuncio", "publicar", "instagram post"], where: [nvLink("divul")] },
    { id: "resumo", title: "Negócio · Resumo", path: "/negocio/resumo", hint: "Visão geral do negócio", kw: ["negocio", "resumo do negocio", "visao geral", "meu negocio"], where: [nvLink("negocio")] },
    { id: "vendas", title: "Vendas", path: "/negocio/vendas", hint: "Registros e pagamentos", kw: ["vendas", "venda", "vendi", "pedidos", "pagamentos", "recebimentos", "historico de vendas"], where: [nvLink("negocio"), '.tabs a[href="#/negocio/vendas"]'] },
    { id: "clientes", title: "Clientes", path: "/negocio/clientes", hint: "Cadastro e histórico de clientes", kw: ["clientes", "cliente", "contatos", "crm", "cadastro de clientes", "carteira"], where: [nvLink("negocio"), '.tabs a[href="#/negocio/clientes"]'] },
    { id: "produtos", title: "Produtos e serviços", path: "/negocio/produtos", hint: "Preços, custos e estoque", kw: ["produtos", "produto", "servicos", "servico", "estoque", "preco", "precos", "mercadoria", "itens", "inventario"], where: [nvLink("negocio"), '.tabs a[href="#/negocio/produtos"]'] },
    { id: "financeiro", title: "Financeiro", path: "/negocio/financeiro", hint: "Entradas, saídas e saldo", kw: ["financeiro", "dinheiro", "entradas", "saidas", "despesas", "lucro", "contas", "fluxo de caixa", "saldo", "gastos"], where: [nvLink("negocio"), '.tabs a[href="#/negocio/financeiro"]'] },
    { id: "agenda", title: "Agenda", path: "/agenda", hint: "Compromissos e horários", kw: ["agenda", "agendamentos", "agendamento", "compromissos", "horarios", "marcar horario", "calendario", "reunioes"], where: [nvLink("agenda")] },
    { id: "catalogo", title: "Catálogo", path: "/catalogo", hint: "Vitrine para enviar aos clientes", kw: ["catalogo", "vitrine", "loja virtual", "link de produtos"], where: [nvLink("catalogo")] },
    { id: "automacoes", title: "Automações", path: "/automacoes", hint: "Rotinas do negócio", kw: ["automacoes", "automacao", "rotinas", "rotina", "automatico", "automatizar", "lembretes automaticos"], where: [nvLink("automacoes")] },
    { id: "relatorios", title: "Relatórios", path: "/relatorios", hint: "Números do negócio por período", kw: ["relatorios", "relatorio", "graficos", "numeros", "desempenho", "indicadores", "analise"], where: [nvLink("relatorios")] },
    { id: "cfg-negocio", title: "Configurações · Dados do negócio", path: "/config/negocio", hint: "Nome, segmento e contato", kw: ["dados do negocio", "nome do negocio", "segmento", "contato comercial", "descricao do negocio"], where: [nvLink("config"), '.cfg-it[href="#/config/negocio"]'] },
    { id: "cfg-perfil", title: "Configurações · Perfil e cor", path: "/config/perfil", hint: "Logo e cor do aplicativo", kw: ["perfil", "logo", "cor do app", "cor do aplicativo", "identidade visual", "minha marca"], where: [nvLink("config"), '.cfg-it[href="#/config/perfil"]'] },
    { id: "cfg-plano", title: "Configurações · Plano", path: "/config/plano", hint: "Plano e uso da IA", kw: ["plano", "meu plano", "uso da ia", "assinatura", "limite da ia"], where: [nvLink("config"), '.cfg-it[href="#/config/plano"]'] },
    { id: "cfg-equipe", title: "Configurações · Equipe", path: "/config/equipe", hint: "Quem acessa o negócio", kw: ["equipe", "colaboradores", "funcionarios", "convidar", "convite", "acesso de equipe", "permissoes"], where: [nvLink("config"), '.cfg-it[href="#/config/equipe"]'], manager: true },
    { id: "cfg-integracoes", title: "Configurações · Integrações", path: "/config/integracoes", hint: "WhatsApp, Instagram e canais", kw: ["integracoes", "integracao", "conectar", "conexoes", "canais", "whatsapp", "instagram", "conectar whatsapp", "conectar instagram"], where: [nvLink("config"), '.cfg-it[href="#/config/integracoes"]'] },
    { id: "cfg-ia", title: "Configurações · Perfil da IA", path: "/config/ia", hint: "Tom e regras das respostas", kw: ["perfil da ia", "tom das respostas", "regras da ia", "tom de voz", "jeito de responder"], where: [nvLink("config"), '.cfg-it[href="#/config/ia"]'] },
    { id: "cfg-notif", title: "Configurações · Notificações", path: "/config/notificacoes", hint: "O que avisar e quando", kw: ["notificacoes", "avisos", "alertas", "lembretes"], where: [nvLink("config"), '.cfg-it[href="#/config/notificacoes"]'] },
    { id: "cfg-conta", title: "Configurações · Minha conta", path: "/config/conta", hint: "Seus dados e negócios", kw: ["minha conta", "conta", "meus dados", "trocar de negocio", "meus negocios", "sair da conta", "senha"], where: [nvLink("config"), '.cfg-it[href="#/config/conta"]'] },
    { id: "cfg-aparencia", title: "Configurações · Aparência", path: "/config/aparencia", hint: "Tema e tamanho", kw: ["aparencia", "tema", "tema escuro", "tema claro", "modo escuro", "modo claro", "tamanho da letra", "fonte", "modo calmo", "menos movimento"], where: [nvLink("config"), '.cfg-it[href="#/config/aparencia"]'] },
    { id: "cfg-seguranca", title: "Configurações · Segurança e privacidade", path: "/config/seguranca", hint: "Sessões e privacidade", kw: ["seguranca", "privacidade", "sessoes", "lgpd", "protecao de dados"], where: [nvLink("config"), '.cfg-it[href="#/config/seguranca"]'] },
    { id: "ajuda", title: "Ajuda", path: "/ajuda", hint: "Perguntas frequentes", kw: ["ajuda", "suporte", "duvidas", "perguntas frequentes", "faq", "socorro"], where: ['aside a[href="#/ajuda"]'] },
    { id: "planos", title: "Planos e preços", path: "/planos", hint: "Comparar planos", kw: ["planos", "precos dos planos", "quanto custa", "mensalidade", "upgrade", "assinar"], where: ['aside a[href="#/planos"]'] },
    { id: "bemvindo", title: "Primeiros passos", path: "/bemvindo", hint: "Comece por aqui", kw: ["primeiros passos", "comecar", "por onde comeco", "tutorial inicial", "boas vindas", "inicio rapido"], where: [] },
  ];

  /* Formulários já existentes (openAction). A Lia só os ABRE; quem salva é o próprio formulário, com a confirmação dele. */
  const forms = [
    { id: "f-venda", action: "venda", title: "Registrar venda", hint: "Abre o formulário Nova venda", kw: ["registrar venda", "nova venda", "lancar venda", "fazer uma venda", "anotar venda", "vender", "vendi"], fields: [["c", /cliente/i], ["p", /produto/i], ["q", /quantidade/i], ["v", /valor/i], ["s", /pagamento/i]] },
    { id: "f-cliente", action: "cliente", title: "Cadastrar cliente", hint: "Abre o formulário Novo cliente", kw: ["cadastrar cliente", "novo cliente", "adicionar cliente", "criar cliente", "incluir cliente"], fields: [["n", /^nome/i], ["e", /e-?mail/i], ["o", /observa/i]] },
    { id: "f-produto", action: "produto", title: "Cadastrar produto ou serviço", hint: "Abre o formulário Novo produto ou serviço", kw: ["cadastrar produto", "novo produto", "cadastrar servico", "novo servico", "adicionar produto", "criar produto", "incluir produto"], fields: [["n", /^nome/i], ["t", /^tipo/i], ["c", /categoria/i], ["p", /pre[cç]o de venda/i], ["k", /custo|quanto voc/i], ["e", /estoque/i]] },
    { id: "f-lanc", action: "lanc", title: "Novo lançamento financeiro", hint: "Abre o formulário Novo lançamento", kw: ["novo lancamento", "lancamento", "lancar entrada", "lancar saida", "registrar despesa", "registrar gasto", "anotar despesa", "nova despesa", "nova entrada"], fields: [["d", /descri/i], ["c", /categoria/i], ["t", /^tipo/i], ["v", /valor/i]] },
    { id: "f-conversa", action: "conversa", title: "Nova conversa", hint: "Abre o formulário Nova conversa", kw: ["nova conversa", "iniciar conversa", "abrir conversa", "falar com cliente"], fields: [["n", /nome/i], ["k", /canal/i], ["m", /mensagem/i]] },
    { id: "f-rotina", action: "rotina", title: "Nova rotina", hint: "Abre o formulário Nova rotina", kw: ["nova rotina", "criar rotina", "nova automacao", "criar automacao"], fields: [["n", /nome/i], ["a", /[áa]rea/i], ["q", /quando/i]] },
  ];

  /* Orientações. Sempre dizem para conferir o estado real na própria tela. */
  const guides = {
    whatsapp: { id: "g-whatsapp", title: "Conectar o WhatsApp", kw: ["conectar whatsapp", "conecto meu whatsapp", "ligar whatsapp", "integrar whatsapp", "whatsapp conectar", "conexao whatsapp", "whatsapp"], path: "/config/integracoes", cta: "Abrir Integrações",
      steps: ["Abra Configurações › Integrações.", "Escolha o canal WhatsApp e siga as instruções da própria tela.", "Confira o estado da conexão na mesma tela: é ele que indica se o canal está pronto."],
      note: "A conexão depende da sua conta e do provedor. A Lia não conecta canais nem confirma a conexão; ela só leva você até lá." },
    instagram: { id: "g-instagram", title: "Conectar o Instagram", kw: ["conectar instagram", "conecto meu instagram", "ligar instagram", "integrar instagram", "instagram conectar", "conexao instagram"], path: "/config/integracoes", cta: "Abrir Integrações",
      steps: ["Abra Configurações › Integrações.", "Escolha o canal Instagram e siga as instruções da tela.", "Confira o estado da conexão ali antes de contar com ela na Caixa."],
      note: "A Lia não conecta canais por você nem confirma a conexão." },
    divulgacao: { id: "g-divulgacao", title: "Fazer uma divulgação", kw: ["fazer uma divulgacao", "como divulgar", "divulgacao como", "criar divulgacao", "preparar divulgacao", "divulgar produto", "fazer postagem"], path: "/divul", cta: "Abrir Divulgação",
      steps: ["Abra Divulgação e escolha o que quer divulgar (um produto, uma promoção ou uma novidade).", "Prepare o texto e revise com calma.", "Publicar é uma decisão sua: a Lia não publica nem envia nada."],
      note: "Salvar um rascunho não é publicar. Confira o texto e o canal antes de qualquer envio." },
    cobrar: { id: "g-cobrar", title: "Cobrar quem ainda não pagou", kw: ["cobrar cliente", "como cobrar", "cobranca", "quem nao pagou", "cobrar pendencias", "cobrar pendentes"], path: "/negocio/vendas", cta: "Ver vendas pendentes", filter: "Pendentes",
      steps: ["Veja as vendas pendentes (o botão abaixo já abre Vendas filtrada, quando a tela permite).", "Escolha a venda e use a ação de cobrança da própria tela ou do Meu dia.", "A cobrança só acontece quando você confirma lá."],
      note: "A Lia não envia cobranças." },
    primeiros: { id: "g-primeiros", title: "Primeiros passos", kw: ["comecar", "primeiros passos", "por onde comeco", "como comeco", "novo por aqui"], path: "/bemvindo", cta: "Abrir Primeiros passos",
      steps: ["Abra Primeiros passos e siga a lista.", "Cadastre pelo menos um produto ou serviço e um cliente.", "Depois volte ao Início: o Meu dia passa a mostrar o que merece atenção."], note: "" },
  };

  const suggestionsByRoute = {
    inicio: ["Organizar meu dia", "Mostrar vendas pendentes", "Quero cadastrar um cliente", "Como conecto meu WhatsApp?"],
    caixa: ["Quantas conversas esperam resposta?", "Como conecto meu WhatsApp?", "Nova conversa", "Ajuda desta tela"],
    oport: ["Organizar meu dia", "Quem está me devendo?", "Ajuda desta tela"],
    divul: ["Como faço uma divulgação?", "Cadastrar produto", "Ajuda desta tela"],
    negocio: ["Mostrar vendas pendentes", "Quanto tenho a receber?", "Registrar venda", "Ajuda desta tela"],
    "negocio/vendas": ["Mostrar vendas pendentes", "Quanto tenho a receber?", "Registrar venda", "Quem está me devendo?"],
    "negocio/clientes": ["Quero cadastrar um cliente", "Quem está me devendo?", "Registrar venda"],
    "negocio/produtos": ["Cadastrar produto", "Produtos com estoque baixo", "Abrir o catálogo"],
    "negocio/financeiro": ["Novo lançamento", "Quanto tenho a receber?", "Abrir relatórios"],
    agenda: ["O que tenho hoje?", "Organizar meu dia", "Ajuda desta tela"],
    automacoes: ["Nova rotina", "Ajuda desta tela"],
    relatorios: ["Quanto tenho a receber?", "Abrir financeiro"],
    config: ["Como conecto meu WhatsApp?", "Trocar para o tema escuro", "Abrir minha conta"],
    default: ["Organizar meu dia", "Onde cadastro um produto?", "Abra os agendamentos", "O que a Lia faz?"],
  };

  window.SocialMEILiaKB = Object.freeze({ screens, forms, guides, suggestionsByRoute });
})();
