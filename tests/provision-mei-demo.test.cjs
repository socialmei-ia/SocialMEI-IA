const { test, before } = require("node:test");
const assert = require("node:assert/strict");
let fixture, guardIdentity, operationId, provisionDemo, validateTarget, createApi;
before(async () => {
  ({ fixture, guardIdentity, operationId, provisionDemo, validateTarget, createApi } =
    await import("../tools/provision-mei-demo.mjs"));
});

const target = {
  business: "Brilho Limpeza",
  workspaceId: 23,
  userId: 71,
  anchorDate: "2026-11-19",
};
function fakeApi(options = {}) {
  let serial = 100,
    reads = 0;
  const identity = {
    usuario: { id: 71, administrador_plataforma: false },
    negocio: {
      id: 23,
      nome: "Brilho Limpeza",
      slug: "brilho-limpeza",
      configuracao: { horario: "Preservado" },
    },
    papel: "owner",
  };
  const calls = [],
    operations = new Map(),
    resources = new Map(),
    appointments = new Map();
  const imports = { clientes: [], produtos: [] };
  const rows = { clientes: [], produtos: [] };
  let profile = { revision: 0, profile: null },
    policy = { revision: 0 };
  const api = async (path, method = "GET", body) => {
    calls.push({ path, method, body: structuredClone(body) });
    if (path === "/auth/session") {
      reads++;
      return structuredClone(options.identity?.(reads, identity) ?? identity);
    }
    if (path === "/workspace-profile" && method === "GET") return structuredClone(profile);
    if (path === "/workspace-profile") {
      profile = { profile: body.profile, revision: 1 };
      return profile;
    }
    if (path === "/agenda/channel-booking" && method === "GET") return structuredClone(policy);
    if (path === "/agenda/channel-booking") {
      policy = { ...body, revision: 1 };
      return policy;
    }
    if (path === "/auth/profile") return identity;
    for (const kind of ["clientes", "produtos"]) {
      const idField = kind === "clientes" ? "cliente_id" : "produto_id";
      if (path === `/${kind}`) return structuredClone(rows[kind]);
      if (path === `/${kind}/importacoes/preview`)
        return {
          pode_importar: true,
          itens: body.itens.map((item) => ({
            local_id: item.local_id,
            acao: imports[kind].some((row) => row.local_id === item.local_id)
              ? "existente"
              : "criar",
          })),
        };
      if (path === `/${kind}/importacoes/confirmar`) {
        if (!imports[kind].length)
          imports[kind] = body.itens.map((item) => {
            const id = serial++;
            rows[kind].push({ id, ...(item.cliente ?? item.produto) });
            return { local_id: item.local_id, [idField]: id };
          });
        return { itens: structuredClone(imports[kind]) };
      }
    }
    if (path.startsWith("/reporting/overview")) return {};
    if (method === "PATCH" && path.startsWith("/agenda/appointments/")) {
      const entry = appointments.get(path.split("/").at(-1));
      assert.equal(body.expected_revision, entry.revision);
      Object.assign(entry, { status: body.status, revision: entry.revision + 1 });
      return structuredClone(entry);
    }
    assert.ok(
      [
        "/agenda/resources",
        "/agenda/appointments",
        "/vendas",
        "/financeiro",
        "/opportunities",
        "/agenda",
      ].includes(path) || /^\/vendas\/\d+\/pagar$/.test(path),
      `Unauthorized endpoint ${path}`,
    );
    const key = `${path}:${body.operation_id}`;
    const fingerprint = JSON.stringify(body);
    if (operations.has(key)) {
      assert.equal(
        operations.get(key).fingerprint,
        fingerprint,
        "Retry must retain its exact payload",
      );
      if (path === "/agenda/appointments")
        return structuredClone(appointments.get(body.operation_id));
      return structuredClone(operations.get(key).result);
    }
    const result = {
      id: path.startsWith("/agenda/") ? body.operation_id : serial++,
      revision: 1,
      versao: 1,
      status: "pending",
    };
    operations.set(key, { fingerprint, result: structuredClone(result) });
    if (path === "/agenda/appointments") appointments.set(result.id, structuredClone(result));
    if (path === "/agenda/resources") resources.set(result.id, result);
    if (options.failOnce === path) {
      options.failOnce = null;
      throw Error("Lost response after persistence");
    }
    return structuredClone(result);
  };
  return { api, calls, operations, imports, rows, resources, appointments };
}

test("target accepts only the two authorized businesses and a fixed valid date", () => {
  assert.equal(validateTarget(target), target);
  for (const patch of [
    { business: "team" },
    { workspaceId: 0 },
    { userId: "71" },
    { anchorDate: "2026-02-30" },
  ])
    assert.throws(() => validateTarget({ ...target, ...patch }));
  assert.notEqual(
    operationId(target, "sale-0"),
    operationId({ ...target, workspaceId: 24 }, "sale-0"),
  );
  assert.equal(operationId(target, "sale-0"), operationId(target, "sale-0"));
});

test("dry-run inspects without data mutations or synthetic messages", async () => {
  const fake = fakeApi();
  const result = await provisionDemo(fake.api, target);
  assert.equal(result.mode, "dry-run");
  assert.equal(result.planned.appointments, 4);
  assert.equal(fake.operations.size, 0);
  assert.equal(fake.calls.filter((call) => call.method !== "GET").length, 2);
  assert.ok(
    fake.calls
      .filter((call) => call.method !== "GET")
      .every((call) => call.path.endsWith("/preview")),
  );
});

test("repeated apply retains IDs, booking states and exact write fingerprints", async () => {
  const fake = fakeApi();
  const first = await provisionDemo(fake.api, target, { apply: true });
  const count = fake.operations.size;
  const second = await provisionDemo(fake.api, target, { apply: true });
  assert.equal(first.complete, true);
  assert.equal(second.complete, true);
  assert.equal(fake.operations.size, count);
  assert.deepEqual(
    first.records.filter((row) => !["profile", "policy"].includes(row.kind)),
    second.records,
  );
  assert.equal(fake.rows.clientes.length, 4);
  assert.equal(fake.rows.produtos.length, 3);
  assert.equal(fake.resources.size, 2);
  assert.deepEqual(
    [...fake.appointments.values()].map((row) => row.status),
    ["done", "cancelled", "pending", "pending"],
  );
  assert.equal(
    fake.calls.filter((call) => call.path === "/agenda/channel-booking" && call.method === "PUT")
      .length,
    1,
  );
  assert.equal(fake.calls.find((call) => call.method === "PUT").body.policy.enabled, false);
});

test("fixed pending dates preserve historical dates, anchor and operation IDs across replay", async () => {
  const planned = { ...target, pendingStartDate: "2026-11-23" };
  assert.deepEqual(fixture(planned).appointmentDates, [
    "2026-11-17",
    "2026-11-18",
    "2026-11-23",
    "2026-11-24",
  ]);
  assert.deepEqual(fixture(target).appointmentDates, [
    "2026-11-17",
    "2026-11-18",
    "2026-11-19",
    "2026-11-20",
  ]);
  for (let index = 0; index < 4; index++)
    assert.equal(
      operationId(planned, `appointment-${index}`),
      operationId(target, `appointment-${index}`),
    );
  const fake = fakeApi();
  const dry = await provisionDemo(fake.api, planned);
  assert.deepEqual(dry.appointmentDates, fixture(planned).appointmentDates);
  assert.equal(dry.anchorDate, target.anchorDate);
  assert.equal(dry.pendingStartDate, "2026-11-23");
  await provisionDemo(fake.api, planned, { apply: true });
  const count = fake.operations.size;
  await provisionDemo(fake.api, planned, { apply: true });
  assert.equal(fake.operations.size, count);
  const writes = fake.calls.filter(
    (call) => call.path === "/agenda/appointments" && call.method === "POST",
  );
  assert.deepEqual(
    writes.slice(0, 4).map((call) => call.body),
    writes.slice(4).map((call) => call.body),
  );
  assert.deepEqual(
    writes.slice(0, 4).map((call) => call.body.scheduled_for),
    fixture(planned).appointmentDates.map((date) => `${date}T09:00:00-03:00`),
  );
  assert.ok(new Date(writes[2].body.scheduled_for) > new Date("2026-11-20T13:00:00Z"));
});

test("pending start date rejects invalid dates and preserves an explicit fixed future date", () => {
  for (const pendingStartDate of [null, 1, "2026-02-30", "2026-11-19", "2026-11-18", "bad"])
    assert.throws(() => validateTarget({ ...target, pendingStartDate }));
  assert.equal(
    validateTarget({ ...target, pendingStartDate: "2026-11-23" }).pendingStartDate,
    "2026-11-23",
  );
});

test("lost response after persistence resumes without duplicate records", async () => {
  const fake = fakeApi({ failOnce: "/financeiro" });
  let inventory;
  await assert.rejects(
    provisionDemo(fake.api, target, {
      apply: true,
      checkpoint: (value) => {
        inventory = value;
      },
    }),
    /Lost response/,
  );
  assert.equal(inventory.complete, false);
  assert.ok(inventory.records.some((row) => row.kind === "sale"));
  const result = await provisionDemo(fake.api, target, { apply: true });
  assert.equal(result.complete, true);
  assert.equal(
    [...fake.operations.keys()].filter((key) => key.startsWith("/financeiro:")).length,
    3,
  );
  assert.equal(fake.rows.clientes.length, 4);
});

test("changed workspace on pre-write recheck prevents any write", async () => {
  const fake = fakeApi({
    identity: (reads, current) =>
      reads > 1 ? { ...current, negocio: { ...current.negocio, id: 24 } } : current,
  });
  await assert.rejects(provisionDemo(fake.api, target, { apply: true }), /Sessão recusada/);
  assert.equal(fake.operations.size, 0);
  assert.ok(
    !fake.calls.some(
      (call) =>
        call.method === "PATCH" || call.method === "PUT" || call.path.endsWith("/confirmar"),
    ),
  );
});

test("platform admin and unverified accounts cannot seed a business", async () => {
  const fake = fakeApi();
  const identity = await fake.api("/auth/session");
  for (const patch of [
    { usuario: { ...identity.usuario, administrador_plataforma: true } },
    { papel: "member" },
    { email_verification: { required: true, verified: false } },
  ])
    assert.throws(() => guardIdentity(target, { ...identity, ...patch }), /Sessão recusada/);
});

test("existing Brilho business alias is matched exactly without renaming or duplication", async () => {
  const actual = {
    ...target,
    workspaceId: 60,
    userId: 33,
    expectedBusinessName: "Brilho&Limpeza Service",
  };
  const identity = {
    usuario: { id: 33, administrador_plataforma: false },
    negocio: { id: 60, nome: "Brilho&Limpeza Service", slug: "existing-brilho" },
    papel: "owner",
  };
  assert.equal(guardIdentity(actual, identity), identity);
  assert.equal(fixture(actual).profile.businessName, "Brilho&Limpeza Service");
  assert.throws(() =>
    guardIdentity(actual, {
      ...identity,
      negocio: { ...identity.negocio, nome: "Brilho Limpeza" },
    }),
  );
  assert.throws(() =>
    validateTarget({ ...actual, expectedBusinessName: "Empresa não autorizada" }),
  );
});

test("same-name records without stable import origin block duplicate creation", async () => {
  const fake = fakeApi();
  fake.rows.clientes.push({ id: 999, nome: fixture(target).clients[0].nome });
  await assert.rejects(provisionDemo(fake.api, target, { apply: true }), /sem vínculo de origem/);
  assert.equal(fake.operations.size, 0);
});

test("fixture data never include contact numbers, CNPJ or real external identities", () => {
  for (const business of ["Brilho Limpeza", "Bella Store"]) {
    const data = fixture({ ...target, business });
    for (const client of data.clients) {
      assert.ok(client.email.endsWith("@example.test"));
      assert.ok(client.nome.endsWith("FICTÍCIO"));
      assert.equal(client.telefone, undefined);
      assert.equal(client.instagram, undefined);
    }
  }
});

test("HTTP adapter rejects non-HTTPS and embedded credentials before connecting", async () => {
  for (const origin of [
    "http://localhost",
    "https://user:pass@example.test",
    "https://example.test/path",
    "https://example.test?token=private",
  ])
    await assert.rejects(createApi(origin, {}), /origem HTTPS/);
});

test("native fetch adapter authenticates and carries cookie, CSRF and exact account identity", async () => {
  const original = globalThis.fetch;
  const calls = [];
  const identity = { usuario: { id: 71 }, negocio: { id: 23 }, csrf_token: "test-csrf" };
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options });
    return new Response(JSON.stringify(identity), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        ...(calls.length === 1
          ? { "Set-Cookie": "socialmei-session=test-cookie; Secure; HttpOnly" }
          : {}),
      },
    });
  };
  try {
    const api = await createApi("https://demo.example.test", {
      email: "owner@example.test",
      senha: "local-test-password",
    });
    await api("/auth/session");
    assert.equal(calls[0].url, "https://demo.example.test/api/v1/auth/login");
    assert.equal(calls[0].options.method, "POST");
    assert.equal(calls[1].options.headers.Cookie, "socialmei-session=test-cookie");
    assert.equal(calls[1].options.headers["X-SocialMEI-CSRF"], "test-csrf");
    assert.equal(calls[1].options.headers["X-SocialMEI-Identity"], "71:23");
    globalThis.fetch = async () => new Response("private-data-must-not-leak", { status: 401 });
    await assert.rejects(
      api("/auth/session"),
      (error) => error.message.includes("HTTP 401") && !error.message.includes("private-data"),
    );
  } finally {
    globalThis.fetch = original;
  }
});
