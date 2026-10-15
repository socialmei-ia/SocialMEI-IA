"""Collect a limited, read-only inventory without printing private configuration."""

import argparse
import json
from pathlib import Path
import re
import subprocess

SERVICES = {
    "team-api": "socialmei-team-team-api-1",
    "team-gateway": "socialmei-team-team-gateway-1",
    "team-postgres": "socialmei-team-team-postgres-1",
    "n8n": "socialmei-n8n",
    "python-api": "socialmei-python",
    "python-runners": "socialmei-python-runners",
    "waha": "socialmei-waha",
}


def read_command(*args):
    result = subprocess.run(
        args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30
    )
    if result.returncode:
        raise RuntimeError("Read command failed")
    return result.stdout.strip()


def inspect_service(container):
    value = json.loads(read_command("docker", "inspect", container))[0]
    state = value["State"]
    return {
        "image_reference": value["Config"]["Image"],
        "image_id": value["Image"],
        "running": bool(state.get("Running")),
        "health": state.get("Health", {}).get("Status", "not_configured"),
        "started_at": state.get("StartedAt"),
        "networks": sorted(value.get("NetworkSettings", {}).get("Networks", {})),
        "volumes": sorted(
            mount["Name"]
            for mount in value.get("Mounts", [])
            if mount.get("Type") == "volume" and mount.get("Name")
        ),
        # Nunca devolver Env, labels completos, mounts privados ou logs.
        "connected": "NÃO CONFIRMADO",
    }


def inventory(root):
    report = {
        "schema_version": 1,
        "source": "read_only",
        "checkout": {},
        "services": {},
    }
    report["checkout"] = {
        "sha": read_command("git", "-C", str(root), "rev-parse", "HEAD"),
        "clean": not bool(
            read_command("git", "-C", str(root), "status", "--porcelain=v1")
        ),
    }
    if not report["checkout"]["clean"]:
        report["blocked"] = "Mudanças locais encontradas. Pare antes de atualizar."
        return report

    for service, container in SERVICES.items():
        try:
            report["services"][service] = inspect_service(container)
        except (
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
            IndexError,
            subprocess.TimeoutExpired,
        ):
            report["services"][service] = {"status": "NÃO CONFIRMADO"}

    try:
        version = read_command("docker", "exec", SERVICES["n8n"], "n8n", "--version")
        report["services"]["n8n"]["version"] = (
            version
            if re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][\w.-]+)?", version)
            else "NÃO CONFIRMADO"
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        report["services"]["n8n"]["version"] = "NÃO CONFIRMADO"

    # Apenas presença das rotas; nenhum payload, header ou segredo é consultado.
    route_probe = (
        "import json,urllib.request; "
        "data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/openapi.json',timeout=10)); "
        "print(json.dumps({p:p in data['paths'] "
        "for p in ['/health','/processar','/saude','/mensagem','/estoque']}))"
    )
    try:
        report["services"]["python-api"]["routes"] = json.loads(
            read_command(
                "docker", "exec", SERVICES["python-api"], "python", "-c", route_probe
            )
        )
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        report["services"]["python-api"]["routes"] = "NÃO CONFIRMADO"
    report["limits"] = (
        "Running/health não comprovam executor registrado, execução de workflow, "
        "sessão WhatsApp ou persistência de negócio. Nenhum workflow foi chamado."
    )
    return report


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Checkout a conferir")
    args = parser.parse_args()
    try:
        report = inventory(args.root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        print("Conferência indisponível. Nenhuma saída privada foi exibida.")
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if "blocked" in report else 0


if __name__ == "__main__":
    raise SystemExit(cli())
