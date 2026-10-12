import { existsSync, copyFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const command = process.argv[2] || "help";
const envFile = ".env.development";
const envExample = ".env.development.example";
const composeArgs = ["compose", "--env-file", envFile, "-f", "compose.dev.yaml"];

function runDocker(args) {
  const result = spawnSync("docker", [...composeArgs, ...args], {
    stdio: "inherit",
  });

  if (result.error) {
    console.error("\nNão foi possível executar Docker.");
    console.error("Confirme se Docker Desktop/Engine está instalado e aberto.");
    process.exit(1);
  }

  process.exitCode = result.status ?? 1;
}

function ensureEnv() {
  if (existsSync(envFile)) return;

  if (!existsSync(envExample)) {
    console.error(`Arquivo ${envExample} não encontrado.`);
    process.exit(1);
  }

  copyFileSync(envExample, envFile);
  console.log(`Criado ${envFile} a partir de ${envExample}.`);
  console.log("Os valores são somente para desenvolvimento local.");
}

switch (command) {
  case "setup":
    ensureEnv();
    console.log("\nPronto. Próximo passo: npm run dev");
    console.log("Frontend: http://localhost:5500");
    console.log("n8n:      http://localhost:5678");
    console.log("API:      http://localhost:8000/health");
    break;

  case "up":
    ensureEnv();
    runDocker(["up", "-d", "--build", "frontend", "postgres", "n8n", "python-api"]);
    break;

  case "up-tools":
    ensureEnv();
    runDocker(["--profile", "tools", "up", "-d", "--build"]);
    break;

  case "up-waha":
    ensureEnv();
    runDocker(["--profile", "waha", "up", "-d", "--build"]);
    break;

  case "down":
    ensureEnv();
    runDocker(["down"]);
    break;

  case "status":
    ensureEnv();
    runDocker(["ps"]);
    break;

  case "logs": {
    ensureEnv();
    const service = process.argv[3];
    const args = ["logs", "--tail", "150", "-f"];
    if (service) args.push(service);
    runDocker(args);
    break;
  }

  case "config":
    ensureEnv();
    runDocker(["config", "--quiet"]);
    break;

  default:
    console.log(`
SocialMEI — ambiente local

npm run setup       cria .env.development
npm run dev         sobe frontend + PostgreSQL + n8n + FastAPI
npm run dev:tools   inclui pgAdmin
npm run dev:waha    inclui WAHA
npm run status      mostra containers
npm run logs        acompanha logs
npm run stop        encerra o ambiente
npm run dev:config  valida o Compose local
`);
}
