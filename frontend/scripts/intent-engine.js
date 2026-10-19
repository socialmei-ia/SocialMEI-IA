(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.SocialMEIIntent = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const MAX_LENGTH = 4000;
  const VERSION = "local-rules-3";
  const rules = [
    {
      id: "price",
      label: "Pergunta sobre preço",
      polarity: "positive",
      pattern:
        /\b(?:quanto\s+(?:custa(?:m)?|fica|sai)|qual\s+(?:e\s+)?(?:o\s+)?(?:preco|valor)|(?:preco|valor)\s+(?:do|da|de)|(?:preco|valor)(?=\s*\?)|(?:tem|faz)\s+(?:um\s+)?desconto)\b/g,
    },
    {
      id: "availability",
      label: "Consulta de disponibilidade",
      polarity: "positive",
      pattern:
        /\b(?:(?:tem|ha|possui)[^.!?;\n]{0,80}\b(?:estoque|pronta\s+entrega|disponiv(?:el|eis))|(?:esta|estao)\s+disponiv(?:el|eis)|disponibilidade)\b/g,
    },
    {
      id: "delivery",
      label: "Consulta de entrega",
      polarity: "positive",
      pattern:
        /\b(?:consegue(?:m)?\s+entregar|pode(?:m)?\s+entregar|entrega(?:m)?\s+(?:hoje|amanha|agora)|prazo\s+(?:de\s+)?entrega|qual\s+(?:e\s+)?o\s+frete|quanto\s+(?:e|custa)\s+o\s+frete)\b/g,
    },
    {
      id: "payment",
      label: "Consulta de pagamento",
      polarity: "positive",
      pattern:
        /\b(?:aceita(?:m)?\s+(?:pix|cartao|boleto)|(?:posso|pode|consigo)\s+pagar|(?:formas?\s+de\s+pagamento)|parcela(?:m)?|parcelamento)\b/g,
    },
    {
      id: "quote",
      label: "Pedido de orçamento",
      polarity: "positive",
      pattern:
        /\b(?:quero|gostaria|preciso|pode|poderia|consegue|mande|envie|solicito)[^.!?;\n]{0,35}\b(?:orcamento|cotacao)\b/g,
    },
    {
      id: "specific_item",
      label: "Referência a item identificado pelas regras",
      polarity: "positive",
      pattern:
        /\b(?:212\s*vip|good\s+girl|malbec|la\s+vie\s+est\s+belle|(?:iphone|galaxy)\s+[a-z]?\d{1,3}(?:\s+(?:pro|max|ultra))?|modelo\s+(?=[a-z0-9-]*\d)[a-z0-9]+(?:[-\s]\d[a-z0-9-]*)?|(?:produto|servico|item)\s+["“][^"”\n]{2,60}["”])/g,
    },
    {
      id: "item",
      label: "Produto ou serviço mencionado",
      polarity: "positive",
      pattern:
        /\b(?:perfumes?|camisas?|canecas?|tenis|kits?|fones?|sabonetes?|cremes?|notebooks?|celulares?|servicos?|corte\s+de\s+cabelo|troca\s+de\s+tela)\b/g,
    },
    {
      id: "quantity",
      label: "Quantidade mencionada",
      polarity: "positive",
      pattern:
        /\b(?:\d{1,3}|um|uma|dois|duas|tres|quatro|cinco|dez)\s+(?:unidades?|pecas?|frascos?|caixas?|kits?|camisas?|canecas?|perfumes?)\b/g,
    },
    {
      id: "urgency",
      label: "Prazo ou urgência mencionados",
      polarity: "ambiguous",
      negatable: true,
      pattern:
        /\b(?:ainda\s+hoje|hoje|agora|urgente|urgencia|o\s+quanto\s+antes|imediat[ao]|pronta\s+entrega)\b/g,
    },
    {
      id: "purchase",
      label: "Expressão de compra ou contratação",
      polarity: "positive",
      pattern:
        /\b(?:(?:quero|vou|vamos|desejo|pretendo|gostaria\s+de)\s+(?:mesmo\s+|muito\s+|ja\s+|mais\s+)?(?:comprar|levar|fechar|encomendar|reservar|agendar|contratar)|(?:pode|podemos)\s+(?:fechar|reservar|separar|confirmar)|fico\s+com|vou\s+ficar\s+com)\b/g,
    },
    {
      id: "decline",
      label: "Recusa ou desistência expressa",
      polarity: "negative",
      pattern:
        /\b(?:(?:nao|nunca|jamais|nem)\s+(?:eu\s+)?(?:quero|vou|desejo|pretendo|posso|consigo)\s+(?:mais\s+|mesmo\s+)?(?:comprar|levar|fechar|contratar|reservar|encomendar)|nao\s+tenho\s+interesse|nao\s+estou\s+interessad[oa]|sem\s+interesse|nao\s+quero\s+mais|desisti|desisto|cancelar|cancele|cancelei|deixa\s+(?:pra|para)\s+la)\b/g,
    },
    {
      id: "exploration",
      label: "Interesse exploratório declarado",
      polarity: "ambiguous",
      pattern:
        /\b(?:(?:so|apenas)\s+(?:estou\s+)?(?:pesquisando|olhando|comparando)|estou\s+(?:pesquisando|comparando)|sem\s+compromisso|apenas\s+curioso|no\s+futuro|mais\s+(?:pra|para)\s+frente)\b/g,
    },
    {
      id: "uncertainty",
      label: "Incerteza declarada",
      polarity: "ambiguous",
      pattern: /\b(?:nao\s+sei\s+se|nao\s+tenho\s+certeza|talvez|ainda\s+nao\s+decidi)\b/g,
    },
    {
      id: "condition",
      label: "Condição para decidir",
      polarity: "ambiguous",
      pattern:
        /(?:^|[.!?;,\n])\s*(?:se|caso)\b[^.!?;\n]{0,80}|\b(?:compraria|fecharia|comprar\s+se|fechar\s+se)\b/g,
    },
    {
      id: "objection",
      label: "Dúvida ou objeção comercial",
      polarity: "ambiguous",
      pattern:
        /\b(?:muito\s+caro|(?:esta|ta|achei)\s+caro|fora\s+do\s+orcamento|nao\s+cabe\s+no\s+orcamento|sem\s+dinheiro|tenho\s+duvidas?|nao\s+sei\s+se\s+vale)\b/g,
    },
    {
      id: "completed",
      label: "Relato de compra concluída",
      polarity: "ambiguous",
      negatable: true,
      pattern:
        /\b(?:ja\s+comprei|finalizei\s+a\s+compra|compra\s+concluida|pagamento\s+aprovado)\b/g,
    },
    {
      id: "support",
      label: "Solicitação de suporte ou problema relatado",
      polarity: "ambiguous",
      negatable: true,
      pattern:
        /\b(?:preciso\s+de\s+(?:suporte|ajuda)|nao\s+chegou|veio\s+quebrad[oa]|nao\s+funciona|(?:leite|alimento|produto)\s+(?:que\s+comprei\s+)?(?:esta|veio)\s+vencid[oa]|(?:corte|barra|ajuste)\s+ficou\s+tort[oa]|reembolso|devolucao|cobranca\s+indevida)\b/g,
    },
    {
      id: "after_sales",
      label: "Possível contexto de pós-venda",
      polarity: "ambiguous",
      negatable: true,
      pattern:
        /\b(?:minha\s+entrega|meu\s+pedido|ja\s+comprei|produto\s+que\s+comprei|nao\s+chegou|reembolso|devolucao|cobranca\s+indevida)\b/g,
    },
    {
      id: "reported",
      label: "Fala atribuída a outra pessoa",
      polarity: "ambiguous",
      pattern: /\b(?:ele|ela|cliente|pessoa|amigo|alguem)\s+(?:disse|falou|perguntou|escreveu)\b/g,
    },
  ];
  const consultations = ["price", "availability", "delivery", "payment", "quote"];
  const limitations = [
    "Regras locais em português, não um modelo de IA treinado nem uma probabilidade de venda.",
    "Somente este texto é analisado. Não há histórico, catálogo ou contexto do negócio conectado.",
    "Ironia, abreviações, erros, outros idiomas e referências indiretas podem não ser reconhecidos. Confirme com a pessoa.",
    "Uma menção a produto é apenas lexical. Preço, estoque, pagamento e entrega não são validados.",
  ];
  function foldWithOffsets(text) {
    let folded = "";
    const starts = [],
      ends = [];
    for (let index = 0; index < text.length;) {
      const char = String.fromCodePoint(text.codePointAt(index));
      const value = char.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
      if (!value && ends.length) ends[ends.length - 1] = index + char.length;
      for (let unit = 0; unit < value.length; unit++) {
        starts.push(index);
        ends.push(index + char.length);
      }
      folded += value;
      index += char.length;
    }
    return { folded, starts, ends };
  }
  function negationBefore(text, index) {
    const previous = text.slice(0, index);
    const boundary = [...previous.matchAll(/[.!?;,\n]|\b(?:mas|porem|contudo|entretanto)\b/g)].at(
      -1,
    );
    const start = boundary ? boundary.index + boundary[0].length : 0;
    const prefix = previous.slice(start);
    if (/\b(?:nao\s+sei\s+se|nao\s+tenho\s+certeza)\b/.test(prefix)) return null;
    const negation = [
      ...prefix.matchAll(/\b(?:nao|nunca|jamais|nem|sem)\b(?!\s+(?:so|somente|apenas)\b)/g),
    ].at(-1);
    if (!negation || prefix.slice(negation.index).trim().split(/\s+/).length > 8) return null;
    return start + negation.index;
  }
  function decide(signals) {
    const has = (id) => signals.some((s) => s.id === id);
    const positive = (id) => signals.some((s) => s.id === id && s.polarity === "positive");
    const inquiry = consultations.some(positive);
    if (has("decline") && (inquiry || positive("purchase")))
      return {
        category: "conflicting",
        label: "Sinais conflitantes",
        explanation:
          "O texto reúne recusa ou desistência e sinais comerciais em outros trechos. É necessário esclarecer a intenção e a qual item ou momento cada trecho se refere.",
        rule: "Recusa acompanhada de uma consulta comercial ou expressão de compra não negada.",
        nextStep:
          "Pergunte a qual item ou decisão cada trecho se refere. Não pressione pela compra nem presuma que a recusa foi retirada.",
      };
    if (has("decline"))
      return {
        category: "declined",
        label: "Recusa ou desistência",
        explanation:
          "Foi encontrada uma recusa ou desistência explícita neste texto. Isso não permite concluir falta de interesse em outros itens ou em outro momento.",
        rule: "Recusa expressa sem outro sinal comercial afirmativo suficiente para estabelecer conflito.",
        nextStep:
          "Respeite a recusa e interrompa a abordagem comercial. Se houver pedido de cancelamento, confirme o que a pessoa deseja cancelar antes de qualquer ação.",
      };
    if (has("reported"))
      return {
        category: "unclear",
        label: "Intenção a esclarecer",
        explanation:
          "Parte da mensagem atribui uma fala a outra pessoa. As palavras citadas não confirmam a intenção de quem escreveu.",
        rule: "Fala relatada exige confirmação do interlocutor e do contexto.",
        nextStep:
          "Confirme quem tem interesse e o que essa pessoa deseja, sem atribuir a compra ao remetente automaticamente.",
      };
    if (has("after_sales") || has("completed") || has("support"))
      return {
        category: positive("purchase") ? "unclear" : "insufficient",
        label: positive("purchase") ? "Intenção a esclarecer" : "Informações insuficientes",
        explanation:
          "Há indício de pós-venda. Uma pergunta sobre entrega ou pagamento pode se referir a uma compra anterior, e não a uma nova intenção comercial.",
        rule: "Contexto de pós-venda impede tratar consultas isoladas como nova compra.",
        nextStep:
          "Esclareça a necessidade de suporte e se existe um novo interesse, sem transformar uma reclamação em oportunidade automaticamente.",
      };
    if (
      has("uncertainty") ||
      has("condition") ||
      has("objection") ||
      signals.some(
        (s) =>
          s.id.startsWith("negated_") &&
          s.id !== "negated_urgency" &&
          !(s.id === "negated_decline" && has("exploration")),
      )
    )
      return {
        category: "unclear",
        label: "Intenção a esclarecer",
        explanation:
          "A mensagem traz incerteza, condição, objeção ou negação que muda o sentido dos sinais encontrados. Uma classificação elevada seria precipitada.",
        rule: "Ressalvas explícitas têm precedência sobre expressões de compra isoladas.",
        nextStep:
          "Esclareça a dúvida ou condição indicada e confira os dados do negócio antes de sugerir uma oferta.",
      };
    if (has("exploration"))
      return {
        category: "exploratory",
        label: "Interesse exploratório",
        explanation:
          "A pessoa declara estar pesquisando ou comparando. Consultas comerciais podem orientar a conversa, mas não confirmam decisão de compra.",
        rule: "Exploração declarada impede interpretar consultas como decisão de fechar.",
        nextStep:
          "Responda às informações solicitadas e pergunte o que a pessoa está comparando. Evite pressionar por uma decisão imediata.",
      };
    const combination =
      positive("price") &&
      positive("availability") &&
      (positive("delivery") || positive("payment") || positive("quote")) &&
      (positive("specific_item") || positive("item"));
    if (positive("purchase") || combination)
      return {
        category: "high",
        label: "Intenção elevada",
        explanation: positive("purchase")
          ? "Foi encontrada uma expressão explícita de compra ou contratação, sem recusa ou ressalva reconhecida pelas regras. É um indício para acompanhar a conversa, não uma venda garantida."
          : "A mensagem combina referência a produto ou serviço, preço, disponibilidade e consulta sobre entrega, pagamento ou orçamento. Há sinais comerciais concretos para acompanhar, sem garantia de venda.",
        rule: positive("purchase")
          ? "Expressão de compra sem recusa ou ressalva reconhecida."
          : "Produto ou serviço + preço + disponibilidade + entrega, pagamento ou orçamento, sem recusa ou ressalva reconhecida.",
        nextStep:
          "Confira os dados reais de preço, disponibilidade e atendimento. Responda ao que foi perguntado e confirme se a pessoa deseja avançar, sem prometer entrega ou reservar automaticamente.",
      };
    if (inquiry)
      return {
        category: "initial",
        label: "Interesse comercial inicial",
        explanation:
          "Há uma consulta comercial concreta, mas ela não confirma decisão de compra. Uma pergunta de preço, por exemplo, pode ser apenas pesquisa.",
        rule: "Consulta comercial sem confirmação suficiente nem ressalva que exija outro resultado.",
        nextStep:
          "Responda à consulta e pergunte qual produto, quantidade ou condição a pessoa precisa esclarecer. Não assuma que ela já decidiu comprar.",
      };
    return {
      category: "insufficient",
      label: "Informações insuficientes",
      explanation:
        "Não foi encontrada uma pergunta comercial ou decisão de compra reconhecida pelas regras. Elogio, sentimento, menção a item ou urgência isolados não confirmam intenção, e ausência de sinais não significa baixa intenção.",
      rule: "Sem consulta comercial ou expressão de compra reconhecida e contextualizada.",
      nextStep:
        "Se fizer sentido para o atendimento, pergunte como pode ajudar e qual é a necessidade. Não classifique a pessoa como desinteressada.",
    };
  }
  function analyzeMessage(text) {
    if (typeof text !== "string") throw new TypeError("Informe uma mensagem de texto.");
    if (text.length > MAX_LENGTH) throw new RangeError(`Use no máximo ${MAX_LENGTH} caracteres.`);
    const normalized = foldWithOffsets(text),
      found = new Map();
    function add(rule, start, end) {
      const evidence = {
        text: text.slice(normalized.starts[start], normalized.ends[end - 1]),
        start: normalized.starts[start],
        end: normalized.ends[end - 1],
      };
      if (!found.has(rule.id))
        found.set(rule.id, {
          id: rule.id,
          label: rule.label,
          polarity: rule.polarity,
          evidence: [],
        });
      const list = found.get(rule.id).evidence;
      if (
        list.length < 3 &&
        !list.some((item) => item.start === evidence.start && item.end === evidence.end)
      )
        list.push(evidence);
    }
    for (const rule of rules)
      for (const match of normalized.folded.matchAll(rule.pattern)) {
        if (
          rule.id === "purchase" &&
          /^\s+(?:a\s+|o\s+)?(?:porta|janela|navegador|loja|conta|aplicativo)\b/.test(
            normalized.folded.slice(match.index + match[0].length),
          )
        )
          continue;
        const negation = negationBefore(normalized.folded, match.index);
        if (
          negation !== null &&
          (rule.negatable || ["positive", "negative"].includes(rule.polarity))
        ) {
          const id = rule.id === "purchase" ? "decline" : `negated_${rule.id}`;
          add(
            {
              id,
              label:
                rule.id === "purchase"
                  ? "Recusa de compra"
                  : "Negação no trecho: " + rule.label.toLowerCase(),
              polarity: rule.id === "purchase" ? "negative" : "ambiguous",
            },
            negation,
            match.index + match[0].length,
          );
        } else add(rule, match.index, match.index + match[0].length);
      }
    // A question about a named/mentioned item can ask availability without saying "estoque".
    for (const match of normalized.folded.matchAll(
      /\b(?:tem|possui|vende(?:m)?)\s+(?!(?:como|que|interesse|certeza|duvida)\b)[^.!?;\n]{1,80}\?/g,
    )) {
      const start = normalized.starts[match.index],
        end = normalized.ends[match.index + match[0].length - 1];
      const itemInQuestion = ["specific_item", "item"].some((id) =>
        found.get(id)?.evidence.some((e) => e.start >= start && e.end <= end),
      );
      if (!itemInQuestion) continue;
      const negation = negationBefore(normalized.folded, match.index);
      add(
        negation === null
          ? { id: "availability", label: "Consulta de disponibilidade", polarity: "positive" }
          : {
              id: "negated_availability",
              label: "Negação na consulta de disponibilidade",
              polarity: "ambiguous",
            },
        negation ?? match.index,
        match.index + match[0].length,
      );
    }
    const signals = [...found.values()];
    const decision = decide(signals);
    const missingInformation = [];
    if (!signals.some((s) => ["specific_item", "item"].includes(s.id)))
      missingInformation.push(
        "Ainda não ficou claro qual produto ou serviço a pessoa procura. Confirme na conversa.",
      );
    if (!signals.some((s) => s.id === "purchase" && s.polarity === "positive"))
      missingInformation.push("Não há confirmação de compra reconhecida no texto.");
    if (!signals.some((s) => ["price", "quote"].includes(s.id)))
      missingInformation.push("Não foi reconhecida uma consulta de preço ou orçamento.");
    missingInformation.push(
      "Não é possível confirmar histórico, necessidades completas ou condições reais do negócio com uma mensagem isolada.",
    );
    return {
      version: VERSION,
      ...decision,
      signals,
      missingInformation,
      limitations: [...limitations],
    };
  }
  return Object.freeze({ analyzeMessage, MAX_LENGTH, VERSION });
});
