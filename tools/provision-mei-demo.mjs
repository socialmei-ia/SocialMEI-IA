import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const notice = "DADOS FICTÍCIOS — demonstração acadêmica SocialMEI.";
const version = "socialmei-demo-v1";
const businesses = new Set(["Brilho Limpeza", "Bella Store"]);
const businessName = (target) => target.expectedBusinessName ?? target.business;

export function operationId(target, key) {
  const hex = createHash("sha256").update(`${version}:${target.workspaceId}:${key}`).digest("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}

export function validateTarget(target) {
  if (
    !businesses.has(target.business) ||
    ![
      target.business,
      ...(target.business === "Brilho Limpeza" ? ["Brilho&Limpeza Service"] : []),
    ].includes(businessName(target)) ||
    !Number.isSafeInteger(target.workspaceId) ||
    target.workspaceId < 1 ||
    !Number.isSafeInteger(target.userId) ||
    target.userId < 1 ||
    !/^\d{4}-\d{2}-\d{2}$/.test(target.anchorDate) ||
    Number.isNaN(Date.parse(target.anchorDate)) ||
    new Date(target.anchorDate).toISOString().slice(0, 10) !== target.anchorDate ||
    (target.pendingStartDate !== undefined &&
      (typeof target.pendingStartDate !== "string" ||
        !/^\d{4}-\d{2}-\d{2}$/.test(target.pendingStartDate) ||
        Number.isNaN(Date.parse(target.pendingStartDate)) ||
        new Date(target.pendingStartDate).toISOString().slice(0, 10) !== target.pendingStartDate ||
        target.pendingStartDate <= target.anchorDate))
  )
    throw Error("Informe negócio autorizado, IDs positivos e data fixa válida no manifesto.");
  return target;
}

export function guardIdentity(target, identity) {
  validateTarget(target);
  if (
    identity?.usuario?.id !== target.userId ||
    identity.usuario.administrador_plataforma !== false ||
    identity?.negocio?.id !== target.workspaceId ||
    identity.negocio.nome !== businessName(target) ||
    identity.negocio.slug === "team" ||
    identity.papel !== "owner" ||
    (identity.email_verification?.required && !identity.email_verification.verified)
  )
    throw Error(
      "Sessão recusada: confira proprietário independente, negócio e verificação de e-mail.",
    );
  return identity;
}

function day(target, offset) {
  const date = new Date(target.anchorDate + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}

export function fixture(target) {
  validateTarget(target);
  const services = target.business === "Brilho Limpeza";
  const catalog = services
    ? [
        ["Limpeza residencial", 180, 50, 120],
        ["Limpeza de escritório", 240, 70, 180],
        ["Higienização de ambiente", 120, 30, 60],
      ]
    : [
        ["Camiseta demonstração", 59.9, 25],
        ["Bolsa demonstração", 89.9, 40],
        ["Lenço demonstração", 29.9, 10],
      ];
  const products = catalog.map(([name, preco, custo, duration]) => ({
    nome: `${name} — FICTÍCIO`,
    tipo: services ? "Serviço" : "Produto",
    preco,
    custo,
    estoque: services ? null : 20,
    minimo: services ? null : 3,
    status: "Ativo",
    descricao: notice,
    categoria: services ? "Limpeza fictícia" : "Moda fictícia",
    ...(services ? { duracao_minutos: duration } : {}),
  }));
  const clients = ["Cliente Alfa", "Cliente Beta", "Cliente Gama", "Cliente Delta"].map(
    (name, index) => ({
      nome: `${name} — FICTÍCIO`,
      email: `cliente-${index + 1}@example.test`,
      observacao: notice,
      tags: ["Fictício", version],
    }),
  );
  const profile = {
    version: 1,
    businessName: businessName(target),
    segment: services ? "services" : "fashion",
    activity: services
      ? "Serviços de limpeza — negócio fictício para demonstração"
      : "Comércio de moda — negócio fictício para demonstração",
    offers: [services ? "services" : "products"],
    services: services ? products.map((row) => row.nome) : [],
    productCategories: services ? [] : ["Moda fictícia"],
    capabilities: {
      appointments: services,
      orders: false,
      deliveries: false,
      inventory: !services,
      team: true,
      walkIns: false,
      quotes: true,
      onlineOrders: false,
      recurring: false,
    },
    modules: [
      "clients",
      "inbox",
      "opportunities",
      services ? "services" : "products",
      ...(services ? ["appointments"] : ["inventory"]),
      "team",
      "sales",
      "finance",
      "reports",
    ],
    ignoredSuggestions: [],
    completed: true,
  };
  const policy = {
    enabled: false,
    timezone: "America/Fortaleza",
    hours: Array.from({ length: 5 }, (_, weekday) => ({
      weekday,
      opens: "08:00",
      closes: "18:00",
    })),
    step_minutes: 30,
    lead_minutes: 120,
    horizon_days: 30,
  };
  const appointmentDates = [0, 1, 2, 3].map((index) =>
    index >= 2 && target.pendingStartDate
      ? day({ anchorDate: target.pendingStartDate }, index - 2)
      : day(target, index - 2),
  );
  return { services, products, clients, profile, policy, appointmentDates };
}

// All writes use the normal account/CSRF/identity contracts. No SQL or transport APIs.
export async function provisionDemo(api, target, { apply = false, checkpoint = () => {} } = {}) {
  const data = fixture(target);
  let identity = guardIdentity(target, await api("/auth/session"));
  const owned = [];
  const report = {
    version,
    mode: apply ? "apply" : "dry-run",
    workspaceId: target.workspaceId,
    userId: target.userId,
    business: target.business,
    expectedBusinessName: businessName(target),
    anchorDate: target.anchorDate,
    pendingStartDate: target.pendingStartDate ?? null,
    notice,
    records: owned,
    complete: false,
    externalMessagesCreated: 0,
    channelsChanged: false,
    accountsCreated: false,
  };
  const save = () => checkpoint(structuredClone(report));
  const write = async (path, method, payload) => {
    identity = guardIdentity(target, await api("/auth/session"));
    return api(path, method, payload);
  };
  const record = (kind, key, id) => {
    owned.push({ kind, key, id });
    save();
  };
  const profile = await api("/workspace-profile");
  const policy = data.services ? await api("/agenda/channel-booking") : null;
  // A pre-existing profile/policy belongs to the owner; a fixture never replaces it.
  report.profile = profile.profile ? "preserved" : "create";
  report.bookingPolicy = policy
    ? policy.revision
      ? "preserved"
      : "create-disabled"
    : "not-applicable";
  const batches = {};
  for (const [kind, rows, field, idField] of [
    ["clientes", data.clients, "cliente", "cliente_id"],
    ["produtos", data.products, "produto", "produto_id"],
  ]) {
    const body = {
      origem: operationId(target, kind),
      itens: rows.map((row, i) => ({ local_id: i + 1, [field]: row, extras: {} })),
    };
    // These documented preview endpoints only inspect import mappings.
    const preview = await api(`/${kind}/importacoes/preview`, "POST", body);
    if (!preview.pode_importar || preview.itens.length !== rows.length)
      throw Error(`Importação ${kind} recusada: conflito ou exclusão anterior. Preserve a origem.`);
    const existing = await api(`/${kind}`);
    for (const item of preview.itens) {
      if (
        item.acao === "criar" &&
        existing.some((row) => row.nome === rows[item.local_id - 1].nome)
      )
        throw Error(
          `Cadastro ${kind} semelhante sem vínculo de origem. Reconciliação manual necessária.`,
        );
    }
    batches[kind] = { body, preview, idField };
  }
  report.planned = {
    clients: 4,
    products: 3,
    resources: data.services ? 2 : 0,
    appointments: data.services ? 4 : 0,
    sales: 2,
    finance: 3,
    opportunities: 2,
    reminders: 2,
  };
  report.appointmentDates = data.services ? data.appointmentDates : [];
  save();
  if (!apply) return report;
  if (!profile.profile) {
    await write("/workspace-profile", "PATCH", {
      schema_version: 1,
      expected_revision: profile.revision,
      profile: data.profile,
    });
    record("profile", "profile", target.workspaceId);
  }
  if (policy && policy.revision === 0) {
    await write("/agenda/channel-booking", "PUT", { expected_revision: 0, policy: data.policy });
    record("policy", "policy-disabled", target.workspaceId);
  }
  if (!identity.negocio.configuracao?.horario) {
    await write("/auth/profile", "PATCH", {
      configuracao_negocio: { horario: "DADOS FICTÍCIOS: segunda a sexta, 08:00–18:00." },
    });
  }
  const ids = {};
  for (const [kind, batch] of Object.entries(batches)) {
    const result = await write(`/${kind}/importacoes/confirmar`, "POST", batch.body);
    ids[kind] = result.itens.map((row) => {
      if (!Number.isSafeInteger(row[batch.idField]) || row[batch.idField] < 1)
        throw Error(
          "Importação sem identificação persistida. Interrompido sem criar dependências.",
        );
      record(kind, String(row.local_id), row[batch.idField]);
      return [row.local_id, row[batch.idField]];
    });
    ids[kind] = new Map(ids[kind]);
  }
  const client = (index) => ids.clientes.get(index + 1);
  const product = (index) => ids.produtos.get(index + 1);
  if (data.services) {
    for (let index = 0; index < 2; index++) {
      const key = `resource-${index}`;
      const resource = await write("/agenda/resources", "POST", {
        operation_id: operationId(target, key),
        nome: `Equipe ${index + 1} — FICTÍCIA`,
      });
      record("resource", key, resource.id);
    }
    for (let index = 0; index < 4; index++) {
      const key = `appointment-${index}`;
      const result = await write("/agenda/appointments", "POST", {
        operation_id: operationId(target, key),
        cliente_id: client(index),
        servico_id: product(index % 3),
        resource_id: operationId(target, `resource-${index % 2}`),
        scheduled_for: `${data.appointmentDates[index]}T09:00:00-03:00`,
        notes: notice,
      });
      record("appointment", key, result.id);
      const status = ["done", "cancelled", "pending", "pending"][index];
      if (result.status !== status) {
        if (result.status !== "pending" || result.revision !== 1)
          throw Error(
            "Agendamento demonstrativo alterado pelo usuário. Estado preservado; confira o inventário.",
          );
        await write(`/agenda/appointments/${result.id}`, "PATCH", { expected_revision: 1, status });
      }
    }
  }
  for (let index = 0; index < 2; index++) {
    const key = `sale-${index}`;
    const itemIndex = data.services && index === 1 ? 2 : index;
    const result = await write("/vendas", "POST", {
      operation_id: operationId(target, key),
      cliente_id: client(itemIndex),
      produto_id: product(itemIndex),
      data: day(target, data.services && index === 1 ? 0 : index - 2),
      quantidade: 1,
      preco: data.products[itemIndex].preco,
      desconto: 0,
      pagamento: "Pix",
      status: "Pendente",
      observacao: notice,
    });
    record("sale", key, result.id);
    if (index === 0)
      await write(`/vendas/${result.id}/pagar`, "POST", {
        operation_id: operationId(target, "sale-paid"),
        expected_version: 1,
      });
  }
  for (const [index, entry] of [
    {
      descricao: "Receita do serviço/item demonstrativo — FICTÍCIA",
      tipo: "receita",
      valor: data.products[0].preco,
      status: "pago",
    },
    {
      descricao: "Receita pendente demonstrativa — FICTÍCIA",
      tipo: "receita",
      valor: data.products[data.services ? 2 : 1].preco,
      status: "aberto",
    },
    {
      descricao: "Materiais de demonstração — FICTÍCIOS",
      tipo: "despesa",
      valor: data.products[0].custo,
      status: "pago",
    },
  ].entries()) {
    const result = await write("/financeiro", "POST", {
      ...entry,
      operation_id: operationId(target, `finance-${index}`),
      vencimento: day(target, index === 1 ? -1 : -2),
    });
    record("finance", String(index), result.id);
  }
  for (let index = 0; index < 2; index++) {
    const opportunity = await write("/opportunities", "POST", {
      operation_id: operationId(target, `opportunity-${index}`),
      client_id: client(index + 2),
      title: `${data.services ? "Orçamento de limpeza" : "Consulta de catálogo"} ${index + 1} — FICTÍCIO`,
      interest_level: index ? "warm" : "hot",
      estimated_amount: data.products[index].preco,
      follow_up_date: day(target, index + 1),
      planning_note: notice,
      contacted: false,
    });
    record("opportunity", String(index), opportunity.id);
    const reminder = await write("/agenda", "POST", {
      operation_id: operationId(target, `reminder-${index}`),
      cliente_id: client(index),
      title: `Atendimento interno demonstrativo ${index + 1} — FICTÍCIO`,
      scheduled_for: `${day(target, index - 2)}T14:00:00-03:00`,
      notes: `${notice} Registro manual; nenhuma mensagem externa.`,
    });
    record("reminder", String(index), reminder.id);
  }
  guardIdentity(target, await api("/auth/session"));
  await api("/reporting/overview?days=30");
  report.complete = true;
  save();
  return report;
}

export async function createApi(origin, credentials, target) {
  if (target) validateTarget(target);
  const url = new URL(origin);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  )
    throw Error("Use apenas a origem HTTPS, sem caminho ou credenciais na URL.");
  let cookie = "",
    identity;
  const api = async (path, method = "GET", body) => {
    const response = await fetch(new URL(`/api/v1${path}`, url), {
      method,
      redirect: "error",
      signal: AbortSignal.timeout(30000),
      headers: {
        "Content-Type": "application/json",
        Origin: url.origin,
        "X-SocialMEI-Client": "browser",
        ...(cookie ? { Cookie: cookie } : {}),
        ...(credentials.basic
          ? { Authorization: `Basic ${Buffer.from(credentials.basic).toString("base64")}` }
          : {}),
        ...(identity
          ? {
              "X-SocialMEI-CSRF": identity.csrf_token,
              "X-SocialMEI-Identity": `${identity.usuario.id}:${identity.negocio.id}`,
            }
          : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok)
      throw Error(`Operação ${method} ${path.split("?")[0]} recusada (HTTP ${response.status}).`);
    const cookies = response.headers.getSetCookie();
    if (cookies.length) cookie = cookies.map((value) => value.split(";")[0]).join("; ");
    const result = response.status === 204 ? null : await response.json();
    if (result?.csrf_token) identity = result;
    return result;
  };
  await api("/auth/login", "POST", { email: credentials.email, senha: credentials.senha });
  if (target) {
    if (
      identity?.usuario?.id !== target.userId ||
      identity.usuario.administrador_plataforma !== false
    )
      throw Error("Conta autenticada diferente da identidade autorizada no manifesto.");
    if (identity?.negocio?.id !== target.workspaceId) {
      const workspaces = await api("/auth/workspaces");
      const matches = workspaces.items?.filter((item) => item.id === target.workspaceId);
      if (
        matches?.length !== 1 ||
        matches[0].nome !== businessName(target) ||
        matches[0].role !== "owner"
      )
        throw Error("Negócio autorizado ausente ou sem propriedade na conta autenticada.");
      await api("/auth/workspaces/switch", "POST", { workspace_id: target.workspaceId });
    }
    guardIdentity(target, await api("/auth/session"));
  }
  return api;
}

async function main() {
  const args = process.argv.slice(2);
  const option = (name) => args[args.indexOf(name) + 1];
  const allowed = new Set(["--target", "--account-file", "--inventory", "--apply"]);
  for (let i = 0; i < args.length; i++) {
    if (!allowed.has(args[i])) throw Error("Argumento desconhecido.");
    if (args[i] !== "--apply" && (!args[++i] || args[i].startsWith("--")))
      throw Error("Argumento sem valor.");
  }
  if (!["--target", "--account-file", "--inventory"].every((key) => args.includes(key)))
    throw Error(
      "Uso: node tools/provision-mei-demo.mjs --target alvo.json --account-file conta-privada.json --inventory inventario.json [--apply]",
    );
  const target = validateTarget(JSON.parse(readFileSync(option("--target"), "utf8")));
  const credentials = JSON.parse(readFileSync(option("--account-file"), "utf8"));
  const inventory = resolve(option("--inventory"));
  if ([option("--target"), option("--account-file")].some((path) => resolve(path) === inventory))
    throw Error("Inventário precisa de arquivo separado do alvo e das credenciais.");
  const api = await createApi(target.origin, credentials, target);
  const report = await provisionDemo(api, target, {
    apply: args.includes("--apply"),
    checkpoint: (value) => {
      writeFileSync(inventory, JSON.stringify(value, null, 2) + "\n", { mode: 0o600 });
    },
  });
  console.log(
    `${report.mode}: ${report.business}; ${report.records.length} registros inventariados; concluído=${report.complete}.`,
  );
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch(() => {
    // HTTP bodies, passwords, tokens and private paths never reach stdout/stderr.
    console.error(
      "Provisionamento interrompido. Confira alvo, conta, aprovação e inventário privado; repita com o mesmo manifesto após resolver a falha.",
    );
    process.exitCode = 1;
  });
