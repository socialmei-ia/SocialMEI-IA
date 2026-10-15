#!/usr/bin/env python3
"""Build inactive structural templates; private node parameters are never copied."""

import argparse
import json
import math
import sys
import uuid
from pathlib import Path


WORKFLOWS = {
    "WWzhvmdPh9LrpuYy": ("00-caixa-local", "Caixa Unificada local — legado"),
    "BtvlHv4mt90tn70z": ("01-caixa-postgresql", "Caixa Unificada PostgreSQL"),
    "DDrphANXE8QdxoWy": ("02-atendimento", "Atendimento"),
    "AUpqr0ko77jQJ6DW": ("02a-consultar-produtos", "Consultar produtos"),
    "LV2rsbXIb3eE0Pb3": ("02b-registrar-pedido", "Registrar pedido"),
    "QAcfeKiXA6ZQQ4Mz": ("02c-confirmar-pedido", "Confirmar pedido"),
    "NDNF5doo9pLtj6sb": ("03-instagram", "Integração Instagram"),
    "EGXHkPjqt0Wiaxl4": ("04-conferir-conexao", "Conferir conexão"),
}

NODE_NAMES = {
    "n8n-nodes-base.code": "Código",
    "n8n-nodes-base.respondToWebhook": "Responder webhook",
    "n8n-nodes-base.webhook": "Receber webhook",
    "n8n-nodes-base.postgres": "PostgreSQL",
    "n8n-nodes-base.stickyNote": "Instruções",
    "n8n-nodes-base.executeWorkflowTrigger": "Receber chamada",
    "n8n-nodes-base.googleSheets": "Google Sheets",
    "n8n-nodes-base.googleSheetsTool": "Ferramenta Google Sheets",
    "n8n-nodes-base.if": "Condição",
    "n8n-nodes-base.set": "Preparar dados",
    "n8n-nodes-base.httpRequest": "Requisição HTTP",
    "n8n-nodes-base.switch": "Selecionar caminho",
    "n8n-nodes-base.manualTrigger": "Iniciar manualmente",
    "@n8n/n8n-nodes-langchain.agent": "Assistente",
    "@n8n/n8n-nodes-langchain.chatTrigger": "Receber chat",
    "@n8n/n8n-nodes-langchain.lmChatGroq": "Modelo Groq",
    "@n8n/n8n-nodes-langchain.lmChatGoogleGemini": "Modelo Gemini",
    "@n8n/n8n-nodes-langchain.memoryBufferWindow": "Memória",
    "@n8n/n8n-nodes-langchain.toolWorkflow": "Chamar subworkflow",
}
CONNECTION_TYPES = {"main", "ai_languageModel", "ai_memory", "ai_tool"}
NOTICE = "Template estrutural. Configuração privada e homologação pendentes. Não ativar."


def default_parameters(node_type):
    # Nenhum texto, código, SQL, URL ou configuração é copiado da instância.
    if node_type == "n8n-nodes-base.code":
        return {"jsCode": 'throw new Error("CONFIGURE_PRIVATELY: código não exportado");'}
    if node_type == "n8n-nodes-base.httpRequest":
        return {"url": "https://configure.example.invalid/", "options": {"timeout": 15000}}
    if node_type == "n8n-nodes-base.stickyNote":
        return {"content": NOTICE}
    return {}


def safe_index(value):
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError("Índice de conexão inválido.")
    return value


def build_template(document, workflow_id):
    if document.get("id") != workflow_id:
        raise ValueError("Identidade do workflow diferente da esperada.")
    slug, label = WORKFLOWS[workflow_id]
    raw_nodes = document.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes or len(raw_nodes) > 200:
        raise ValueError("Lista de nós inválida.")
    names = {}
    nodes = []
    for index, node in enumerate(raw_nodes):
        node_type = node.get("type")
        if node_type not in NODE_NAMES:
            raise ValueError("Tipo de nó ainda não revisado.")
        old_name = node.get("name")
        if not isinstance(old_name, str) or not old_name or old_name in names:
            raise ValueError("Nome de nó ausente ou duplicado.")
        version = node.get("typeVersion")
        if type(version) not in (int, float) or not math.isfinite(version) or not 1 <= version <= 10:
            raise ValueError("Versão de nó inválida.")
        name = f"{index + 1:02d} · {NODE_NAMES[node_type]}"
        names[old_name] = name
        nodes.append({
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"socialmei:structure:{slug}:{index}")),
            "name": name,
            "type": node_type,
            "typeVersion": version,
            "position": [(index % 4) * 280, (index // 4) * 220],
            "parameters": default_parameters(node_type),
            "disabled": True,
            "notes": NOTICE,
            "notesInFlow": True,
        })

    connections = {}
    raw_connections = document.get("connections")
    if not isinstance(raw_connections, dict):
        raise ValueError("Conexões ausentes.")
    for source, ports in raw_connections.items():
        if source not in names or not isinstance(ports, dict):
            raise ValueError("Origem de conexão inválida.")
        connections[names[source]] = {}
        for port_type, outputs in ports.items():
            if port_type not in CONNECTION_TYPES or not isinstance(outputs, list) or len(outputs) > 101:
                raise ValueError("Porta de conexão inválida.")
            public_outputs = []
            for output in outputs:
                if not isinstance(output, list):
                    raise ValueError("Saída de conexão inválida.")
                targets = []
                for target in output:
                    if target.get("node") not in names or target.get("type") not in CONNECTION_TYPES:
                        raise ValueError("Destino de conexão inválido.")
                    targets.append({
                        "node": names[target["node"]],
                        "type": target["type"],
                        "index": safe_index(target.get("index")),
                    })
                public_outputs.append(targets)
            connections[names[source]][port_type] = public_outputs

    return {
        "name": "[STRUCTURE] " + label,
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
    }


def export_templates(source, destination):
    source = source.resolve()
    destination = destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Origem privada e destino devem ser separados.")
    # Valida o conjunto completo antes de criar qualquer saída.
    templates = {}
    for workflow_id, (slug, _) in WORKFLOWS.items():
        path = source / f"{workflow_id}.json"
        if path.stat().st_size > 10_000_000:
            raise ValueError("Documento acima do tamanho esperado.")
        document = json.loads(path.read_text(encoding="utf-8"))
        templates[slug + ".json"] = build_template(document, workflow_id)
    if destination.exists():
        raise ValueError("O destino já existe; nenhum arquivo foi sobrescrito.")
    destination.mkdir(parents=True, mode=0o700)
    for name, template in templates.items():
        (destination / name).write_text(
            json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print("CONFIRMADO: oito templates estruturais inativos; todos os nós desabilitados.")
    print("Parâmetros, código, SQL, credenciais e dados privados não foram copiados.")
    print("Templates não substituem exports completos nem estão prontos para execução.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        export_templates(arguments.source_dir, arguments.output_dir)
    except Exception as error:
        # Mensagens de bibliotecas podem conter dados do documento privado.
        print(f"ETAPA INTERROMPIDA: exportação estrutural ({type(error).__name__}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
