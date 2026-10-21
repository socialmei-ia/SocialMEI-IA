import { existsSync, mkdirSync, readFileSync, writeFileSync, lstatSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export function validateEnvironment(env) {
  for (const key of Object.keys(env)) {
    if (
      (key.startsWith("COMPOSE_") ||
        [
          "DOCKER_HOST",
          "DOCKER_CONTEXT",
          "DOCKER_TLS_VERIFY",
          "DOCKER_CERT_PATH",
          "DATABASE_URL",
          "PREVIEW_POSTGRES_PASSWORD",
          "PREVIEW_TEST_KEY",
        ].includes(key)) &&
      env[key]
    ) {
      throw new Error(`Remova ${key} do ambiente antes de usar o preview isolado.`);
    }
  }
}

export function validateDockerEndpoint(endpoint) {
  if (
    typeof endpoint !== "string" ||
    !(endpoint.startsWith("unix:///") || endpoint.startsWith("npipe:////./pipe/"))
  ) {
    throw new Error(
      "O preview exige um Docker local (socket Unix ou pipe local do Docker Desktop).",
    );
  }
}

export function ensurePreviewEnv(directory) {
  if (existsSync(directory) && lstatSync(directory).isSymbolicLink())
    throw new Error("Diretório de configuração inválido.");
  mkdirSync(directory, { recursive: true });
  const file = join(directory, ".env");
  if (!existsSync(file)) {
    writeFileSync(
      file,
      `PREVIEW_POSTGRES_PASSWORD=${randomBytes(32).toString("hex")}\nPREVIEW_TEST_KEY=${randomBytes(32).toString("hex")}\n`,
      { mode: 0o600, flag: "wx" },
    );
  }
  if (
    lstatSync(file).isSymbolicLink() ||
    !/^PREVIEW_POSTGRES_PASSWORD=[a-f0-9]{64}\nPREVIEW_TEST_KEY=[a-f0-9]{64}\n$/.test(
      readFileSync(file, "utf8"),
    )
  ) {
    throw new Error(
      "Arquivo de configuração do preview inválido; preserve-o para análise e gere um novo ambiente local.",
    );
  }
  return file;
}

export function composeArguments(command, file) {
  const commands = {
    up: ["up", "-d", "--build", "--wait", "--wait-timeout", "180"],
    status: ["ps"],
    down: ["down"],
    check: ["config", "--quiet"],
  };
  if (!Object.hasOwn(commands, command))
    throw new Error("Comando inválido. Use up, status, down ou check.");
  return [
    "compose",
    "--project-name",
    "socialmei-preview",
    "--env-file",
    file,
    "-f",
    "compose.preview.yaml",
    ...commands[command],
  ];
}

function inspectDocker() {
  const inspect = spawnSync(
    "docker",
    ["context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
    { cwd: root, encoding: "utf8" },
  );
  if (inspect.error || inspect.status !== 0)
    throw new Error("Docker local indisponível. Abra o Docker Desktop em modo Linux.");
  let endpoint;
  try {
    endpoint = JSON.parse(inspect.stdout.trim());
  } catch {
    throw new Error("Não foi possível validar o contexto Docker local.");
  }
  validateDockerEndpoint(endpoint);
  const info = spawnSync("docker", ["info", "--format", "{{.OSType}}"], {
    cwd: root,
    encoding: "utf8",
  });
  if (info.error || info.status !== 0 || info.stdout.trim() !== "linux")
    throw new Error("O preview exige Docker local em modo Linux.");
}

export function main(command = process.argv[2] || "up") {
  validateEnvironment(process.env);
  composeArguments(command, "");
  inspectDocker();
  const file = ensurePreviewEnv(join(root, ".preview"));
  const result = spawnSync("docker", composeArguments(command, file), {
    cwd: root,
    stdio: "inherit",
  });
  if (result.error || result.status !== 0)
    throw new Error(
      "A operação do preview falhou; nenhuma implantação em produção foi solicitada.",
    );
  const revision = spawnSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" });
  console.log(
    `Preview local · SHA ${revision.status === 0 ? revision.stdout.trim() : "não disponível"} · ${command}: concluído.`,
  );
  if (command === "up") {
    console.log(
      "Abra https://localhost:8443 — certificado local: o navegador pode solicitar confiança.",
    );
    console.log(
      "Use somente dados fictícios. Autenticação individual habilitada; cadastre uma conta de teste.",
    );
    console.log(
      "Instagram, WAHA, n8n e IA: simulações/laboratório, sem publicação ou envio automático.",
    );
  }
  if (command === "down")
    console.log("Somente o preview foi encerrado; o volume local foi preservado.");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
