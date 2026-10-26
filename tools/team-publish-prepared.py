"""Publish a verified prepared team release; defaults to inspection, never generic deploy."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path("/home/ubuntu/socialmei-team")
BACKUPS = Path("/home/ubuntu/socialmei-backups")
ORIGIN = "https://socialmei-ia.54-94-213-7.sslip.io"
SERVICES = ("team-api", "team-gateway")
OFF = ("SOCIALMEI_INSTAGRAM_RUNTIME_MODE", "SOCIALMEI_INSTAGRAM_OAUTH_MODE",
       "SOCIALMEI_INSTAGRAM_INGRESS_MODE", "SOCIALMEI_INSTAGRAM_DIRECT_MODE",
       "SOCIALMEI_WAHA_INGRESS_MODE", "SOCIALMEI_RECOVERY_MODE")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def allowed_change(before, after, service, sha):
    expected = copy.deepcopy(before)
    expected["services"][service]["image"] = f"socialmei-v22/{service}:{sha}"
    if service == "team-api":
        expected["services"][service].setdefault("environment", {})["SOCIALMEI_RELEASE_SHA"] = sha
    return after == expected


def runtime_shape_matches(model, container, service):
    config = model["services"][service]
    networks = {model["networks"][key]["name"] for key in config.get("networks", {})}
    if networks != set(container["NetworkSettings"]["Networks"]):
        return False
    expected = {(v["type"], v["source"], v["target"], not v.get("read_only", False)) for v in config.get("volumes", [])}
    actual = {(v["Type"], v.get("Name") if v["Type"] == "volume" else v["Source"], v["Destination"], v["RW"]) for v in container["Mounts"]}
    return expected == actual and not config.get("ports") and not container["HostConfig"].get("PortBindings")


def baseline_matches(meta, live, accept_recreated=False):
    return live["Image"] == meta["image_id"] and (live["Id"] == meta["container_id"] or accept_recreated)


def up_command(args, service):
    require(service in SERVICES, "Serviço fora do escopo.")
    return args + ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", service]


class Publisher:
    def __init__(self, folder, sha, rollback_backup, accept_recreated=False):
        self.folder, self.sha, self.rollback_backup = folder, sha, rollback_backup
        self.accept_recreated = accept_recreated
        self.commands = json.loads((folder / "compose-commands.json").read_text())
        self.log = folder / "publication-private.log"

    def run(self, args, **kwargs):
        result = subprocess.run(args, cwd=ROOT, capture_output=True, **kwargs)
        with self.log.open("ab") as stream:
            stream.write(result.stdout or b"")
            stream.write(result.stderr or b"")
        require(result.returncode == 0, "Comando falhou; detalhes no log privado. Não compartilhe o log.")
        return result.stdout

    def inspect(self, name):
        return json.loads(self.run(["docker", "inspect", name]))[0]

    def compose(self, service, mode):
        return self.commands[service][mode]

    def preflight(self):
        require(not self.run(["git", "status", "--porcelain"]).strip(), "Checkout possui alterações locais.")
        require(set(self.commands) == set(SERVICES), "Manifesto fora do escopo.")
        receipt = self.rollback_backup / "SHA256SUMS"
        found = set()
        for line in receipt.read_text().splitlines():
            checksum, name = line.split(maxsplit=1)
            name = name.lstrip(" *")
            require(name in {"images.tar.gz", "runtime-config.tar.gz", "containers.json", "image-ids.txt"}, "Manifesto de backup inválido.")
            require(digest(self.rollback_backup / name) == checksum, "Backup de rollback divergente.")
            found.add(name)
        require(len(found) == 4, "Backup de rollback incompleto.")
        recreated = []
        for service in SERVICES:
            meta = self.commands[service]
            live = self.inspect("socialmei-team-" + service + "-1")
            require(baseline_matches(meta, live, self.accept_recreated), "Container mudou após preparação; revalide o rollback antes de aceitar nova identidade.")
            if live["Id"] != meta["container_id"]:
                recreated.append({"service": service, "previous_id": meta["container_id"], "revalidated_id": live["Id"]})
            for mode, suffix in (("previous", "before"), ("candidate", "candidate")):
                model = json.loads(self.run(self.compose(service, mode) + ["config", "--format", "json"]))
                require(model == json.loads((self.folder / f"{service}.{suffix}.json").read_text()), "Configuração mudou após preparação.")
            before = json.loads((self.folder / f"{service}.before.json").read_text())
            after = json.loads((self.folder / f"{service}.candidate.json").read_text())
            require(runtime_shape_matches(before, live, service), "Redes, mounts ou portas diferem da instalação.")
            require(allowed_change(before, after, service, self.sha), "Mudança de Compose fora do escopo.")
            old_image = before["services"][service]["image"]
            require(self.inspect_image(old_image)["Id"] == meta["image_id"], "Imagem de rollback não corresponde à instalação.")
            image = self.inspect_image(after["services"][service]["image"])
            require(image["Config"]["Labels"].get("org.opencontainers.image.revision") == self.sha, "Imagem candidata com SHA divergente.")
            env = dict(item.split("=", 1) for item in live["Config"]["Env"])
            require(all(env.get(k) == str(v) for k, v in before["services"][service].get("environment", {}).items()), "Ambiente instalado divergiu.")
            if service == "team-api":
                require(env.get("SOCIALMEI_AUTH_ENABLED", "").lower() in {"true", "1", "yes", "on"}, "Autenticação não confirmada.")
                require(all(env.get(key, "disabled") in {"", "disabled"} for key in OFF), "Integração externa ou recuperação habilitada: revisão necessária.")
        source = self.folder / "source"
        files = sorted((source / "database/migrations").glob("*.sql"))
        require(len(files) == 26 and [p.name[:3] for p in files] == [f"{i:03}" for i in range(1, 27)], "Cadeia de migrations divergente.")
        for file in files + [source / "tools/team_migrate.py"]:
            relative = file.relative_to(source).as_posix()
            require(hashlib.sha256(self.run(["git", "show", f"{self.sha}:{relative}"])).hexdigest() == digest(file), "Fonte de migration alterada.")
        with urlopen(ORIGIN + "/frontend/config.js", timeout=20) as response:
            public_config = response.read().decode()
        require(re.search(r"auth[\"\']?\s*:\s*\{[^{}]*?mode[\"\']?\s*:\s*[\"\']remote[\"\']", public_config), "Configuração pública de autenticação remota não confirmada.")
        current_hash = self.run(["docker", "exec", "socialmei-team-team-gateway-1", "sha256sum", "/etc/caddy/Caddyfile"]).split()[0]
        candidate_hash = self.run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "sha256sum", f"socialmei-v22/team-gateway:{self.sha}", "/etc/caddy/Caddyfile"]).split()[0]
        require(current_hash == candidate_hash, "Caddy candidato difere do gateway instalado.")
        if recreated:
            (self.folder / "revalidated-baseline.json").write_text(json.dumps(recreated, indent=2))
            print("Containers recriados revalidados com as mesmas imagens/configurações de rollback.", flush=True)
        print("PREFLIGHT CONFERIDO.", flush=True)

    def inspect_image(self, name):
        return json.loads(self.run(["docker", "image", "inspect", name]))[0]

    def wait(self, service):
        for _ in range(60):
            state = self.inspect("socialmei-team-" + service + "-1")["State"]
            if state["Running"] and ("Health" not in state or state["Health"]["Status"] == "healthy"):
                if service == "team-gateway":
                    try:
                        self.run(["docker", "exec", "socialmei-team-team-gateway-1", "wget", "-q", "-T", "2", "-O", "/dev/null", "http://127.0.0.1:80/"])
                    except RuntimeError:
                        time.sleep(2)
                        continue
                return
            time.sleep(2)
        raise RuntimeError("Serviço não ficou saudável no prazo.")

    def migrate(self):
        print("Executando backup atualizado e migrations transacionais.", flush=True)
        output = self.run([sys.executable, "tools/team-maintenance.py", "backup"]).decode()
        match = re.search(r"Backup da equipe concluído e índice conferido: ([^\r\n]+)", output)
        require(match, "Recibo de backup atualizado ausente.")
        backup = Path(match[1]).resolve()
        require(backup.parent == BACKUPS, "Backup fora do diretório autorizado.")
        receipt = json.loads((backup / "concluido.json").read_text())
        require({"equipe.dump", "configuracao.tar.gz", "conteudo.txt"} <= set(receipt.get("sha256", {})), "Backup incompleto ou sem checksums.")
        for name, checksum in receipt["sha256"].items():
            require(Path(name).name == name and digest(backup / name) == checksum, "Backup atualizado divergente.")
        (self.folder / "fresh-backup-path.txt").write_text(str(backup) + "\n")
        api = self.inspect("socialmei-team-team-api-1")
        database = self.inspect("socialmei-team-team-postgres-1")
        networks = set(api["NetworkSettings"]["Networks"]) & set(database["NetworkSettings"]["Networks"])
        require(len(networks) == 1, "Rede do banco ambígua.")
        env = api["Config"]["Env"]
        require(all("\n" not in item and "\r" not in item for item in env), "Ambiente incompatível com env-file.")
        env_file = self.folder / "migration-private.env"
        env_file.write_text("\n".join(env) + "\n")
        source = self.folder / "source"
        try:
            self.run(["docker", "run", "--rm", "--network", next(iter(networks)),
                      "--env-file", str(env_file), "--env", "PGOPTIONS=-c lock_timeout=10s -c statement_timeout=120s",
                      "--mount", f"type=bind,src={source / 'tools/team_migrate.py'},dst=/maintenance/team_migrate.py,readonly",
                      "--mount", f"type=bind,src={source / 'database/migrations'},dst=/migrations,readonly",
                      "--entrypoint", "python", f"socialmei-v22/team-api:{self.sha}", "/maintenance/team_migrate.py"])
        finally:
            env_file.unlink(missing_ok=True)

    def https(self, path, expected):
        for attempt in range(12):
            status, content = None, b""
            try:
                with urlopen(ORIGIN + path, timeout=5) as response:
                    status, content = response.status, response.read()
            except HTTPError as error:
                status = error.code
            except URLError as error:
                require(not isinstance(error.reason, ssl.SSLError), "Falha de certificado/TLS; publicação interrompida.")
            except TimeoutError:
                pass
            if status == expected:
                return content
            if status not in (None, 502, 503, 504) or attempt == 11:
                raise RuntimeError(f"HTTPS divergente em {path}: {status}.")
            time.sleep(2)

    def smoke(self):
        for path, expected in (("/", 200), ("/frontend/entrada.html", 200), ("/api/v1/clientes", 401), ("/health/db", 404)):
            self.https(path, expected)
        for path in ("socialmei-app.html", "scripts/v22-bootstrap.js", "scripts/v22-backend.js", "scripts/v22-frame.js", "scripts/entrada.js", "styles/entrada.css", "telas/oportunidades.html", "telas/divulgacao.html"):
            value = hashlib.sha256(self.https("/frontend/" + path, 200)).hexdigest()
            require(value == digest(self.folder / "source/frontend" / path), "Arquivo publicado diverge da candidata.")

    def switch(self, mode, services=SERVICES):
        for service in services:
            if mode == "previous":
                model = json.loads(self.run(self.compose(service, mode) + ["config", "--format", "json"]))
                before = json.loads((self.folder / f"{service}.before.json").read_text())
                require(model == before, "Configuração de rollback foi alterada; intervenção necessária.")
                require(self.inspect_image(before["services"][service]["image"])["Id"] == self.commands[service]["image_id"], "Imagem de rollback divergente.")
            self.run(up_command(self.compose(service, mode), service))
            self.wait(service)

    def publish(self):
        self.preflight()
        self.migrate()
        attempted = []
        try:
            for service in SERVICES:
                attempted.append(service)
                print("Atualizando somente " + service, flush=True)
                self.switch("candidate", (service,))
            self.smoke()
        except Exception:
            print("Falha crítica; restaurando imagens/configuração anteriores dos serviços afetados.", flush=True)
            self.switch("previous", tuple(attempted))
            print("ROLLBACK DOS SERVICOS CONCLUIDO; banco preservado com migrations aditivas.", flush=True)
            raise
        (self.folder / "installed.json").write_text(json.dumps({"sha": self.sha, "services": list(SERVICES), "https": ORIGIN, "browser_login": "pending_manual_validation"}, indent=2))
        print("API/GATEWAY PUBLICADOS E HTTPS/ARQUIVOS CONFERIDOS. SHA: " + self.sha, flush=True)
        print("Validar login e interface no navegador. Demais serviços não foram comandados.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--rollback-backup", required=True, type=Path)
    parser.add_argument("--accept-recreated-baseline", action="store_true", help="Após rollback confirmado: revalidar IDs novos somente com mesmas imagens/configurações.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9a-f]{40}", args.sha), "SHA completo obrigatório.")
    require(Path.cwd().resolve() == ROOT, "Execute no checkout team autorizado.")
    require(args.folder.resolve().parent == BACKUPS and args.rollback_backup.resolve().parent == BACKUPS, "Pasta fora dos backups team.")
    os.umask(0o077)
    with (BACKUPS / ".team-publication.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = Publisher(args.folder.resolve(), args.sha, args.rollback_backup.resolve(), args.accept_recreated_baseline)
        if args.rollback:
            release.switch("previous")
            print("Imagens anteriores restauradas; migrations aditivas e dados preservados.")
        elif args.apply:
            release.publish()
        else:
            release.preflight()
            print("Somente inspeção; use --apply para publicação autorizada.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("INTERROMPIDO: " + str(error), file=sys.stderr)
        sys.exit(1)
