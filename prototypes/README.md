# Protótipos isolados

Política aprovada pelo pedido de 15/10/2026: **ideia → análise → HTML isolado → visualização → ajustes → aprovação explícita → integração → testes → publicação por etapa**. Features visuais grandes seguem esse fluxo. Bug funcional/acessibilidade pode ser corrigido na V1 dentro do escopo autorizado.

Não incluir protótipos na navegação principal, imports do app ou imagem do gateway. Usar dados fictícios, estado em memória e recursos locais/embutidos. Sem API, banco, stores/keys do app, analytics, secrets ou alterações de schema. Uma ação simulada deve ficar identificada como tal. Código técnico em inglês; interface em português.

## Oportunidades

Abra `opportunities.html` diretamente no navegador. É um arquivo autocontido, sem instalação. Alternativa para desenvolvimento: servir a raiz do projeto com `python -m http.server 5500` e abrir `http://localhost:5500/prototypes/opportunities.html` **no mesmo computador**. Esse localhost não é endereço para o grupo.

O protótipo oferece busca, filtro de temperatura, lista/quadro, detalhes com razões/histórico fictícios, troca de etapa em memória, temas e reinício da demonstração. Recarregar descarta alterações. Não há cálculo, previsão ou integração real; percentuais/temperaturas foram atribuídos manualmente para explorar UX. Testes em `node tests/opportunities-browser.cjs`.

No CI do PR, o artifact **opportunities-prototype** reúne o HTML e capturas desktop/mobile claro/escuro. Baixe o ZIP, extraia e abra `prototypes/opportunities.html` no navegador. A página de código do GitHub mostra o código, não uma prévia do aplicativo. Se o navegador gerenciado bloquear arquivos locais, use o servidor estático no mesmo computador. Não é necessário atualizar o site da AWS para revisar essa proposta.

Aceite visual pendente: localização no produto, densidade/lista/quadro/mobile, apresentação da avaliação e utilidade das razões. Aceite funcional pendente: critérios/pesos, significado do percentual, janela temporal, dados autorizados e regras da oportunidade. Aprovar visual não autoriza inventar a fórmula.

Antes de integrar: registrar aprovação e ajustes; mapear modelo/API/store/UI, isolamento e estados sem avaliação/erro/carregamento; reutilizar tokens/componentes do app; testar CRUD/permissões/concorrência/temas/teclado; publicar apenas serviços afetados. A proposta arquitetural está em [V2-FOUNDATION-PLAN.md](../docs/V2-FOUNDATION-PLAN.md#15-funil--oportunidades).

GitHub Pages, se configurado para publicar toda a raiz, pode disponibilizar a pasta estática; isso não torna o protótipo parte do app. O gateway team copia apenas frontend e não o serve. Não fornecer link público sem conferir a publicação real.
