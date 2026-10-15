## O que mudou?

Descreva de forma curta.

## Como testar?

Explique os passos para outra pessoa reproduzir a validação.

## Impacto

- [ ] Frontend
- [ ] Caixa Unificada
- [ ] Clientes / Vendas / Financeiro / Produtos
- [ ] Automações / Assistente
- [ ] n8n
- [ ] Banco de dados
- [ ] Docker / Caddy
- [ ] FastAPI
- [ ] Documentação
- [ ] Sem impacto em produção

## Checklist

- [ ] Testei o que alterei
- [ ] Trabalhei em uma branch, não diretamente na `main`
- [ ] Testei visualmente quando alterei a interface
- [ ] Não adicionei `.env`, senhas, tokens ou chaves privadas
- [ ] Atualizei documentação quando necessário
- [ ] Editei a fonte oficial em `frontend/` e preservei as entradas de compatibilidade
- [ ] Executei `npm test`, `format:check` e os testes pertinentes
- [ ] Validei `docker compose config --quiet` se alterei infraestrutura
- [ ] Expliquei rollback se a mudança puder afetar produção

## Evidências

Adicione prints, resultados de testes ou observações úteis.

Informe o SHA de base e o ambiente testado (local, CI, team ou legado). Separe resultados de CI de qualquer conferência de runtime; merge/build não comprovam publicação. Registre skips e serviços externos não testados.

## Banco / infraestrutura

Explique o impacto, a aplicação e o rollback. Se não houver impacto, escreva **Sem impacto**.

Se houver mudança de contrato, liste request/response/status e compatibilidade. Para configuração, indique somente nomes de variáveis; nunca valores privados. Migration aplicada é imutável; alterações novas precisam de teste e alvo/backup próprios.
