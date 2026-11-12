import { createHash, randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const fail = (code) => {
  throw new Error(code);
};
export function migrationManifest(root = ROOT) {
  const python = process.platform === "win32" ? "python" : "python3";
  const identity = JSON.parse(
    command(python, [
      join(root, "tools/team-release-profile.py"),
      "--source",
      root,
      "--profile",
      "039",
    ]),
  );
  const hashes = identity.migrations,
    names = Object.keys(hashes);
  return {
    names,
    source_migrations: hashes,
    baseline_migrations: Object.fromEntries(names.slice(0, 35).map((name) => [name, hashes[name]])),
  };
}
export function parseOptions(argv) {
  const options = { run: false, docker: "docker", postgresImage: "postgres:16-alpine" };
  const fields = {
    "--docker": "docker",
    "--api-image": "apiImage",
    "--source-sha": "sourceSha",
    "--receipt": "receipt",
  };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--run") options.run = true;
    else if (fields[argv[i]] && argv[i + 1] && !argv[i + 1].startsWith("--"))
      options[fields[argv[i]]] = argv[++i];
    else fail("unknown_or_incomplete_argument");
  }
  if (
    options.run &&
    (!/^[a-f0-9]{40}$/.test(options.sourceSha || "") ||
      !/^(?:sha256:)?[a-f0-9]{64}$/.test(options.apiImage || ""))
  )
    fail("exact_source_and_image_required");
  return options;
}
export function workspacePath(root, path) {
  const target = resolve(root, path),
    rel = relative(root, target);
  if (!rel || rel.startsWith("..") || isAbsolute(rel)) fail("artifact_outside_workspace");
  return target;
}
export function localDocker(endpoint) {
  return (
    typeof endpoint === "string" &&
    (endpoint === "unix:///var/run/docker.sock" ||
      /^npipe:\/\/\/+\.\/pipe\/(?:docker_engine|dockerDesktopLinuxEngine)$/.test(endpoint))
  );
}

export function canonicalExpression(expression) {
  // The existing Direct check is flattened by PostgreSQL when its dump is parsed.
  const nestedTextCheck =
    "CHECK ((((octet_length(text) >= 1) AND (octet_length(text) <= 1000)) AND (length(btrim(text)) > 0)))";
  if (expression === nestedTextCheck)
    return "CHECK (((octet_length(text) >= 1) AND (octet_length(text) <= 1000) AND (length(btrim(text)) > 0)))";
  // pg_dump/restore distributes this lossless cast over varchar literal arrays.
  const literal = "'(?:[^']|'')*'::character varying";
  const array = new RegExp(
    "\\(ARRAY\\[(" + literal + "(?:,\\s*" + literal + ")*)\\]\\)::text\\[\\]",
    "g",
  );
  return expression.replace(
    array,
    (_, items) =>
      "ARRAY[" + items.replace(new RegExp("(" + literal + ")", "g"), "($1)::text") + "]",
  );
}

function canonicalSchema(raw) {
  const value = JSON.parse(raw);
  for (const constraint of value.constraints || [])
    constraint[2] = canonicalExpression(constraint[2]);
  for (const index of value.indexes || []) index.indexdef = canonicalExpression(index.indexdef);
  return JSON.stringify(value);
}

const SEED = `
INSERT INTO socialmei.workspaces(id,slug,nome,configuracao) VALUES
 (1001,'release35-synthetic-a','Empresa fictícia A','{"horario":"09:00–18:00"}'),
 (1002,'release35-synthetic-b','Empresa fictícia B','{}');
INSERT INTO socialmei.users(id,email,nome) VALUES (2001,'rehearsal-a@example.test','Operador fictício A'),(2002,'rehearsal-b@example.test','Operador fictício B');
INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES (1001,2001,'owner'),(1002,2002,'owner');
INSERT INTO socialmei.crm_clientes(id,workspace_id,nome) VALUES (3001,1001,'Cliente fictício A'),(3002,1002,'Cliente fictício B');
INSERT INTO socialmei.crm_produtos(id,workspace_id,nome,tipo,preco,estoque,minimo) VALUES (4001,1001,'Produto fictício','Produto',25,8,1),(4002,1002,'Serviço fictício','Serviço',40,NULL,NULL);
INSERT INTO socialmei.crm_canais(id,workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned) VALUES
 (5001,1001,'rehearsal-a','synthetic','1000001@c.us',true,true),(5002,1002,'rehearsal-b','synthetic','1000002@c.us',true,true);
INSERT INTO socialmei.me_conversations(id,workspace_id,channel,account_ref,contact_ref,contact_name,origin) VALUES
 (6001,1001,'whatsapp','waha:1000001@c.us','waha:2000001@c.us','Contato fictício A','waha'),
 (6002,1002,'whatsapp','waha:1000002@c.us','waha:2000002@c.us','Contato fictício B','waha');
INSERT INTO socialmei.me_messages(id,workspace_id,conversation_id,external_message_id,fingerprint,conversation_revision,text,origin) VALUES
 (7001,1001,6001,'synthetic-rehearsal-a',repeat('a',64),1,'Mensagem exclusivamente fictícia A','waha'),
 (7002,1002,6002,'synthetic-rehearsal-b',repeat('b',64),1,'Mensagem exclusivamente fictícia B','waha');
INSERT INTO socialmei.crm_vendas(id,workspace_id,cliente_id,produto_id,cliente,item,tipo_item,data,quantidade,preco,valor,pagamento,status) VALUES
 (8001,1001,3001,4001,'Cliente fictício A','Produto fictício','Produto','2026-10-31',2,25,50,'Pix','Pago');
INSERT INTO socialmei.crm_financeiro(id,workspace_id,cliente_id,descricao,tipo,valor,vencimento,status) VALUES
 (9001,1001,3001,'Receita fictícia de demonstração','receita',50,'2026-10-31','aberto');
SELECT setval('socialmei.workspaces_id_seq',1002),setval('socialmei.users_id_seq',2002),
 setval('socialmei.crm_clientes_id_seq',3002),setval('socialmei.crm_produtos_id_seq',4002),
 setval('socialmei.crm_canais_id_seq',5002),setval('socialmei.me_conversations_id_seq',6002),
 setval('socialmei.me_messages_id_seq',7002),setval('socialmei.crm_vendas_id_seq',8001),setval('socialmei.crm_financeiro_id_seq',9001);
`;

export const CONTRACT = `
BEGIN;
SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='15s';
CREATE FUNCTION pg_temp.expect_rejection(command text, expected text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual text;
BEGIN
 BEGIN EXECUTE command; EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE; END;
 IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'constraint_rejection_missing'; END IF;
END $$;
INSERT INTO socialmei.agenda_reminders(workspace_id,id,title,scheduled_for,cliente_id,creation_fingerprint)
 VALUES(1001,'00000000-0000-4000-8000-000000000001','Lembrete fictício','2026-10-31T12:00:00Z',3001,repeat('a',64));
SELECT pg_temp.expect_rejection($q$INSERT INTO socialmei.agenda_reminders(workspace_id,id,title,scheduled_for,cliente_id,creation_fingerprint) VALUES(1001,'00000000-0000-4000-8000-000000000002','Inválido',NOW(),3002,repeat('a',64))$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_reminders SET status='sent'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_reminders SET revision=9007199254740992$q$,'23514');
INSERT INTO socialmei.wa_human_replies(workspace_id,id,channel_id,conversation_id,source_message_id,binding_hash,fingerprint,text,created_by)
 VALUES(1001,'00000000-0000-4000-8000-000000000011',5001,6001,7001,repeat('a',64),repeat('b',64),'Resposta fictícia',2001);
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.wa_human_replies SET channel_id=5002$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.wa_human_replies SET conversation_id=6002$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.wa_human_replies SET source_message_id=7002$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.wa_human_replies SET created_by=2002$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.wa_human_replies SET status='invalid'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.wa_human_replies SET status='dispatching'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.wa_human_replies SET status='confirmed',claimed_at=NOW(),finished_at=NOW()$q$,'23514');
UPDATE socialmei.wa_human_replies SET status='confirmed',provider_message_id='synthetic-provider-receipt',claimed_at=NOW(),finished_at=NOW();
SELECT pg_temp.expect_rejection($q$INSERT INTO socialmei.wa_human_replies(workspace_id,id,channel_id,conversation_id,source_message_id,binding_hash,fingerprint,text,status,provider_message_id,claimed_at,finished_at) VALUES(1001,'00000000-0000-4000-8000-000000000012',5001,6001,7001,repeat('a',64),repeat('b',64),'Resposta fictícia','confirmed','synthetic-provider-receipt',NOW(),NOW())$q$,'23505');
UPDATE socialmei.agenda_reminders SET cliente_id=NULL;
DELETE FROM socialmei.workspace_members WHERE workspace_id=1001 AND user_id=2001;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM socialmei.wa_human_replies WHERE created_by IS NOT NULL) OR NOT EXISTS(SELECT 1 FROM socialmei.wa_human_replies WHERE workspace_id=1001) THEN RAISE EXCEPTION 'member_delete_contract_invalid'; END IF;
 IF (SELECT count(*) FROM pg_constraint WHERE conrelid IN ('socialmei.agenda_reminders'::regclass,'socialmei.wa_human_replies'::regclass) AND contype='f' AND convalidated) <> 6 THEN RAISE EXCEPTION 'tenant_fk_contract_invalid'; END IF;
 IF (SELECT count(*) FROM pg_indexes WHERE schemaname='socialmei' AND indexname IN ('ix_agenda_reminders_workspace_schedule','ix_wa_human_reply_history','ux_wa_human_provider_receipt')) <> 3 THEN RAISE EXCEPTION 'index_contract_invalid'; END IF;
END $$;

INSERT INTO socialmei.crm_produtos(id,workspace_id,nome,tipo,preco,estoque,minimo,duracao_minutos,categoria,descricao) VALUES(4003,1001,'Servico ficticio 039','Servi\u00e7o',50,NULL,NULL,30,'Servicos','Descricao ficticia');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.crm_produtos SET duracao_minutos=0 WHERE id=4003$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.crm_produtos SET duracao_minutos=30 WHERE id=4001$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.crm_produtos SET categoria=NULL WHERE id=4003$q$,'23502');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.crm_produtos SET descricao=repeat('x',2001) WHERE id=4003$q$,'22001');
INSERT INTO socialmei.agenda_resources(workspace_id,id,nome,creation_fingerprint) VALUES
 (1001,'00000000-0000-4000-8000-000000000021','Recurso A',repeat('a',64)),
 (1002,'00000000-0000-4000-8000-000000000022','Recurso B',repeat('b',64));
INSERT INTO socialmei.agenda_appointments(workspace_id,id,cliente_id,servico_id,resource_id,client_name,service_name,duration_minutes,price,scheduled_for,ends_at,creation_fingerprint)
VALUES(1001,'00000000-0000-4000-8000-000000000031',3001,4003,'00000000-0000-4000-8000-000000000021','Cliente A','Servico A',30,50,'2026-11-03T12:00:00Z','2026-11-03T12:30:00Z',repeat('a',64));
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_appointments SET cliente_id=3002$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_appointments SET servico_id=4002$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_appointments SET resource_id='00000000-0000-4000-8000-000000000022'$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_appointments SET ends_at=ends_at+INTERVAL '1 minute'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_appointments SET status='sent'$q$,'23514');
INSERT INTO socialmei.agenda_appointment_history(workspace_id,appointment_id,revision,scheduled_for,ends_at,status) SELECT workspace_id,id,revision,scheduled_for,ends_at,status FROM socialmei.agenda_appointments;
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.agenda_appointment_history SET workspace_id=1002$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.me_conversations SET cliente_id=3002 WHERE id=6001$q$,'23503');
CREATE TEMP TABLE contact_revision_before ON COMMIT DROP AS SELECT revision FROM socialmei.me_conversations WHERE id=6001;
UPDATE socialmei.me_conversations SET cliente_id=3001 WHERE id=6001;
DO $$ BEGIN IF (SELECT revision FROM socialmei.me_conversations WHERE id=6001)<>(SELECT revision+1 FROM contact_revision_before) THEN RAISE EXCEPTION 'customer_link_revision_missing'; END IF; END $$;
DELETE FROM socialmei.crm_clientes WHERE id=3001;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM socialmei.me_conversations WHERE id=6001 AND cliente_id IS NULL AND revision=(SELECT revision+2 FROM contact_revision_before)) THEN RAISE EXCEPTION 'customer_unlink_revision_missing'; END IF;
 IF (SELECT count(*) FROM pg_tables WHERE schemaname='socialmei')<>76 THEN RAISE EXCEPTION '039_table_count_invalid'; END IF;
 IF (SELECT count(*) FROM pg_indexes WHERE schemaname='socialmei' AND indexname IN ('ix_appointments_resource_schedule','ix_me_conversation_customer'))<>2 THEN RAISE EXCEPTION '039_indexes_missing'; END IF;
END $$;


-- Profile 039: create a synthetic Instagram conversation, then verify its tenant-bound menu state.
INSERT INTO socialmei.me_conversations(id,workspace_id,channel,account_ref,contact_ref,contact_name,origin)
 VALUES (6003,1001,'instagram','instagram:111111','instagram:222222','Contato fictício Instagram','instagram');
INSERT INTO socialmei.me_messages(id,workspace_id,conversation_id,external_message_id,fingerprint,conversation_revision,text,origin)
 VALUES (7003,1001,6003,'synthetic-ig-039',repeat('c',64),1,'Mensagem fictícia Instagram','instagram');
INSERT INTO socialmei.ig_menu_conversations(workspace_id,conversation_id,last_message_id)
 VALUES(1001,6003,7003);
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.ig_menu_conversations SET state='not_a_state' WHERE workspace_id=1001 AND conversation_id=6003$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.ig_menu_conversations SET conversation_id=6002 WHERE workspace_id=1001 AND conversation_id=6003$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.ig_menu_conversations SET last_message_id=7002 WHERE workspace_id=1001 AND conversation_id=6003$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.ig_menu_conversations SET revision=-1 WHERE workspace_id=1001 AND conversation_id=6003$q$,'23514');
DO $$ BEGIN
 IF (SELECT count(*) FROM pg_constraint WHERE conrelid IN (
   'socialmei.ig_menu_conversations'::regclass,'socialmei.ig_menu_replies'::regclass
 ) AND contype='f' AND convalidated) <> 7 THEN RAISE EXCEPTION '039_tenant_fk_contract_invalid'; END IF;
 IF (SELECT count(*) FROM pg_indexes WHERE schemaname='socialmei'
   AND indexname IN ('ux_ig_menu_provider_receipt','ix_ig_menu_conversation_history')) <> 2
 THEN RAISE EXCEPTION '039_receipt_indexes_missing'; END IF;
END $$;

ROLLBACK;
`;

let diagnosticStage = "startup";

function command(binary, args, { input, binaryOutput = false, timeout = 120000 } = {}) {
  const result = spawnSync(binary, args, {
    cwd: ROOT,
    input,
    encoding: binaryOutput ? null : "utf8",
    windowsHide: true,
    timeout,
    maxBuffer: 32 * 1024 * 1024,
  });
  if (result.error || result.status !== 0) {
    const phase = args.includes("/workspace/tools/team_migrate.py")
      ? "migrator"
      : args.includes("pg_restore")
        ? "backup_restore"
        : args.includes("pg_dump")
          ? "backup_dump"
          : args.includes("psql")
            ? "database_check"
            : args.includes("pg_isready")
              ? "database_startup"
              : "command";
    if (phase === "database_check" && diagnosticStage === "contract039") {
      // Disposable fixtures only; print a bounded PostgreSQL error summary, never SQL input.
      const stderr = String(result.stderr || "");
      const diagnostics = stderr
        .split(/\r?\n/)
        .filter((line) => /ERROR:|DETAIL:|CONTEXT:/.test(line))
        .map((line) => line.slice(0, 200))
        .slice(0, 5);
      if (diagnostics.length) console.error("039_SYNTHETIC_CONTRACT:", diagnostics.join(" | "));
    }
    fail("rehearsal_" + phase + "_failed_" + diagnosticStage);
  }
  return result.stdout;
}

export async function rehearse(options, root = ROOT) {
  const manifest = migrationManifest(root);
  if (!options.run)
    return {
      mode: "plan",
      profile: "039",
      baseline: "035",
      ...manifest,
      production_data_used: false,
      production_runtime_changed: false,
      provider_messages_sent: false,
    };
  if (process.env.DOCKER_HOST && !localDocker(process.env.DOCKER_HOST))
    fail("local_docker_required");
  const docker = (...args) => command(options.docker, args);
  const context = JSON.parse(docker("context", "inspect"));
  if (context.length !== 1 || !localDocker(context[0]?.Endpoints?.docker?.Host))
    fail("local_docker_required");
  const images = JSON.parse(docker("image", "inspect", options.apiImage));
  const image = images[0],
    revision = image?.Config?.Labels?.["org.opencontainers.image.revision"];
  if (
    images.length !== 1 ||
    revision !== options.sourceSha ||
    !/^sha256:[a-f0-9]{64}$/.test(image.Id || "")
  )
    fail("source_image_revision_mismatch");
  const head = command("git", ["-C", root, "rev-parse", "HEAD"]).trim();
  if (head !== options.sourceSha) fail("source_checkout_revision_mismatch");
  const dirty =
    command("git", ["-C", root, "status", "--porcelain=v1", "--untracked-files=all"]).trim() !== "";
  let originalUnchanged = true;
  for (const name of manifest.names.slice(0, 35)) {
    const committed = command("git", ["-C", root, "show", "HEAD:database/migrations/" + name]);
    if (sha256(committed.replace(/\r\n/g, "\n")) !== manifest.source_migrations[name])
      originalUnchanged = false;
  }
  if (!originalUnchanged) fail("original_migrations_changed");
  if (dirty) fail("clean_source_required");
  const token = randomBytes(6).toString("hex"),
    label = "socialmei.migration-rehearsal=" + token;
  const artifact = workspacePath(root, ".preview/migration-rehearsal-" + token);
  const receiptPath = workspacePath(
    root,
    options.receipt || relative(root, join(artifact, "receipt.json")),
  );
  if (existsSync(receiptPath)) fail("receipt_already_exists");
  mkdirSync(join(artifact, "migrations035"), { recursive: true });
  for (const name of manifest.names.slice(0, 35))
    writeFileSync(
      join(artifact, "migrations035", name),
      readFileSync(join(root, "database/migrations", name)),
      { flag: "wx" },
    );
  const networkName = "socialmei-rehearsal38-" + token,
    sourceName = networkName + "-source",
    targetName = networkName + "-restored";
  let network = null,
    receipt = null;
  const containers = [];
  const inspectOwned = (id, networkResource = false) => {
    const rows = JSON.parse(
      docker(...(networkResource ? ["network", "inspect", id] : ["inspect", id])),
    );
    if (
      rows.length !== 1 ||
      (networkResource ? rows[0].Labels : rows[0].Config?.Labels)?.[
        "socialmei.migration-rehearsal"
      ] !== token
    )
      fail("cleanup_target_not_owned");
  };
  const sql = (name, statement, database = "rehearsal35") =>
    command(
      options.docker,
      [
        "exec",
        "-i",
        name,
        "psql",
        "-X",
        "-U",
        "rehearsal",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-Atq",
      ],
      { input: statement },
    ).trim();
  const ledger = (name, database) =>
    sql(name, "SELECT version FROM socialmei.schema_migrations ORDER BY version;", database).split(
      /\r?\n/,
    );
  const tableNames = (name) =>
    JSON.parse(
      sql(
        name,
        "SELECT json_agg(tablename ORDER BY tablename) FROM pg_tables WHERE schemaname='socialmei';",
      ),
    );
  const sequences = (name) =>
    sql(
      name,
      "SELECT COALESCE(jsonb_agg(to_jsonb(s) ORDER BY sequencename),'[]'::jsonb)::text FROM pg_sequences s WHERE schemaname='socialmei';",
    );
  const snapshot = (name, tables, schema = false, legacy = false) => {
    const names = tables.map((table) => "'" + table.replace(/'/g, "''") + "'").join(",");
    if (schema)
      return canonicalSchema(
        sql(
          name,
          `SELECT jsonb_build_object('columns',(SELECT jsonb_agg(to_jsonb(c) ORDER BY table_name,ordinal_position) FROM information_schema.columns c WHERE table_schema='socialmei' AND table_name IN (${names})),'constraints',(SELECT jsonb_agg(jsonb_build_array(t.relname,c.conname,pg_get_constraintdef(c.oid)) ORDER BY t.relname,c.conname) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='socialmei' AND t.relname IN (${names})),'indexes',(SELECT jsonb_agg(to_jsonb(i) ORDER BY tablename,indexname) FROM pg_indexes i WHERE schemaname='socialmei' AND tablename IN (${names})))::text;`,
        ),
      );
    const rows = tables
      .filter((table) => table !== "schema_migrations")
      .map(
        (table) =>
          `SELECT '${table.replace(/'/g, "''")}' AS table_name,COALESCE(jsonb_agg(value ORDER BY value::text),'[]'::jsonb) AS rows FROM (SELECT ${legacy && table === "crm_produtos" ? "to_jsonb(t) - ARRAY['duracao_minutos','categoria','descricao']" : legacy && table === "me_conversations" ? "to_jsonb(t) - 'cliente_id'" : "to_jsonb(t)"} AS value FROM socialmei."${table.replace(/"/g, '""')}" t) x`,
      );
    return sql(
      name,
      `SELECT jsonb_object_agg(table_name,rows)::text FROM (${rows.join(" UNION ALL ")}) snapshots;`,
    );
  };
  let apiRuns = 0;
  const migrate = (host, directory, database = "rehearsal35") => {
    const name = networkName + "-migrator-" + ++apiRuns;
    command(options.docker, [
      "run",
      "--rm",
      "--name",
      name,
      "--label",
      label,
      "--network",
      networkName,
      "-v",
      root + ":/workspace:ro",
      "-v",
      directory + ":/migrations:ro",
      "-e",
      "PYTHONPATH=/workspace/python-service",
      "-e",
      "DATABASE_URL=",
      "-e",
      "POSTGRES_PASSWORD=",
      "-e",
      "POSTGRES_HOST=" + host,
      "-e",
      "POSTGRES_PORT=5432",
      "-e",
      "POSTGRES_USER=rehearsal",
      "-e",
      "POSTGRES_DB=" + database,
      image.Id,
      "python",
      "/workspace/tools/team_migrate.py",
    ]);
  };
  try {
    network = docker("network", "create", "--internal", "--label", label, networkName).trim();
    if (!/^[a-f0-9]{64}$/.test(network)) fail("isolated_network_not_created");
    for (const name of [sourceName, targetName]) {
      const id = docker(
        "run",
        "-d",
        "--name",
        name,
        "--label",
        label,
        "--network",
        networkName,
        "-e",
        "POSTGRES_USER=rehearsal",
        "-e",
        "POSTGRES_DB=rehearsal35",
        "-e",
        "POSTGRES_HOST_AUTH_METHOD=trust",
        options.postgresImage,
      ).trim();
      if (!/^[a-f0-9]{64}$/.test(id)) fail("isolated_postgres_not_created");
      containers.push(id);
      let ready = false;
      for (let attempt = 0; attempt < 60; attempt++) {
        try {
          docker(
            "exec",
            name,
            "pg_isready",
            "-h",
            "127.0.0.1",
            "-U",
            "rehearsal",
            "-d",
            "rehearsal35",
          );
          ready = true;
          break;
        } catch {
          await new Promise((resolveWait) => setTimeout(resolveWait, 500));
        }
      }
      if (!ready) fail("isolated_postgres_not_ready");
      if (sql(name, "SELECT current_setting('server_version_num')::int / 10000;") !== "16")
        fail("postgres_16_required");
    }
    diagnosticStage = "baseline_restore";
    migrate(sourceName, join(artifact, "migrations035"));
    if (JSON.stringify(ledger(sourceName)) !== JSON.stringify(manifest.names.slice(0, 35)))
      fail("baseline_ledger_invalid");
    diagnosticStage = "baseline_seed";
    sql(sourceName, SEED);
    const tables = tableNames(sourceName),
      before = snapshot(sourceName, tables),
      schema = snapshot(sourceName, tables, true);
    const sequenceState = sequences(sourceName);
    const baselineLedgerRows = sql(
      sourceName,
      "SELECT jsonb_agg(to_jsonb(t) ORDER BY version)::text FROM socialmei.schema_migrations t;",
    );
    const dump = command(
      options.docker,
      [
        "exec",
        sourceName,
        "pg_dump",
        "-U",
        "rehearsal",
        "-d",
        "rehearsal35",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
      ],
      { binaryOutput: true },
    );
    if (!dump.length || dump.subarray(0, 5).toString() !== "PGDMP") fail("backup_format_invalid");
    writeFileSync(join(artifact, "synthetic035.dump"), dump, { flag: "wx", mode: 0o600 });
    const persistedDump = readFileSync(join(artifact, "synthetic035.dump"));
    if (sha256(persistedDump) !== sha256(dump)) fail("backup_readback_mismatch");
    command(
      options.docker,
      [
        "exec",
        "-i",
        targetName,
        "pg_restore",
        "-U",
        "rehearsal",
        "-d",
        "rehearsal35",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-privileges",
      ],
      { input: persistedDump },
    );
    if (
      snapshot(targetName, tables) !== before ||
      snapshot(targetName, tables, true) !== schema ||
      sequences(targetName) !== sequenceState ||
      JSON.stringify(ledger(targetName)) !== JSON.stringify(manifest.names.slice(0, 35))
    )
      fail("isolated_restore_diverged");
    const legacySchemaPreserved = (current) => {
      const old = JSON.parse(schema),
        after = JSON.parse(current);
      return Object.entries(old).every(([group, rows]) =>
        (rows || []).every((row) =>
          (after[group] || []).some((item) => JSON.stringify(item) === JSON.stringify(row)),
        ),
      );
    };
    // An incompatible pre-existing relation must abort the official transaction.
    sql(targetName, "CREATE DATABASE rehearsal_incompatible TEMPLATE rehearsal35;", "postgres");
    sql(
      targetName,
      "CREATE TABLE socialmei.agenda_resources(workspace_id BIGINT,id UUID,nome TEXT);",
      "rehearsal_incompatible",
    );
    let incompatibleRejected = false;
    try {
      migrate(targetName, join(root, "database/migrations"), "rehearsal_incompatible");
    } catch {
      incompatibleRejected = true;
    }
    if (
      !incompatibleRejected ||
      JSON.stringify(ledger(targetName, "rehearsal_incompatible")) !==
        JSON.stringify(manifest.names.slice(0, 35)) ||
      sql(
        targetName,
        "SELECT to_regclass('socialmei.agenda_appointments') IS NULL;",
        "rehearsal_incompatible",
      ) !== "t" ||
      sql(
        targetName,
        "SELECT count(*) FROM information_schema.columns WHERE table_schema='socialmei' AND table_name='crm_produtos' AND column_name='duracao_minutos';",
        "rehearsal_incompatible",
      ) !== "0"
    )
      fail("incompatible_migration_not_atomic");
    diagnosticStage = "upgrade039";
    migrate(targetName, join(root, "database/migrations"));
    if (
      snapshot(targetName, tables, false, true) !== before ||
      !legacySchemaPreserved(snapshot(targetName, tables, true)) ||
      sequences(targetName) !== sequenceState ||
      JSON.stringify(ledger(targetName)) !== JSON.stringify(manifest.names)
    )
      fail("migration_preservation_failed");
    if (
      sql(
        targetName,
        "SELECT jsonb_agg(to_jsonb(t) ORDER BY version)::text FROM socialmei.schema_migrations t WHERE version<'036';",
      ) !== baselineLedgerRows
    )
      fail("baseline_ledger_timestamps_changed");
    diagnosticStage = "contract039";
    sql(targetName, CONTRACT);
    sql(
      targetName,
      `BEGIN;
      UPDATE socialmei.crm_produtos SET duracao_minutos=30,categoria='Servicos',descricao='Descricao sintetica 039' WHERE id=4002;
      INSERT INTO socialmei.agenda_resources(workspace_id,id,nome,creation_fingerprint) VALUES(1002,'00000000-0000-4000-8000-000000000041','Recurso ficticio persistido',repeat('d',64));
      INSERT INTO socialmei.agenda_appointments(workspace_id,id,cliente_id,servico_id,resource_id,client_name,service_name,duration_minutes,price,scheduled_for,ends_at,creation_fingerprint)
      VALUES(1002,'00000000-0000-4000-8000-000000000042',3002,4002,'00000000-0000-4000-8000-000000000041','Cliente B','Servico B',30,40,'2026-11-03T14:00:00Z','2026-11-03T14:30:00Z',repeat('e',64));
      INSERT INTO socialmei.agenda_appointment_history(workspace_id,appointment_id,revision,scheduled_for,ends_at,status) SELECT workspace_id,id,revision,scheduled_for,ends_at,status FROM socialmei.agenda_appointments;
      UPDATE socialmei.me_conversations SET cliente_id=3002 WHERE id=6002;
      COMMIT;`,
    );
    diagnosticStage = "post_contract_039";
    const migratedTables = tableNames(targetName),
      after = snapshot(targetName, migratedTables),
      appliedLedger = sql(
        targetName,
        "SELECT jsonb_agg(to_jsonb(t) ORDER BY version)::text FROM socialmei.schema_migrations t;",
      );
    migrate(targetName, join(root, "database/migrations"));
    if (
      snapshot(targetName, migratedTables) !== after ||
      sql(
        targetName,
        "SELECT jsonb_agg(to_jsonb(t) ORDER BY version)::text FROM socialmei.schema_migrations t;",
      ) !== appliedLedger
    )
      fail("migration_reapply_changed_data");
    // Retry the raw additive SQL as well as the official ledger-aware migrator.
    for (const name of manifest.names.slice(35))
      sql(targetName, readFileSync(join(root, "database/migrations", name), "utf8"));
    if (snapshot(targetName, migratedTables) !== after) fail("raw_migration_retry_changed_data");
    const upgradedSchema = snapshot(targetName, migratedTables, true),
      upgradedSequences = sequences(targetName);
    const upgradedDump = command(
      options.docker,
      [
        "exec",
        targetName,
        "pg_dump",
        "-U",
        "rehearsal",
        "-d",
        "rehearsal35",
        "-Fc",
        "--no-owner",
        "--no-privileges",
      ],
      { binaryOutput: true },
    );
    if (!upgradedDump.length || upgradedDump.subarray(0, 5).toString() !== "PGDMP")
      fail("upgraded_backup_invalid");
    writeFileSync(join(artifact, "synthetic039.dump"), upgradedDump, { flag: "wx", mode: 0o600 });
    sql(sourceName, "DROP DATABASE rehearsal35;", "postgres");
    sql(sourceName, "CREATE DATABASE rehearsal35;", "postgres");
    command(
      options.docker,
      [
        "exec",
        "-i",
        sourceName,
        "pg_restore",
        "-U",
        "rehearsal",
        "-d",
        "rehearsal35",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-privileges",
      ],
      { input: readFileSync(join(artifact, "synthetic039.dump")) },
    );
    if (
      snapshot(sourceName, migratedTables) !== after ||
      snapshot(sourceName, migratedTables, true) !== upgradedSchema ||
      sequences(sourceName) !== upgradedSequences ||
      JSON.stringify(ledger(sourceName)) !== JSON.stringify(manifest.names)
    )
      fail("upgraded_restore_diverged");
    receipt = {
      format: "socialmei-migration-rehearsal-v1",
      profile: "039",
      baseline: "035",
      source_sha: options.sourceSha,
      source_dirty: dirty,
      source_migrations: manifest.source_migrations,
      baseline_migrations: manifest.baseline_migrations,
      api_image_id: image.Id,
      api_image_revision: revision,
      backup_sha256: sha256(dump),
      upgraded_backup_sha256: sha256(upgradedDump),
      upgraded_backup_restore_verified: true,
      isolated: true,
      disposable: true,
      restored_backup_verified: true,
      existing_data_preserved: true,
      migration_reapply_verified: true,
      constraints_verified: true,
      schema_contract_verified: true,
      original_migrations_unchanged: originalUnchanged,
      backwards_compatible_reads_verified: true,
      backwards_compatible_reads_scope:
        "035 original-column SQL projections; old application binary not executed",
      sequences_preserved: true,
      incompatible_state_rejected: incompatibleRejected,
      production_data_used: false,
      production_runtime_changed: false,
      provider_messages_sent: false,
      created_at: new Date().toISOString(),
    };
  } finally {
    for (const id of containers.reverse()) {
      inspectOwned(id);
      docker("rm", "-f", "-v", id);
    }
    if (network) {
      inspectOwned(network, true);
      docker("network", "rm", network);
    }
  }
  receipt.isolated_cleanup_verified = true;
  mkdirSync(dirname(receiptPath), { recursive: true });
  writeFileSync(receiptPath, JSON.stringify(receipt, null, 2) + "\n", { flag: "wx", mode: 0o600 });
  return receipt;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  rehearse(parseOptions(process.argv.slice(2)))
    .then((receipt) => console.log(JSON.stringify(receipt, null, 2)))
    .catch((error) => {
      console.error(
        /^[a-z0-9_]+$/.test(error.message)
          ? error.message
          : "migration_rehearsal_failed_details_suppressed",
      );
      process.exitCode = 1;
    });
}
