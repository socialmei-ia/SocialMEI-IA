# Prévia de agendamento público

Abra `index.html` por um servidor estático a partir da raiz do projeto. A prévia fica isolada da navegação principal e usa somente dados fictícios de Bella Store e Brilho Limpeza. Não consulta API, não envia dados, não usa armazenamento do navegador e não cria reservas.

Permite experimentar serviço → profissional/equipe → dia/horário → dados mínimos → resumo. Os controles de demonstração também mostram indisponibilidade, consulta com falha e disputa por horário antes da solicitação. Os temas usam os tokens do aplicativo; a paleta escura segue `storage-and-themes.js`.

## Antes de publicar uma experiência real

- Definir publicação explícita do negócio e dos serviços autorizados, sem expor identificadores internos, clientes ou endpoints administrativos.
- Especificar autenticação/verificação de contato para visitantes, limites por origem e negócio e proteção contra abuso. Um e-mail digitado não comprova identidade nem autoriza associação ao CRM.
- Criar contrato próprio de consulta e solicitação pública, com validação e isolamento no servidor, idempotência e transação de agenda compartilhada. Revalidar preço, duração e disponibilidade antes de confirmar.
- Decidir quais dados mínimos o cliente deve informar, como serão verificados e como será informado sobre a solicitação. Nunca apresentar confirmação antes de persistência comprovada.
- Revisar e aprovar o protótipo antes da integração, conforme a skill `prototype-first`. Revisão de segurança e homologação do contrato público continuam necessárias.

Não foi demonstrada necessidade inevitável de migration. A configuração e as tabelas existentes podem oferecer parte da base; falta um contrato de visitante seguro, cuja implementação não deve reutilizar permissões do painel.
