"""Build portable Windows payloads for a tagged Glimio release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
EDITIONS = {
    "cli": {"web": False, "diarization": False},
    "web": {"web": True, "diarization": False},
    "web-diarization": {"web": True, "diarization": True},
}


def check_version(expected: str) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    frontend = json.loads((ROOT / "src/web/frontend/package.json").read_text(encoding="utf-8"))["version"]
    lock = json.loads((ROOT / "src/web/frontend/package-lock.json").read_text(encoding="utf-8"))["version"]
    api = re.search(r'version="([^"]+)"', (ROOT / "src/web/app.py").read_text(encoding="utf-8"))
    seance = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", (ROOT / "src/seance/__init__.py").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    found = {"pyproject": project, "frontend": frontend, "frontend lock": lock,
             "FastAPI": api.group(1) if api else None, "seance": seance.group(1) if seance else None}
    mismatches = {name: value for name, value in found.items() if value != expected}
    if mismatches:
        raise SystemExit(f"Versions incohérentes : tag={expected}, valeurs={found}")
    if not re.search(rf"(?m)^## {re.escape(expected)}(?:\s|—)", changelog):
        raise SystemExit(f"CHANGELOG.md ne contient pas encore d’entrée pour {expected}.")


def run_pyinstaller(name: str, entry: Path, output: Path, work: Path, *, web: bool, diarization: bool) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", name, "--distpath", str(output), "--workpath", str(work / "build"),
        "--specpath", str(work), "--paths", str(ROOT / "src"),
        "--collect-all", "numpy", "--collect-all", "soundcard",
    ]
    if diarization:
        command.extend(["--collect-all", "sherpa_onnx"])
    if web:
        angular = ROOT / "dist" / "glimio-web-ui"
        if not (angular / "index.html").is_file():
            raise SystemExit(f"Build Angular absent : {angular / 'index.html'}")
        command.extend([
            "--collect-all", "fastapi", "--collect-all", "starlette",
            "--collect-all", "uvicorn", "--collect-all", "pydantic",
            "--collect-all", "multipart", "--add-data", f"{angular};angular",
        ])
    command.append(str(entry))
    subprocess.run(command, cwd=ROOT, check=True)
    result = output / name
    executable = result / f"{name}.exe"
    if not executable.is_file():
        raise SystemExit(f"Exécutable PyInstaller absent : {executable}")
    return result


def make_portable_zip(payload: Path, output: Path, top_level: str) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                archive.write(path, Path(top_level) / path.relative_to(payload))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--edition", choices=EDITIONS, required=True)
    parser.add_argument("--version", required=True, help="Version sans préfixe v.")
    args = parser.parse_args()
    check_version(args.version)

    edition = EDITIONS[args.edition]
    release_root = ROOT / "dist" / "release" / args.edition
    payload = release_root / "payload"
    work = ROOT / "build" / "release" / args.edition
    shutil.rmtree(release_root, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    payload.mkdir(parents=True)
    (work / "dist").mkdir(parents=True)

    cli = run_pyinstaller(
        "GlimioCLI", ROOT / "scripts/package/cli_entry.py", work / "dist", work / "cli",
        web=edition["web"], diarization=edition["diarization"],
    )
    shutil.copytree(cli, payload / "GlimioCLI")
    subprocess.run([str(cli / "GlimioCLI.exe"), "--help"], cwd=payload, check=True, stdout=subprocess.DEVNULL)
    if edition["web"]:
        web_app = run_pyinstaller(
            "GlimioWeb", ROOT / "scripts/package/web_entry.py", work / "dist", work / "web",
            web=True, diarization=edition["diarization"],
        )
        shutil.copytree(web_app, payload / "GlimioWeb")
        subprocess.run(
            [str(web_app / "GlimioWeb.exe"), "--check-bundle"],
            cwd=payload, check=True,
        )

    legal_docs = [ROOT / "LICENSE", ROOT / "NOTICE", ROOT / "docs/MODELS.md", ROOT / "docs/LICENSING.md"]
    for document in legal_docs:
        shutil.copy2(document, payload / document.name)
    readme = """Glimio — édition {edition} pour Windows x64

Installation
  Installez l’application avec le fichier Setup.exe, ou extrayez cette archive
  dans un dossier accessible en écriture pour utiliser l’édition portable.

Lancement
  CLI : GlimioCLI\\GlimioCLI.exe --help
""".format(edition=args.edition)
    if edition["web"]:
        readme += "  Web : GlimioWeb\\GlimioWeb.exe (le navigateur s’ouvre au démarrage)\n"
    readme += """
Configuration et modèles
  Les exécutables natifs et les poids de modèles ne sont pas redistribués avec
  Glimio. Configurez leurs chemins dans Paramètres et consultez MODELS.md et
  LICENSING.md. L’édition Web démarre sans Node.js et sert son interface Angular
  incluse. Les données utilisateur sont conservées dans %LOCALAPPDATA%\\Glimio\\Data.
"""
    (payload / "LISEZ-MOI.txt").write_text(readme, encoding="utf-8")
    portable = release_root / f"Glimio-{args.edition}-{args.version}-Windows-x64-portable.zip"
    make_portable_zip(payload, portable, f"Glimio-{args.edition}")


if __name__ == "__main__":
    main()
