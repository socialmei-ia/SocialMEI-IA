#!/usr/bin/env python3
"""Inventario sanitizado e somente leitura dos workflows vivos do n8n team.

Nunca imprime tokens, parametros, URLs, mensagens, pinData ou credenciais.
Nao altera, executa, publica ou desativa workflows.
"""
import argparse
import getpass
import json
import re
import subprocess
import sys
import unicodedata

CONTAINER = "socialmei-n8n"
NODE_SCRIPT = r"""
(async () => {
  let key = "";
  for await (const chunk of process.stdin) key += chunk.toString();
  if (!key.trim()) throw new Error("api_key_absent");
  const base = "http://127.0.0.1:5678/api/v1";
  async function read(path, optional = false) {
    const response = await fetch(base + path, {
      method: "GET",
      headers: { "X-N8N-API-KEY": key.trim() },
      signal: AbortSignal.timeout(12000)
    });
    if (!response.ok) {
      if (optional) return null;
      throw new Error("api_unavailable_" + response.status);
    }
    return response.json();
  }
  const allowed = [
    "webhook", "switch", "httpRequest", "agent",
    "lmChatGroq", "lmChatGoogleGemini", "memoryBufferWindow",
    "postgres", "code", "formTrigger", "wait",
    "toolWorkflow", "executeWorkflow", "scheduleTrigger",
    "respondToWebhook", "manualTrigger", "set", "if"
  ];
  function stats(nodes) {
    if (!Array.isArray(nodes)) return null;
    const types = {};
    let fixedBearer = false;
    let templatedAuth = false;
    for (const node of nodes) {
      const type = typeof node.type === "string" ? node.type.split(".").pop() : "";
      if (allowed.includes(type)) types[type] = (types[type] || 0) + 1;
      // Somente flags booleanas. Nunca copiar cabecalho ou seu valor.
      if (type === "httpRequest") {
        if (node.parameters?.genericAuthType === "httpTemplatedCustomAuth") {
          templatedAuth = true;
        }
        const headers = node.parameters?.headerParameters?.parameters;
        if (Array.isArray(headers) && headers.some(h =>
          String(h.name || "").toLowerCase() === "authorization" &&
          typeof h.value === "string" &&
          /^Bearer\s+/i.test(h.value) &&
          !h.value.startsWith("=")
        )) fixedBearer = true;
      }
    }
    return {
      total: nodes.length,
      desabilitados: nodes.filter(n => n.disabled === true).length,
      tipos: types,
      bearer_fixo_presente: fixedBearer,
      auth_template_presente: templatedAuth
    };
  }
  let cursor = null, list = [];
  do {
    const page = await read("/workflows?limit=100" +
      (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""));
    if (!Array.isArray(page.data)) throw new Error("unexpected_response");
    list.push(...page.data);
    cursor = page.nextCursor || null;
    if (list.length > 1000) throw new Error("too_many_workflows");
  } while (cursor);
  const output = [];
  for (const row of list) {
    if (!/^[A-Za-z0-9_-]{1,100}$/.test(String(row.id))) continue;
    const w = await read("/workflows/" + row.id + "?excludePinnedData=true");
    let live = null;
    if (w.active && w.activeVersionId) {
      const v = await read("/workflows/" + row.id + "/versions/" +
        encodeURIComponent(w.activeVersionId), true);
      if (v) live = stats(v.nodes);
    }
    output.push({
      id: String(w.id),
      nome: typeof w.name === "string" ? w.name : "",
      ativo: w.active === true,
      atualizado_em: typeof w.updatedAt === "string" ? w.updatedAt : null,
      criado_em: typeof w.createdAt === "string" ? w.createdAt : null,
      salvo: stats(w.nodes),
      publicado: live,
      versoes_diferentes: w.active === true && w.activeVersionId
        ? w.versionId !== w.activeVersionId : null
    });
  }
  console.log(JSON.stringify({ok:true, workflows:output}));
})().catch(() => {
  // Nunca imprimir erro de rede, URL, resposta HTTP ou configuracao.
  console.log(JSON.stringify({ok:false, motivo:"consulta_indisponivel"}));
});
"""


def safe_name(raw):
    if not isinstance(raw, str):
        return "Nome nao identificado"
    if re.search(r"(?:IGAG|EAAB|sk-|gh[pousr]_|n8n_api_)[A-Za-z0-9_-]{8,}", raw, re.I):
        return "[nome oculto: possivel segredo]"
    value = re.sub(r"https?://\S+", "[URL]", raw)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", value)
    value = re.sub(r"[A-Za-z0-9_-]{40,}", "[identificador]", value)
    value = "".join(c for c in value if c.isprintable())
    return value[:85] or "Sem nome"


def category(name):
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    if re.search(r"instagram|direct|reels|stories|feed", normalized):
        if re.search(r"\b(?:publica\w*|post(?:s|agem)?|reels?|stori(?:es|e)?|feed)\b", normalized):
            return "instagram_publicacao"
        return "instagram_direct_ou_conta"
    if re.search(r"whats|waha|whatza|menu interativo", normalized):
        return "whatsapp"
    if re.search(r"sentim|emoc|analise|classific", normalized):
        return "analise"
    if re.search(r"orcament|pedido|catalog|produto|estoque", normalized):
        return "catalogo_e_pedidos"
    if re.search(r"atend|caixa|chat|mensagen", normalized):
        return "caixa_e_atendimento"
    if re.search(r"relator", normalized):
        return "relatorios"
    if re.search(r"python|teste|test|hello", normalized):
        return "teste_ou_suporte"
    return "outros"


def summarise(workflows, recent_since="2026-10-20"):
    rows = []
    for item in workflows:
        if not isinstance(item, dict):
            continue
        saved = item.get("salvo") if isinstance(item.get("salvo"), dict) else {}
        live = item.get("publicado") if isinstance(item.get("publicado"), dict) else {}
        raw_name = item.get("nome", "")
        when = item.get("atualizado_em")
        when = when if isinstance(when, str) and re.match(r"^20\d\d-\d\d-\d\dT", when) else None
        rows.append({
            "id": item.get("id") if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", str(item.get("id", ""))) else "nao_identificado",
            "nome": safe_name(raw_name),
            "familia": category(raw_name if isinstance(raw_name, str) else ""),
            "ativo": item.get("ativo") is True,
            "atualizado_em": when,
            "nos_salvos": saved.get("total"),
            "nos_publicados": live.get("total"),
            "tipos_salvos": saved.get("tipos", {}),
            "versoes_diferentes": item.get("versoes_diferentes") is True,
            "bearer_fixo_no_rascunho": saved.get("bearer_fixo_presente") is True,
            "auth_template_no_rascunho": saved.get("auth_template_presente") is True,
        })
    rows.sort(key=lambda r: (r["atualizado_em"] or "", r["id"]), reverse=True)
    return {
        "modo": "somente_leitura",
        "altera_producao": False,
        "total_workflows": len(rows),
        "ativos": sum(row["ativo"] for row in rows),
        "atualizados_desde": recent_since,
        "recentes": [row for row in rows if row["atualizado_em"] and row["atualizado_em"][:10] >= recent_since],
        "demais": [row for row in rows if not row["atualizado_em"] or row["atualizado_em"][:10] < recent_since],
        "nota": "Os tipos nao comprovam funcionamento real, credenciais validas nem integracao com o site."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=("team",))
    args = parser.parse_args()
    if args.target != "team":
        parser.error("Alvo nao permitido.")
    key = getpass.getpass("Chave da API n8n (nao aparece na tela): ")
    if not key.strip():
        raise SystemExit("Chave ausente. Nada foi alterado.")
    try:
        result = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "node", "-e", NODE_SCRIPT],
            input=key,
            capture_output=True,
            text=True,
            timeout=180,
            check=False
        )
        if result.returncode:
            raise RuntimeError("container")
        data = json.loads(result.stdout)
        if not data.get("ok") or not isinstance(data.get("workflows"), list):
            raise RuntimeError("api")
        print(json.dumps(summarise(data["workflows"]), ensure_ascii=False, indent=2))
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError):
        raise SystemExit("Inventario nao concluido. Nenhuma alteracao realizada.") from None
    finally:
        key = ""


if __name__ == "__main__":
    main()
