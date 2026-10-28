# Compatibilidade de grants OAuth do Instagram

O grant recebido pode ser flat ou ter um envelope data com exatamente um item. Permissões podem ser texto separado por vírgulas ou lista de strings. Todos os escopos obrigatórios continuam exigidos; tipos incorretos, duplicatas e escopos desconhecidos continuam bloqueados.

Na conta de teste, a resposta HTTPS da Meta concedeu todos os requisitos e devolveu também instagram_business_manage_insights. Esse extra é descartado antes de criar o grant interno. Não é solicitado, persistido como capacidade ou habilitado pelo SocialMEI. A allowlist das permissões solicitáveis e do frontend permanece inalterada. Outros escopos extras continuam rejeitados.

Os testes reproduzem quatro escopos suportados mais insights e verificam rejeição de duplicatas, outros extras e requisitos ausentes. O teste OAuth com PostgreSQL descartável confirma conexão e token criptografado, persistindo somente os escopos suportados. Isso não substitui a autorização da conta real após instalar a correção.

Atualização operacional somente da API, sem SQL, mantendo a rede de saída e gateway atual. Publicação, Direct e automações permanecem sujeitos aos gates de ativação e homologação próprios.
