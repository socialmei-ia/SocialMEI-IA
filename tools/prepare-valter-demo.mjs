import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const origin = "https://127.0.0.1:8443";
const notice = "DADOS FICTÍCIOS — demonstração acadêmica do professor Valter.";

export function operationId(workspace, name) {
  const bytes = createHash("sha256").update(`valter-demo:${workspace}:${name}`).digest();
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = bytes.subarray(0, 16).toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function requirePreview(marker, capabilities) {
  if (marker?.environment !== "local-disposable-preview" || marker.transport !== "none")
    throw Error("O ambiente não é o preview local descartável. Nenhum cadastro autorizado.");
  if (capabilities?.mode !== "stub" || capabilities.transport !== "none")
    throw Error("A demonstração exige análise simulada e transporte externo desativado.");
}

export async function prepareDemo(api, account) {
  requirePreview(
    await api("/__preview", "GET", undefined, false),
    await api("/message-enrichment/capabilities"),
  );
  let identity = await api("/auth/session");
  if (identity?.usuario.email !== account.email || !account.email.endsWith("@example.test"))
    throw Error("A sessão não corresponde à conta fictícia reservada.");
  if (account.workspaceId && account.workspaceId !== identity.negocio.id)
    throw Error("O negócio da demonstração mudou. Preserve o recibo e confira a conta.");
  const workspace = identity.negocio.id;
  account.workspaceId = workspace;
  identity = await api("/auth/profile", "PATCH", {
    nome_negocio: "Ateliê Escola — MEI FICTÍCIO",
    configuracao_negocio: {
      horario: "DEMONSTRAÇÃO: segunda a sexta, 09:00–18:00; sábado, 09:00–12:00.",
    },
  });
  const profile = await api("/workspace-profile");
  if (!profile.profile)
    await api("/workspace-profile", "PATCH", {
      schema_version: 1,
      expected_revision: profile.revision,
      profile: {
        version: 1,
        businessName: identity.negocio.nome,
        segment: "tailoring",
        activity: "Costura e venda de kits — demonstração fictícia",
        offers: ["products", "services"],
        services: ["Ajuste de barra"],
        productCategories: ["Kits de costura"],
        capabilities: {
          appointments: false,
          orders: true,
          deliveries: false,
          inventory: true,
          team: false,
          walkIns: true,
          quotes: true,
          onlineOrders: false,
          recurring: false,
        },
        modules: [
          "clients",
          "inbox",
          "products",
          "services",
          "inventory",
          "sales",
          "finance",
          "reports",
        ],
        ignoredSuggestions: [],
        completed: true,
      },
    });

  const clients = ["Ana Exemplo", "Carlos Exemplo", "Beatriz Exemplo"];
  await api("/clientes/importacoes/confirmar", "POST", {
    origem: operationId(workspace, "clients"),
    itens: clients.map((nome, index) => ({
      local_id: index + 1,
      cliente: {
        nome,
        email: `cliente-${index + 1}@example.test`,
        observacao: notice,
        tags: ["Fictício"],
      },
      extras: {},
    })),
  });
  const products = [
    {
      nome: "Kit de costura — fictício",
      tipo: "Produto",
      preco: 45,
      custo: 20,
      estoque: 12,
      minimo: 3,
      status: "Ativo",
    },
    {
      nome: "Linha colorida — fictício",
      tipo: "Produto",
      preco: 12.5,
      custo: 5,
      estoque: 0,
      minimo: 2,
      status: "Ativo",
    },
    {
      nome: "Ajuste de barra — fictício",
      tipo: "Serviço",
      preco: 25,
      custo: 5,
      estoque: null,
      minimo: null,
      status: "Ativo",
    },
  ];
  await api("/produtos/importacoes/confirmar", "POST", {
    origem: operationId(workspace, "products"),
    itens: products.map((produto, index) => ({ local_id: index + 1, produto, extras: {} })),
  });
  const savedClients = await api("/clientes"),
    savedProducts = await api("/produtos");
  const client = (name) => savedClients.find((row) => row.nome === name)?.id;
  const product = (name) => savedProducts.find((row) => row.nome === name)?.id;
  for (const index of [0, 1]) {
    const sale = await api("/vendas", "POST", {
      operation_id: operationId(workspace, `sale-${index}`),
      cliente_id: client(clients[index]),
      produto_id: product(products[index ? 2 : 0].nome),
      data: account.day,
      quantidade: index ? 1 : 2,
      preco: index ? 25 : 45,
      desconto: 0,
      pagamento: "Pix",
      status: "Pendente",
      observacao: notice,
    });
    if (index === 0)
      await api(`/vendas/${sale.id}/pagar`, "POST", {
        operation_id: operationId(workspace, "sale-0-paid"),
        expected_version: sale.versao,
      });
  }
  for (const [index, entry] of [
    { descricao: "Recebimento dos kits — fictício", tipo: "receita", valor: 90, status: "pago" },
    { descricao: "Compra de material — fictícia", tipo: "despesa", valor: 30, status: "pago" },
    { descricao: "Ajuste a receber — fictício", tipo: "receita", valor: 25, status: "aberto" },
  ].entries())
    await api("/financeiro", "POST", {
      ...entry,
      operation_id: operationId(workspace, `finance-${index}`),
      vencimento: account.day,
    });

  const messages = [
    [
      "whatsapp",
      "ana",
      "Ana Exemplo [SIMULADO]",
      "Olá! Quero dois kits de costura. Qual é o preço e a disponibilidade?",
    ],
    [
      "whatsapp",
      "carlos",
      "Carlos Exemplo [SIMULADO]",
      "Meu ajuste ficou apertado. Preciso de ajuda para resolver.",
    ],
    [
      "instagram",
      "beatriz",
      "Beatriz Exemplo [SIMULADO]",
      "Adorei o trabalho! Gostaria de um orçamento para ajustar uma calça.",
    ],
  ];
  for (const [channel, ref, contact_name, text] of messages) {
    const incoming = await api("/message-enrichment/synthetic-messages", "POST", {
      schema_version: 1,
      operation_id: operationId(workspace, `message-${ref}`),
      channel,
      account_ref: "synthetic:valter-demo",
      contact_ref: `synthetic:valter-${ref}`,
      contact_name,
      external_message_id: `valter-${ref}`,
      text,
      occurred_at: account.createdAt,
    });
    await api(`/message-enrichment/messages/${incoming.message_id}/enrich`, "POST", {
      schema_version: 1,
      operation_id: operationId(workspace, `analysis-${ref}`),
      expected_revision: incoming.revision,
    });
  }
  await api("/agenda", "POST", {
    operation_id: operationId(workspace, "reminder"),
    title: "Confirmar orçamento — fictício",
    scheduled_for: account.day + "T14:30:00-03:00",
    notes: notice,
    cliente_id: client(clients[1]),
  });
  const menu = [];
  for (const opcao of ["0", "1", "2", "3", "4", "5"]) {
    const preview = await api(`/whatsapp/bot/preview?opcao=${opcao}`);
    if (preview.preview_only !== true || preview.send_enabled !== false)
      throw Error("A consulta do bot não confirmou o modo sem envio.");
    menu.push({ opcao, action: preview.action, handoff: preview.handoff });
  }
  const report = await api("/reporting/overview?days=30");
  return {
    environment: "local-disposable-preview",
    workspace,
    notice,
    sales: (await api("/vendas")).length,
    finance: (await api("/financeiro")).length,
    clients: savedClients.length,
    products: savedProducts.length,
    conversations: (await api("/message-enrichment/conversations")).items.length,
    reminders: (await api("/agenda")).items.length,
    analysis: "SIMULAÇÃO determinística persistida; nenhum provedor de IA acionado",
    transport: "none",
    real_messages_sent: 0,
    menu,
    report,
    url: `${origin}/frontend/entrada.html#/entrar`,
  };
}

async function main() {
  const { request } = await import("playwright");
  const directory = join(root, ".preview"),
    file = join(directory, "valter-demo-account.json");
  mkdirSync(directory, { recursive: true });
  const context = await request.newContext({ baseURL: origin, ignoreHTTPSErrors: true });
  let identity;
  const api = async (path, method = "GET", data, prefixed = true) => {
    const response = await context.fetch((prefixed ? "/api/v1" : "") + path, {
      method,
      data,
      headers: {
        Origin: origin,
        "X-SocialMEI-Client": "browser",
        ...(identity
          ? {
              "X-SocialMEI-CSRF": identity.csrf_token,
              "X-SocialMEI-Identity": `${identity.usuario.id}:${identity.negocio.id}`,
            }
          : {}),
      },
    });
    if (!response.ok())
      throw Error(`Não foi possível concluir ${path.split("?")[0]} (HTTP ${response.status()}).`);
    return response.status() === 204 ? null : response.json();
  };
  try {
    const marker = await api("/__preview", "GET", undefined, false);
    if (marker.environment !== "local-disposable-preview" || marker.transport !== "none")
      throw Error("Destino recusado: somente preview local descartável.");
    const existing = existsSync(file);
    const account = existing
      ? JSON.parse(readFileSync(file, "utf8"))
      : {
          email: `valter-demo-${randomUUID()}@example.test`,
          senha: `Demo-${randomUUID()}!`,
          day: new Intl.DateTimeFormat("en-CA", { timeZone: "America/Fortaleza" }).format(
            new Date(),
          ),
          createdAt: new Date().toISOString(),
        };
    if (!existing)
      writeFileSync(file, JSON.stringify(account, null, 2), { mode: 0o600, flag: "wx" });
    if (existing) {
      try {
        identity = await api("/auth/login", "POST", { email: account.email, senha: account.senha });
      } catch (error) {
        if (!error.message.includes("HTTP 401")) throw error;
        identity = await api("/auth/register", "POST", {
          nome: "Professor Valter — DEMONSTRAÇÃO",
          email: account.email,
          senha: account.senha,
        });
      }
    } else
      identity = await api("/auth/register", "POST", {
        nome: "Professor Valter — DEMONSTRAÇÃO",
        email: account.email,
        senha: account.senha,
      });
    const result = await prepareDemo(api, account);
    writeFileSync(file, JSON.stringify(account, null, 2), { mode: 0o600 });
    writeFileSync(join(directory, "valter-demo-result.json"), JSON.stringify(result, null, 2));
    console.log(
      `MEI fictício preparado: ${result.clients} clientes, ${result.products} itens, ${result.sales} vendas, ${result.finance} lançamentos, ${result.conversations} conversas simuladas.`,
    );
    console.log(
      `Acesso local: ${result.url}\nCredenciais exclusivamente de teste: .preview/valter-demo-account.json`,
    );
  } finally {
    await context.dispose();
  }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
