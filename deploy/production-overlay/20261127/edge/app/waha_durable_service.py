"""Fail-closed Docker service around the receive-only durable WAHA prototype.

Preparation only: does not install or change AWS, Caddy, WAHA, or n8n.
"""
import json
import os
import re
import signal
import stat
import sys
import threading
import time
from pathlib import Path

from waha_durable_receiver import DurableReceiver, Rejected, make_server, private_api_post

INSTANCE = "socialmei-equipe-piloto"
REGISTRY = "/run/socialmei/private/waha-registry.json"
SPOOL = "/var/lib/socialmei/wa-edge"


def positive_integer(name, fallback, minimum, maximum):
    raw = os.environ.get(name, str(fallback))
    if not re.fullmatch(r"[0-9]{1,15}", raw):
        raise ValueError("invalid_configuration")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError("invalid_configuration")
    return value


def unique_json_pairs(pairs):
    value = {}
    for k, v in pairs:
        if k in value:
            raise ValueError("duplicate_key")
        value[k] = v
    return value


def load_binding(path=REGISTRY):
    """Read only the already provisioned root-owned, private registry."""
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        metadata = os.fstat(source.fileno())
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) not in (0o400, 0o600)
                or not 1 <= metadata.st_size <= 65536):
            raise ValueError("registry_not_private")
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ValueError("registry_invalid")
    value = json.loads(raw.decode("utf8"), object_pairs_hook=unique_json_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if (not isinstance(value, dict) or set(value) != {"version", "bindings"}
            or value["version"] != 1 or type(value["version"]) is not int
            or not isinstance(value["bindings"], list)
            or len(value["bindings"]) != 1):
        raise ValueError("registry_invalid")
    entry = value["bindings"][0]
    if (not isinstance(entry, dict) or entry.get("instance") != INSTANCE
            or entry.get("workspace_id") not in (1,60) or type(entry.get("workspace_id")) is not int):
        raise ValueError("registry_not_pilot")
    engine = entry.get("engine", "WEBJS")
    if engine not in {"WEBJS", "GOWS"}:
        raise ValueError("engine_not_authorized")
    binding = {k: entry[k] for k in (
        "workspace_id", "instance", "session", "account_id", "hmac_key"
    )}
    binding["engine"] = engine
    if entry["workspace_id"] == 60:
        if (
            type(entry.get("channel_id")) is not int
            or entry["channel_id"] <= 0
            or entry.get("revision") != 2
            or type(entry.get("ingress_after")) is not int
            or entry["ingress_after"] <= 0
            or entry.get("session") != "01"
            or engine != "GOWS"
        ):
            raise ValueError("target_binding_invalid")
        for key in ("channel_id","revision","ingress_after"):
            binding[key] = entry[key]
    return binding


class CapacityGuardedReceiver(DurableReceiver):
    def __init__(self, directory, binding, max_bytes, min_free_bytes):
        self.max_bytes = max_bytes
        self.min_free_bytes = min_free_bytes
        self.admission_lock = threading.Lock()
        super().__init__(directory, binding)

    def capacity_ok(self):
        disk = os.statvfs(self.directory)
        if disk.f_bavail * disk.f_frsize < self.min_free_bytes:
            return False
        consumed = sum(
            p.stat().st_size for p in (
                self.path, Path(str(self.path) + "-wal"), Path(str(self.path) + "-shm")
            ) if p.exists()
        )
        return consumed + 65536 < self.max_bytes

    def accept(self, body, signature, algorithm):
        # Admission control must run BEFORE the original ACK-after-commit path.
        with self.admission_lock:
            if not self.capacity_ok():
                raise OSError("spool_capacity_unavailable")
            return super().accept(body, signature, algorithm)


def run():
    if os.environ.get("WAHA_INSTANCE") != INSTANCE:
        raise ValueError("instance_not_authorized")
    if os.environ.get("WAHA_REGISTRY_FILE") != REGISTRY:
        raise ValueError("registry_path_not_authorized")
    if os.environ.get("WAHA_SPOOL_DIR") != SPOOL:
        raise ValueError("spool_path_not_authorized")
    if os.environ.get("WAHA_REQUIRE_MOUNT") != "true" or not os.path.ismount(SPOOL):
        raise ValueError("persistent_volume_required")
    max_bytes = positive_integer("WAHA_MAX_SPOOL_BYTES", 536870912, 1048576, 4294967296)
    min_free_bytes = positive_integer("WAHA_MIN_FREE_BYTES", 1073741824, 1048576, 10737418240)
    port = positive_integer("WAHA_LISTEN_PORT", 8097, 1025, 65535)

    receiver = CapacityGuardedReceiver(
        SPOOL, load_binding(), max_bytes=max_bytes, min_free_bytes=min_free_bytes
    )
    post = private_api_post(INSTANCE)
    stop = threading.Event()

    def delivery_loop():
        while not stop.is_set():
            try:
                did_work = receiver.deliver_one(post)
            except Exception:
                # Never print event body, signature, or exception arguments.
                did_work = False
                print("delivery_error retrying", flush=True)
            stop.wait(0.05 if did_work else 1.0)

    worker = threading.Thread(target=delivery_loop, name="waha-delivery", daemon=True)
    server = make_server(receiver, ("0.0.0.0", port))
    parent_handler = server.RequestHandlerClass

    class HealthHandler(parent_handler):
        def do_GET(self):
            if self.path != "/health":
                self.send_error(404)
                return
            try:
                healthy = worker.is_alive() and receiver.capacity_ok()
            except Exception:
                healthy = False
            self.send_response(204 if healthy else 503)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

    server.RequestHandlerClass = HealthHandler
    server_thread = threading.Thread(target=server.serve_forever, name="waha-http", daemon=True)

    def stop_signal(*_):
        stop.set()

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    worker.start()
    server_thread.start()
    print("waha_receive_only_started", flush=True)
    try:
        last_report = 0.0
        while not stop.wait(1.0):
            if not worker.is_alive() or not server_thread.is_alive():
                raise RuntimeError("worker_stopped")
            now = time.monotonic()
            if now - last_report >= 60:
                counts = receiver.counts()
                print("queue_counts " + " ".join(
                    f"{k}={counts.get(k, 0)}" for k in ("pending", "delivered", "quarantined")
                ), flush=True)
                last_report = now
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=15)
        server_thread.join(timeout=10)


if __name__ == "__main__":
    try:
        run()
    except (Exception, KeyboardInterrupt):
        # Do not echo secrets or paths from exception objects.
        print("waha_receive_only_unavailable", file=sys.stderr, flush=True)
        raise SystemExit(1) from None
