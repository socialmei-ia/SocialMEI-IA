# SocialMEI-IA — roteiro de testes para o professor

**Ambiente:** https://socialmei-ia.54-94-213-7.sslip.io

**Importante:** o site publicado atualmente é a release040 em produção. As novas correções de WhatsApp e Instagram no GitHub não entram automaticamente no site. Este roteiro deve ser usado conforme a situação real de publicação e os controles da empresa.

## Acesso seguro

O responsável deverá criar um convite de usuário para o professor, quando o fluxo de convites estiver validado. Utilizar conta individual, com permissões mínimas necessárias. **Não compartilhar senha de administrador, tokens da Meta, chaves AWS nem credenciais de banco.**

## Etapas disponíveis para avaliação

1. **Site e painel:** entrar, navegar pelas páginas e conferir se menus, formulários e navegação funcionam; relatar erros com tela, ação e horário.
2. **Dados da empresa:** verificar perfil, clientes, produtos, serviços e profissionais cadastrados. Evitar alterar dados reais sem necessidade.
3. **Agenda administrativa:** consultar agendamentos e histórico, incluindo a reserva de demonstração em 19/11/2026 às 9h de Pernambuco, se ainda existir no ambiente utilizado. O status inicial pode ser `pending`; confirmar o significado com a equipe antes de classificá-lo como falha.
4. **Agendamento público:** o fluxo completo de código por e-mail e confirmação foi homologado uma vez, mas a publicação pública está **desativada após o teste**. Reativar somente para uma janela de demonstração combinada, com acompanhamento e restauração ao final.
5. **WhatsApp:** o menu interativo GOWS está habilitado no contato piloto autorizado. Para testar com o telefone do professor, é necessário incluí-lo previamente no piloto, com autorização e confirmação de que o contato é válido.
6. **Instagram Direct:** a infraestrutura está ativa; recebimento, registro na Caixa Unificada e resposta automática única requerem homologação real. Não declarar aprovado até chegar uma mensagem e a resposta correspondente ser comprovada.
7. **Cancelamento e reagendamento por canal:** código implementado na branch de continuidade; precisa passar pelos testes de integração descartáveis, build da imagem correspondente e publicação autorizada antes de ser apresentado como funcional em produção.

## Critérios objetivos de aprovação

- A conta correta acessa exclusivamente o workspace autorizado.
- Cada canal recebe e responde **uma única vez** a uma mensagem real.
- Agendamento mostra cliente, serviço, profissional, fuso horário, status e histórico corretos.
- Reserva de outra empresa/conversa não pode ser cancelada ou reagendada.
- Atendimento humano prevalece sobre automação.
- Falhas de credenciais, rede ou permissão não expõem informações sensíveis.
- A publicação e seu rollback preservam os dados anteriores.

## Registro de problemas

Para cada falha, registrar: data/hora, módulo, ação realizada, resultado esperado, resultado observado e se o problema pôde ser reproduzido. **Não incluir códigos de e-mail, senhas, tokens nem mensagens pessoais de clientes.**

## Situação da preparação em 18/11/2026

A validação automática, imagens candidatas e integração ao runtime ainda são tarefas separadas. O sistema só deve ser anunciado como inteiramente pronto para o professor quando a nova versão estiver publicada e os testes de Instagram e WhatsApp em ambiente real forem aprovados.
