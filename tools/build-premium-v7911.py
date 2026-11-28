"""Build a versioned Premium frontend without a bundled runtime config."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "deploy/premium-v7911"
ARCHIVE_SHA256 = "463daca04427c86ffa90c02eb7905d8a268de8d29d8c53e6fd369f75ad840929"
CANDIDATE_FILES = (
    "agendar.html",
    "ativar.html",
    "scripts/identity-entry.js",
    "scripts/inbox-notification-sound.js",
    "scripts/public-booking.js",
    "scripts/v22-inbox-layout.js",
    "scripts/v22-whatsapp-management.js",
    "styles/public-booking.css",
    "styles/v22-inbox-layout.css",
)


def release_files(profile):
    names = json.loads((RELEASE / "files.json").read_text(encoding="utf-8"))
    if profile == "candidate":
        names = sorted(set(names).union(CANDIDATE_FILES))
    for name in names:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or name == "config.js":
            raise ValueError(f"Invalid release path: {name}")
        override = RELEASE / "schema046" / relative
        source = override if profile == "schema046" and override.is_file() else ROOT / "frontend" / relative
        yield relative, source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--profile", choices=("schema046", "candidate"), required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "version": "7.9.11",
        "profile": args.profile,
        "source_archive_sha256": ARCHIVE_SHA256,
        "files": {},
    }
    for relative, source in release_files(args.profile):
        target = args.output / "frontend" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest["files"][relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Premium 7.9.11 ({args.profile}): {len(manifest['files'])} files")


if __name__ == "__main__":
    main()
