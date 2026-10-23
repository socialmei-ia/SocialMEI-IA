// Build an allowlisted static artifact; this tool never publishes it.
import { readFile, mkdir, writeFile, rm } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, "test-results/public-demo");
const files = [
  ["frontend/testes-publicos.html", "index.html"],
  ["frontend/reference/Oportunidades-V8-original.html", "reference/Oportunidades-V8-original.html"],
  ["frontend/reference/Divulgacao-V4-original.html", "reference/Divulgacao-V4-original.html"],
];
const originals = await Promise.all(
  files.map(async ([source]) => readFile(resolve(root, source), "utf8")),
);
const scriptHashes = originals.flatMap((html) =>
  [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(
    (match) => "'sha256-" + createHash("sha256").update(match[1]).digest("base64") + "'",
  ),
);
const policy =
  "default-src 'none'; script-src " +
  scriptHashes.join(" ") +
  "; style-src 'unsafe-inline'; img-src 'self' data: blob:; media-src blob: data:; connect-src 'none'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'";
await rm(output, { recursive: true, force: true });
await mkdir(resolve(output, "reference"), { recursive: true });
const manifest = {
  sha: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
  workingTreeDirty: Boolean(
    execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }).trim(),
  ),
  published: false,
  assets: [],
  files: [],
};
for (const [source, target] of files) {
  const original = await readFile(resolve(root, source), "utf8");
  const notice =
    target === "index.html"
      ? ""
      : '<aside aria-label="Ambiente demonstrativo" style="position:relative;z-index:1;padding:8px 16px;background:#10233e;color:#eef3fb;font:13px/1.5 system-ui;text-align:center">Demonstração · use somente dados fictícios · nada é enviado ou sincronizado. <a href="../index.html" style="color:inherit">Voltar ao laboratório</a></aside>';
  // The golden masters stay byte-identical; only the distributed copy receives this narrow mobile containment fix.
  const containment = target.includes("Oportunidades")
    ? "<style>@media(max-width:980px){.tbi,.tbr{flex-wrap:wrap}.tbr{max-width:100%}.tbi{align-items:flex-start}.wrap,.wk,.filters{min-width:0;max-width:100%}}</style>"
    : "";
  const html = original
    .replace(
      /<head>/i,
      '<head><meta name="robots" content="noindex,nofollow"><meta http-equiv="Content-Security-Policy" content="' +
        policy +
        '"><meta name="referrer" content="no-referrer">',
    )
    .replace(/<\/head>/i, containment + "</head>")
    .replace(/(<body[^>]*>)/i, "$1" + notice);
  await writeFile(resolve(output, target), html);
  manifest.files.push({
    source,
    target,
    sourceSha256: createHash("sha256").update(original).digest("hex"),
    sha256: createHash("sha256").update(html).digest("hex"),
  });
}
async function asset(target, content) {
  await writeFile(resolve(output, target), content);
  manifest.assets.push({ target, sha256: createHash("sha256").update(content).digest("hex") });
}
await asset(
  "_headers",
  "/*\n  Cache-Control: no-store\n  Referrer-Policy: no-referrer\n  X-Content-Type-Options: nosniff\n  Content-Security-Policy: " +
    policy +
    "; frame-ancestors 'none'\n  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()\n  Cross-Origin-Opener-Policy: same-origin\n  Cross-Origin-Resource-Policy: same-origin\n",
);
await asset(
  "README.txt",
  "Candidata NÃO publicada. Servir index.html por HTTP local ou HTTPS em origem EXCLUSIVA, sem cookies de domínio do CRM. Apenas dados fictícios; armazenamento local da origem, sem sincronização. Não copiar outros arquivos do repositório. _headers depende do provedor; aplicar cabeçalhos equivalentes. Sem backend/API. Rollback: restaurar artefato anterior ou retirar a hospedagem. Ver docs/PUBLIC-PROTOTYPE-BETA.md.\nSHA: " +
    manifest.sha +
    "\n",
);
await asset(
  "404.html",
  '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Página não encontrada · SocialMEI.IA</title></head><body><h1>Página não encontrada</h1><p>Este laboratório não possui API ou login.</p><a href="/">Voltar à demonstração</a></body></html>',
);
await asset("robots.txt", "User-agent: *\nDisallow: /\n");
await writeFile(resolve(output, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log("Static candidate prepared: test-results/public-demo; no publication performed.");
