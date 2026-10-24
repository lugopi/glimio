"""Provider catalogue, diagnostics and on-demand installation for the CLI."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .contracts import ProviderInfo
from .installer import ProviderInstallManager
from .registry import BUILTIN_PROVIDERS, default_provider_options, get_provider_info, get_provider_statuses


def add_provider_cli_parser(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = commands.add_parser(
        "providers", aliases=["provider"],
        help="Afficher l’aide des providers, diagnostiquer leurs ressources et installer leurs dépendances à la demande.",
        description=(
            "Gestion des providers indépendamment de l’interface Web. Les paquets Python sont installés à la demande ; "
            "les modèles et les exécutables externes restent configurés séparément."
        ),
    )
    parser.set_defaults(_providers_parser=parser)
    subcommands = parser.add_subparsers(dest="provider_command")

    list_parser = subcommands.add_parser("list", help="Lister les providers et leur état local.")
    list_parser.add_argument("--json", action="store_true", help="Afficher les états au format JSON.")

    info_parser = subcommands.add_parser("info", help="Afficher l’aide, les options et les liens d’un provider.")
    info_parser.add_argument("provider_id", choices=tuple(item.id for item in BUILTIN_PROVIDERS))

    install_parser = subcommands.add_parser(
        "install", help="Installer les dépendances Python d’un provider dans l’environnement adapté.",
    )
    install_parser.add_argument("provider_id", choices=tuple(item.id for item in BUILTIN_PROVIDERS))

    doctor_parser = subcommands.add_parser("doctor", help="Vérifier les providers, dépendances et ressources locales.")
    doctor_parser.add_argument("--json", action="store_true", help="Afficher les diagnostics au format JSON.")


def _statuses(project_root: Path) -> list[Any]:
    settings = SimpleNamespace(
        provider_options=default_provider_options(),
        ffmpeg="ffmpeg",
        diarization_segmentation_model="models/diarization/segmentation/segmentation.onnx",
        diarization_embedding_model="models/diarization/embedding/embedding.onnx",
    )
    return get_provider_statuses(settings, project_root=project_root)


def _status_payload(project_root: Path) -> list[dict[str, Any]]:
    return [status.to_dict() for status in _statuses(project_root)]


def _provider_label(info: ProviderInfo) -> str:
    return f"{info.id:<28} {info.task:<18}"


def _print_list(project_root: Path, *, doctor: bool = False) -> int:
    statuses = _statuses(project_root)
    print(f"{'PROVIDER':<28} {'TÂCHE':<18} {'ÉTAT':<14} DÉTAILS")
    print("-" * 104)
    has_errors = False
    for status in statuses:
        state = "PRÊT" if status.ready else "À CONFIGURER"
        details = "; ".join(status.missing) if status.missing else status.message
        if not status.ready:
            has_errors = True
        if status.provider.python_install_extra or status.provider.python_install_packages:
            details = f"{details} · dépendances Python installables à la demande"
        print(f"{status.provider.id:<28} {status.provider.task:<18} {state:<14} {details}")
    if doctor and has_errors:
        print("\nAide : exécutez `glimio providers info ID` pour les dépendances, les modèles et les liens officiels.")
    return 0


def _print_info(info: ProviderInfo, project_root: Path) -> None:
    statuses = {status.provider.id: status for status in _statuses(project_root)}
    status = statuses.get(info.id)
    print(f"{info.name} ({info.id})")
    print(f"Tâche          : {info.task}")
    print(f"Exécution      : {info.execution}")
    print(f"État           : {'Prêt' if status and status.ready else 'À configurer'}")
    print(f"Description    : {info.description}")
    if info.requires:
        print(f"Providers requis: {', '.join(info.requires)}")
    if info.python_install_extra or info.python_install_packages:
        print("Installation Python : disponible à la demande")
        if info.python_install_note:
            print(f"  {info.python_install_note}")
        if info.python_install_packages:
            print(f"  Paquets catalogue : {', '.join(info.python_install_packages)}")
        if getattr(sys, "frozen", False):
            print("  Édition empaquetée : le premier install téléchargera un runtime CPython vérifié par SHA-256.")
            print("  Redémarrez Glimio après l’installation. Les modèles ne sont pas téléchargés par cette commande.")
        elif info.python_install_extra:
            print(f"  Depuis les sources : `python -m pip install -e '.[{info.python_install_extra}]'`")
    if info.options:
        print("Options :")
        for option in info.options:
            required = " (requis)" if option.required else ""
            print(f"  -- {option.key}{required} — {option.description or option.label}")
            print(f"     défaut : {option.default!r}")
        print("  Pour le CLI, passez les valeurs par `--provider-options-file chemin/vers/providers.json`.")
    if info.setup_links:
        print("Ressources :")
        for link in info.setup_links:
            suffix = f" — {link.description}" if link.description else ""
            print(f"  [{link.kind}] {link.label}: {link.url}{suffix}")
    if status and status.missing:
        print("Manquant :")
        for item in status.missing:
            print(f"  - {item}")


def _install_provider(info: ProviderInfo, project_root: Path) -> int:
    if not (info.python_install_extra or info.python_install_packages):
        print(f"{info.id} ne déclare pas de dépendance Python installable automatiquement.", file=sys.stderr)
        if info.setup_links:
            print("Consultez les ressources avec `glimio providers info " + info.id + "`.", file=sys.stderr)
        return 2
    manager = ProviderInstallManager()
    try:
        started = manager.start(info, project_root=project_root, frozen=bool(getattr(sys, "frozen", False)))
    except (RuntimeError, ValueError) as exc:
        print(f"Impossible de démarrer l’installation : {exc}", file=sys.stderr)
        return 2
    install_id = str(started["id"])
    previous_output = ""
    previous_message = ""
    current = started
    while current and current["state"] in {"queued", "running"}:
        output = str(current.get("output") or "")
        if output.startswith(previous_output):
            delta = output[len(previous_output):]
        elif output != previous_output:
            delta = "\n[Le journal a été tronqué ; dernières lignes :]\n" + output
        else:
            delta = ""
        if delta:
            print(delta, end="" if delta.endswith("\n") else "\n", flush=True)
        previous_output = output
        message = str(current.get("message") or "")
        if message and message != previous_message:
            print(message, flush=True)
            previous_message = message
        time.sleep(0.25)
        current = manager.get(install_id)
    if current is None:
        print("L’état d’installation est introuvable.", file=sys.stderr)
        return 1
    output = str(current.get("output") or "")
    if output.startswith(previous_output):
        delta = output[len(previous_output):]
    elif output != previous_output:
        delta = "\n[Journal final :]\n" + output
    else:
        delta = ""
    if delta:
        print(delta, end="" if delta.endswith("\n") else "\n", flush=True)
    print(str(current.get("message") or "Installation terminée."))
    if current["state"] == "succeeded":
        if current.get("restart_required"):
            print("Redémarrez Glimio pour charger le provider installé.")
        print("Les modèles et éventuels exécutables système doivent encore être configurés séparément.")
        return 0
    if current.get("returncode") is not None:
        return int(current["returncode"] or 1)
    return 1


def run_provider_command(args: argparse.Namespace, *, project_root: str | Path) -> int | None:
    """Run the nested provider CLI; return ``None`` for ordinary processing commands."""
    if args.command not in {"providers", "provider"}:
        return None
    root = Path(project_root).expanduser().resolve()
    command = getattr(args, "provider_command", None)
    if command is None:
        parser = getattr(args, "_providers_parser", None)
        if parser is not None:
            parser.print_help()
        return 0
    if command == "list":
        if args.json:
            print(json.dumps(_status_payload(root), ensure_ascii=False, indent=2))
            return 0
        return _print_list(root)
    if command == "doctor":
        if args.json:
            print(json.dumps(_status_payload(root), ensure_ascii=False, indent=2))
            return 0 if all(item["ready"] for item in _status_payload(root)) else 1
        return _print_list(root, doctor=True)
    info = get_provider_info(str(args.provider_id))
    if info is None:
        print(f"Provider inconnu : {args.provider_id}", file=sys.stderr)
        return 2
    if command == "info":
        _print_info(info, root)
        return 0
    if command == "install":
        return _install_provider(info, root)
    print(f"Commande provider inconnue : {command}", file=sys.stderr)
    return 2
