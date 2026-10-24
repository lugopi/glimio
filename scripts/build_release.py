"""Build portable Glimio CLI or Web release payloads on the current OS.

The CLI-only edition contains only the CLI entry point. The Web edition contains
both the CLI and the Web application. The base package stays light: optional Python
provider runtimes and wheels are installed on demand into user data, while models
and separately distributed native executables remain outside the app bundle.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 remains supported for source installs and CI.
    import tomli as tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EDITIONS = {
    "cli": {"web": False},
    "web": {"web": True},
}
PLATFORMS = {"windows", "linux"}


def project_version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def check_version(expected: str) -> None:
    project = project_version()
    frontend = json.loads((ROOT / "src/web/frontend/package.json").read_text(encoding="utf-8"))["version"]
    lock = json.loads((ROOT / "src/web/frontend/package-lock.json").read_text(encoding="utf-8"))["version"]
    api = re.search(r'version="([^"]+)"', (ROOT / "src/web/app.py").read_text(encoding="utf-8"))
    seance = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", (ROOT / "src/seance/__init__.py").read_text(encoding="utf-8"))
    found = {
        "pyproject": project,
        "frontend": frontend,
        "frontend lock": lock,
        "FastAPI": api.group(1) if api else None,
        "seance": seance.group(1) if seance else None,
    }
    mismatches = {name: value for name, value in found.items() if value != expected}
    if mismatches:
        raise SystemExit(f"Version mismatch: tag={expected}, values={found}")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"(?m)^## {re.escape(expected)}(?:\s|—)", changelog):
        raise SystemExit(f"CHANGELOG.md has no heading for version {expected}.")


def executable_path(bundle_dir: Path, name: str) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return bundle_dir / f"{name}{suffix}"


def run_pyinstaller(
    name: str,
    entry: Path,
    output: Path,
    work: Path,
    *,
    include_web: bool,
    angular_dist: Path | None = None,
) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", name, "--distpath", str(output), "--workpath", str(work / "build"),
        "--specpath", str(work), "--paths", str(ROOT / "src"),
        "--collect-all", "numpy",
    ]
    # Audio capture via soundcard is installed on Windows only; don't ask
    # PyInstaller to collect a package which isn't part of the Linux runtime.
    if importlib.util.find_spec("soundcard") is not None:
        command.extend(["--collect-all", "soundcard"])

    if include_web:
        if angular_dist is None or not (angular_dist / "index.html").is_file():
            expected = angular_dist / "index.html" if angular_dist else "dist/glimio-web-ui/index.html"
            raise SystemExit(f"Angular production build is missing: {expected}")
        command.extend([
            "--collect-all", "fastapi", "--collect-all", "starlette",
            "--collect-all", "uvicorn", "--collect-all", "pydantic",
            "--collect-all", "multipart",
            "--add-data", f"{angular_dist}{os.pathsep}angular",
        ])
    command.append(str(entry))
    subprocess.run(command, cwd=ROOT, check=True)

    result = output / name
    executable = executable_path(result, name)
    if not executable.is_file():
        raise SystemExit(f"PyInstaller executable missing: {executable}")
    return result


def make_portable_zip(payload: Path, output: Path, top_level: str) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=7) as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                archive.write(path, Path(top_level) / path.relative_to(payload))


def make_portable_tar_gz(payload: Path, output: Path, top_level: str) -> None:
    with tarfile.open(output, "w:gz", compresslevel=6) as archive:
        for path in sorted(payload.rglob("*")):
            archive.add(path, arcname=str(Path(top_level) / path.relative_to(payload)), recursive=False)


def write_readme(payload: Path, edition: str, platform_name: str) -> None:
    if platform_name == "windows":
        cli_command = r"GlimioCLI\GlimioCLI.exe"
        web_command = r"GlimioWeb\GlimioWeb.exe"
        data_path = r"%LOCALAPPDATA%\Glimio\Data"
        extraction = "Utilisez Setup.exe pour installer l’application, ou extrayez cette archive dans un dossier accessible en écriture."
    else:
        cli_command = "./GlimioCLI/GlimioCLI"
        web_command = "./GlimioWeb/GlimioWeb"
        data_path = "${XDG_DATA_HOME:-$HOME/.local/share}/Glimio/Data"
        extraction = "Extrayez l’archive dans un dossier de votre choix. Les exécutables Linux x86_64 sont fournis dans les sous-dossiers ci-dessous."

    platform_label = "Windows x64" if platform_name == "windows" else "Linux x86_64"
    lines = [
        f"Glimio {edition} — {platform_label}",
        "",
        "Installation",
        f"  {extraction}",
        "",
        "Lancement",
        f"  CLI : {cli_command} --help",
    ]
    if edition == "web":
        lines.append(f"  Web : {web_command} (ouvre l’interface dans le navigateur)")
    lines.extend([
        "",
        *( ["Compatibilité Linux", "  Paquet construit sur Ubuntu 22.04 x86_64 ; glibc 2.35 ou plus récent est requis.", ""] if platform_name == "linux" else [] ),
        "Providers Python optionnels",
        "  Le paquet de base reste léger. Listez les providers avec :",
        f"  CLI : {cli_command} providers list",
        f"  Aide : {cli_command} providers --help",
        f"  Détails/options : {cli_command} providers info sherpa-onnx",
        "  Installez un provider Python à la demande, par exemple :",
        f"  {cli_command} providers install sherpa-onnx",
        "  Le premier provider téléchargera un runtime Python vérifié par SHA-256 ;",
        "  ses dépendances peuvent être volumineuses. Utilisez `providers info ID`",
        "  pour consulter l’aide propre à chaque provider. Les modèles ONNX de",
        "  diarisation, les modèles SpeechBrain et les exécutables Whisper/llama.cpp/",
        "  FFmpeg ne sont pas inclus. Consultez MODELS.md et LICENSING.md.",
        "",
        "Données utilisateur",
        f"  {data_path}",
        "",
        "Web",
        "  L’interface Angular de production est incluse : Node.js n’est pas requis.",
    ])
    (payload / "LISEZ-MOI.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_release(edition_name: str, platform_name: str, version: str) -> Path:
    current_platform = "windows" if os.name == "nt" else "linux" if sys.platform.startswith("linux") else None
    if platform_name not in PLATFORMS:
        raise SystemExit(f"Unsupported platform: {platform_name}")
    if current_platform != platform_name:
        raise SystemExit(f"Build target mismatch: requested {platform_name}, current runner is {current_platform or sys.platform}.")

    edition = EDITIONS[edition_name]
    release_root = ROOT / "dist" / "release" / edition_name
    payload = release_root / "payload"
    work = ROOT / "build" / "release" / edition_name
    shutil.rmtree(release_root, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    payload.mkdir(parents=True)
    (work / "dist").mkdir(parents=True)

    angular_dist = ROOT / "dist" / "glimio-web-ui" if edition["web"] else None
    cli = run_pyinstaller(
        "GlimioCLI", ROOT / "scripts/package/cli_entry.py", work / "dist", work / "cli",
        include_web=False,
    )
    shutil.copytree(cli, payload / "GlimioCLI")
    cli_executable = executable_path(cli, "GlimioCLI")
    cli_smoke_commands = (
        ["--help"], ["import", "--help"], ["providers", "--help"],
        ["providers", "list"], ["providers", "list", "--json"],
        ["providers", "info", "sherpa-onnx"], ["providers", "info", "speechbrain-ecapa"],
        ["providers", "install", "--help"], ["sessions", "--help"],
        ["sessions", "settings", "--help"], ["sessions", "audio", "--help"],
        ["artifacts", "--help"], ["preferences", "--help"], ["jobs", "--help"],
        ["devices", "--help"], ["search", "--help"],
    )
    for cli_args in cli_smoke_commands:
        subprocess.run([str(cli_executable), *cli_args], cwd=payload, check=True, stdout=subprocess.DEVNULL)

    if edition["web"]:
        web_app = run_pyinstaller(
            "GlimioWeb", ROOT / "scripts/package/web_entry.py", work / "dist", work / "web",
            include_web=True, angular_dist=angular_dist,
        )
        shutil.copytree(web_app, payload / "GlimioWeb")
        subprocess.run([str(executable_path(web_app, "GlimioWeb")), "--check-bundle"], cwd=payload, check=True)

    for document in (
        ROOT / "LICENSE", ROOT / "NOTICE", ROOT / "docs/MODELS.md", ROOT / "docs/LICENSING.md",
    ):
        shutil.copy2(document, payload / document.name)
    write_readme(payload, edition_name, platform_name)

    if platform_name == "windows":
        output = release_root / f"Glimio-{edition_name}-{version}-Windows-x64-portable.zip"
        make_portable_zip(payload, output, f"Glimio-{edition_name}")
    else:
        output = release_root / f"Glimio-{edition_name}-{version}-Linux-x86_64.tar.gz"
        make_portable_tar_gz(payload, output, f"Glimio-{edition_name}")
    print(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a portable Glimio CLI or Web release for Windows or Linux.")
    parser.add_argument("--edition", choices=EDITIONS)
    parser.add_argument("--platform", choices=sorted(PLATFORMS))
    parser.add_argument("--version", help="Version without the v prefix")
    parser.add_argument(
        "--check-version", action="store_true",
        help="Validate all project version declarations against --version (or pyproject.toml if omitted)",
    )
    args = parser.parse_args()
    if args.check_version:
        expected = args.version or project_version()
        check_version(expected)
        print(f"All Glimio version declarations match {expected}.")
        return
    if not args.edition or not args.platform or not args.version:
        parser.error("--edition, --platform and --version are required for a release build")
    check_version(args.version)
    build_release(args.edition, args.platform, args.version)


if __name__ == "__main__":
    main()
