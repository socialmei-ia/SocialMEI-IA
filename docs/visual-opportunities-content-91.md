# Oportunidades e Divulgação — acabamento nativo

Base funcional: PR #91, `83129ce9a55ab1c27733f84a21a739a13b1898ce`.
Continuação de `feat/visual-opportunities-content-91`, inicialmente em
`a95c0fcc59522b96b85daf127a52003a43da2f5b`. Os quatro commits preliminares
foram preservados. A PR visual depende da #91; não é uma alternativa à sua cadeia.

## Alterações

- Composição aprovada aplicada às duas páginas oficiais, sem sandbox ou iframe.
- Oportunidades: formulário semântico na ordem de teclado cliente → interesse →
  necessidade; filtros com ícones e contadores, foco preservado; estados vazio,
  uma e várias oportunidades. Interesse e resultado continuam separados.
- Encerramento, motivo, reabertura, histórico e vínculo com vendas mantidos.
- Análise heurística identificada separadamente, sem criar registros comerciais.
  Controles compartilhados ficam ocultos no modo exclusivamente local.
- Divulgação: quatro abas com ícones e descrição, navegação por teclado, passos
  numerados, mídia local com botão em português, prévia 4:5 ou 9:16 sem recortar
  o arquivo. Rascunhos, Agenda e Conexões utilizam a navegação e os contratos nativos.
- Falhas de rede, sessão, permissão, conflito e serviço indisponível têm mensagens
  em português. Campos são preservados; nenhuma escrita remota falha vira cópia local.
- CSS restrito às duas páginas. A seção antiga de Divulgação foi substituída por
  `visual-content-polish.css`, sem repetir a camada preliminar.

## Abrir a prévia

Na branch `feat/visual-opportunities-content-91`, com Node 22+ e Docker Linux local:

```sh
npm ci
npm run preview -- up
```

Abra **https://127.0.0.1:8443**. O certificado é local. Cadastre uma conta fictícia;
utilize Oportunidades e Divulgação pela sidebar oficial. Crie um cliente em
Negócio → Clientes antes de registrar uma oportunidade. Rascunhos locais podem ser
criados sem simular publicação. No preview, Agenda e Conexões são preparação e
simulação sem transporte externo. `npm run preview -- down` encerra somente a prévia
sem apagar o volume. Não use contas ou informações reais.

Neste ambiente gerenciado, o build inicial precisou da CA pública do proxy em
um secret BuildKit temporário; o Caddy descartável precisou de `NO_PROXY` para os
aliases internos `api,database`. Esses ajustes não alteraram Dockerfiles, Compose,
configurações oficiais nem serviços existentes. A validação TLS externa permaneceu
ativa. Não copie configurações de proxy desta sessão para outro ambiente.

## Verificação e evidências

Comandos: `npm test`, `npm run format:check`, `npm run test:browser` e
`npm run test:preview` (Chromium real, backend e PostgreSQL descartáveis).
Resultados finais e link do CI são registrados na PR.

- Matriz Divulgação: quatro abas × cinco larguras × dois temas; teclado, mídia,
  proporções, rascunho preservado e ausência de erros JavaScript.
- Matriz Oportunidades: 320/390/768/1024/1440, dois temas, estados 0/1/3, controles
  de 44 px, ordem do formulário, foco dos filtros e ausência de sobreposição.
- Reflow equivalente a 200%: viewport CSS 720 × 500, densidade 2 e tela 1440 × 1000.
  Não é uma medição de zoom da interface do navegador nem teste com leitor de tela.
- Preview real: duas contas isoladas, CSRF, criação/encerramento/reabertura/histórico,
  recarga, conflito CAS, configuração pública Instagram e agendamento simulado.
- Regressores existentes mantidos; expectativas textuais de erro atualizadas sem
  remover verificações de persistência, bloqueio ou isolamento.

Capturas completas são geradas em `test-results/visual-opportunities`,
`test-results/visual-content` e `test-results/preview`. Uma seleção está em
[`docs/evidence/visual-workspaces-91`](evidence/visual-workspaces-91).
A captura anterior opcional usa `SOCIALMEI_VISUAL_BASELINE=true` e exige o commit
inicial disponível no checkout; o CI não depende dessa captura histórica.

## Limites preservados

Rascunhos e arquivos locais não são sincronizados. A mídia não é enviada nem
armazenada pelo fluxo de preparação. Legendas são sugestões locais demonstrativas;
IA de imagens não está conectada. Instagram, n8n, Meta e WhatsApp não publicam nem
enviam mensagens nesta entrega. A preparação compartilhada exige backend, sessão,
permissão e ativação explícita do modo de testes. A decoração do cabeçalho é um
asset gerado, sem dados de clientes ou significado estatístico.

Nenhum backend, migration, autenticação, ambiente publicado ou outro módulo foi
redesenhado. Nenhum merge ou deploy foi realizado.
