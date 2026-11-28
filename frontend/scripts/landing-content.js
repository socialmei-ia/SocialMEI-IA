/* Textos da landing v2 (editar aqui, sem mexer na lógica). Tudo fictício e ilustrativo. */
window.SMEI_LANDING = {
  historia: [
    { id: 'conversa', rotulo: 'Conversa', area: 'Caixa Unificada · WhatsApp', titulo: 'Emilly pergunta como pagar o kit',
      linhas: [['Cliente', 'Emilly'], ['Canal', 'WhatsApp'], ['Mensagem', '“Posso pagar no Pix?”']], nota: 'Tudo começa no atendimento: a mensagem chega com o nome da cliente ao lado.' },
    { id: 'oportunidade', rotulo: 'Oportunidade', area: 'Oportunidades', titulo: 'Emilly está perto de comprar',
      linhas: [['Interesse', 'Quente'], ['Produto', 'Kit de presente'], ['Valor', 'R$ 180,00']], nota: 'Você vê quem merece um retorno hoje, sem varrer todas as conversas.' },
    { id: 'venda', rotulo: 'Venda', area: 'Vendas', titulo: 'Venda #1042 registrada',
      linhas: [['Cliente', 'Emilly'], ['Itens', '1 kit de presente'], ['Total', 'R$ 180,00']], nota: 'Cliente, itens e pagamento ficam no mesmo registro.' },
    { id: 'pagamento', rotulo: 'Pagamento', area: 'Vendas', titulo: 'Pix recebido',
      linhas: [['Forma', 'Pix'], ['Valor', 'R$ 180,00'], ['Situação', 'Recebido']], nota: 'Quem pagou, quanto e quando, sem caderninho.' },
    { id: 'financeiro', rotulo: 'Financeiro', area: 'Financeiro e relatórios', titulo: 'O mês ganha mais uma entrada',
      linhas: [['Entrou', 'R$ 180,00'], ['Origem', 'Venda #1042'], ['Saldo do mês', 'R$ 260,00']], nota: 'O dinheiro aparece com a história de onde veio.' }
  ],
  /* Rótulos e ordem dos ramos: os MESMOS na hero, na demonstração e no passo 2 (ids = áreas do onboarding). */
  rotulos: { comida: 'Vendo doces', moda: 'Loja de roupas', beleza: 'Beleza', casa: 'Serviços e reparos', presentes: 'Presentes e artesanato', outra: 'Outro ramo' },
  ordem: ['comida', 'moda', 'beleza', 'casa', 'presentes', 'outra'],
  ramos: [
    { id: 'presentes', cliente: 'Emilly', msg: 'Oi! Quanto fica o kit de presente para retirar amanhã?', sug: 'Oi, Emilly! O kit de presente sai por R$\u00a0180,00. Consigo separar para retirada amanhã. Quer que eu reserve?', item: 'Kit de presente', valor: 'R$\u00a0180,00' },
    { id: 'moda', cliente: 'Lyly', msg: 'Ainda tem a camisa azul no M?', sug: 'Oi, Lyly! Tenho sim no M, por R$\u00a089,90. Quer que eu separe uma para você?', item: 'Camisa azul (M)', valor: 'R$\u00a089,90' },
    { id: 'beleza', cliente: 'Tawanny', msg: 'Tem horário amanhã à tarde para escova?', sug: 'Oi, Tawanny! Tenho 15h ou 16h30 amanhã. Qual prefere? Já reservo para você.', item: 'Escova', valor: 'R$\u00a090,00' },
    { id: 'comida', cliente: 'Mike', msg: 'Vocês fazem bolo de pote para 20 pessoas?', sug: 'Oi, Mike! Fazemos sim: 20 potes saem por R$\u00a0240,00. Para qual data você precisa?', item: '20 bolos de pote', valor: 'R$\u00a0240,00' },
    { id: 'casa', cliente: 'Richard', msg: 'Consegue passar aí para um orçamento de pintura?', sug: 'Oi, Richard! Consigo passar na quinta de manhã. Qual é o endereço?', item: 'Orçamento de pintura', valor: 'a combinar' },
    { id: 'outra', cliente: 'Maiccon', msg: 'Oi! Vocês conseguem me atender na sexta à tarde?', sug: 'Oi, Maiccon! Consigo sim na sexta à tarde. Qual horário fica melhor para você?', item: 'Atendimento na sexta', valor: 'a combinar' }
  ]
};
