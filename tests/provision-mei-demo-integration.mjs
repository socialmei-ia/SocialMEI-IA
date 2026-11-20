import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { provisionDemo } from "../tools/provision-mei-demo.mjs";

const database = new URL(process.env.TEST_DATABASE_URL ?? "http://invalid");
if (
  process.env.SOCIALMEI_DEMO_DISPOSABLE_TESTS !== "1" ||
  !["localhost", "127.0.0.1"].includes(database.hostname) ||
  database.port !== "55491" ||
  database.pathname !== "/socialmei_demo_test"
)
  throw Error(
    "Set TEST_DATABASE_URL to the disposable loopback:55491 DB and SOCIALMEI_DEMO_DISPOSABLE_TESTS=1.",
  );

const child = spawn(
  process.env.MEI_DEMO_TEST_PYTHON ?? "python",
  [fileURLToPath(new URL("./mei-demo-api-bridge.py", import.meta.url))],
  {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
  },
);
const pending = new Map();
let serial = 0,
  stderr = "";
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
});
const lines = createInterface({ input: child.stdout });
let readyResolve, readyReject;
const ready = new Promise((resolve, reject) => {
  readyResolve = resolve;
  readyReject = reject;
});
lines.on("line", (line) => {
  const result = JSON.parse(line);
  if (result.ready) return readyResolve();
  const task = pending.get(result.id);
  if (!task) return;
  pending.delete(result.id);
  if (result.error) task.reject(Error(`Bridge ${result.error}`));
  else task.resolve(result);
});
child.on("exit", (code) => {
  const error = Error(`Disposable bridge ended (${code}): ${stderr.slice(-1500)}`);
  readyReject(error);
  for (const task of pending.values()) task.reject(error);
});
child.on("error", (error) => {
  readyReject(error);
  for (const task of pending.values()) task.reject(error);
});
const command = (message) =>
  new Promise((resolve, reject) => {
    const id = ++serial;
    pending.set(id, { resolve, reject });
    child.stdin.write(JSON.stringify({ id, ...message }) + "\n");
  });
const apiFor =
  (account) =>
  async (path, method = "GET", body) => {
    const response = await command({ action: "request", account, path, method, body });
    if (response.status >= 400)
      throw Error(
        `API ${method} ${path}: HTTP ${response.status}: ${JSON.stringify(response.body)}`,
      );
    return response.body;
  };
const snapshot = async (account) => (await command({ action: "snapshot", account })).body;
try {
  await ready;
  const targets = {};
  for (const [account, business, expectedBusinessName] of [
    ["brilho", "Brilho Limpeza", "Brilho&Limpeza Service"],
    ["bella", "Bella Store", "Bella Store"],
  ]) {
    const response = await command({ action: "register", account, business: expectedBusinessName });
    assert.equal(response.status, 200, JSON.stringify(response.body));
    targets[account] = {
      business,
      expectedBusinessName,
      workspaceId: response.body.negocio.id,
      userId: response.body.usuario.id,
      anchorDate: "2026-11-19",
    };
  }
  const a = apiFor("brilho"),
    b = apiFor("bella");
  const beforeA = await snapshot("brilho"),
    beforeB = await snapshot("bella");
  await provisionDemo(a, targets.brilho);
  assert.deepEqual(await snapshot("brilho"), beforeA, "Dry-run must not write business records");
  let fail = true,
    checkpoint;
  const lostResponse = async (path, method, body) => {
    const result = await a(path, method, body);
    if (path === "/financeiro" && method === "POST" && fail) {
      fail = false;
      throw Error("Injected lost response after PostgreSQL commit");
    }
    return result;
  };
  await assert.rejects(
    provisionDemo(lostResponse, targets.brilho, {
      apply: true,
      checkpoint: (value) => {
        checkpoint = value;
      },
    }),
    /lost response/,
  );
  assert.equal(checkpoint.complete, false);
  const firstA = await provisionDemo(a, targets.brilho, { apply: true });
  const afterA = await snapshot("brilho");
  const againA = await provisionDemo(a, targets.brilho, { apply: true });
  assert.equal(firstA.complete, true);
  assert.equal(againA.complete, true);
  assert.deepEqual(await snapshot("brilho"), afterA, "Replay must retain persisted counts");
  assert.deepEqual(await snapshot("bella"), beforeB, "Other workspace must remain unchanged");
  for (const [table, count] of Object.entries({
    crm_clientes: 4,
    crm_produtos: 3,
    agenda_resources: 2,
    agenda_appointments: 4,
    crm_vendas: 2,
    crm_financeiro: 3,
    crm_opportunities: 2,
    agenda_reminders: 2,
  }))
    assert.equal(afterA[table], count, table);
  assert.deepEqual(
    afterA.transport_global,
    beforeA.transport_global,
    "No channel or external message creation",
  );
  await provisionDemo(b, targets.bella, { apply: true });
  const afterB = await snapshot("bella");
  await provisionDemo(b, targets.bella, { apply: true });
  assert.deepEqual(await snapshot("bella"), afterB);
  assert.deepEqual(await snapshot("brilho"), afterA);
  assert.equal(afterB.agenda_appointments, 0);
  assert.equal(afterB.crm_clientes, 4);
  await assert.rejects(provisionDemo(b, targets.brilho, { apply: true }), /Sessão recusada/);
  const forged = await command({
    action: "request",
    account: "bella",
    path: "/clientes",
    method: "POST",
    headers: { "X-SocialMEI-Identity": `${targets.brilho.userId}:${targets.brilho.workspaceId}` },
    body: { nome: "Forbidden foreign write" },
  });
  assert.equal(forged.status, 409);
  assert.deepEqual(await snapshot("bella"), afterB);
  const appointments = await a(
    "/agenda/appointments?from_date=2026-11-01&to_date=2026-11-30&include_cancelled=true",
  );
  assert.deepEqual(appointments.items.map((row) => row.status).sort(), [
    "cancelled",
    "done",
    "pending",
    "pending",
  ]);
  assert.equal((await b("/produtos")).filter((row) => row.estoque === 19).length, 2);
  console.log(
    "PASS real FastAPI/PostgreSQL: 2 independent accounts, dry-run, lost-response recovery, apply twice, immutable counts, booking states, stock and cross-workspace refusal; no external messages/channels.",
  );
} finally {
  child.stdin.end();
  lines.close();
}
