"""CLI adapters for library, artifacts, preferences, jobs and cross-session search.

All business operations are delegated to ``seance.core``. This module must stay
usable without importing the FastAPI/Angular application.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .core import sessions as session_core
SessionServiceError = session_core.SessionServiceError
from .core.job_store import JobStore
from .core.preferences_store import PreferencesStore
from .core.sqlite_db import SQLiteDatabase, database_path
from .core.library import retrieve_passages
from .core.search_synthesis import generate_search_synthesis
from .project_paths import DEFAULT_LLAMA_COMPLETION_PATH, resolve_session_root
from .providers import DEFAULT_TEXT_PROVIDER, get_provider_info

ACTIVE_STATES = {"queued", "running", "stopping"}


def add_application_cli_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register application-level commands that mirror Web library operations."""
    sessions = commands.add_parser("sessions", aliases=["session"], help="Gérer la bibliothèque locale de séances.")
    sessions.set_defaults(_sessions_parser=sessions)
    scommands = sessions.add_subparsers(dest="sessions_command")
    listing = scommands.add_parser("list", help="Lister et filtrer les séances.")
    listing.add_argument("--directory", help="Racine des séances (sinon préférence Glimio).")
    listing.add_argument("--query", "-q", default="", help="Rechercher dans les titres, résumés et transcriptions.")
    listing.add_argument("--filter", choices=("all", "audio", "transcript", "summary"), default="all")
    listing.add_argument("--limit", type=int, default=25)
    listing.add_argument("--offset", type=int, default=0)
    listing.add_argument("--json", action="store_true")

    show = scommands.add_parser("show", help="Afficher les métadonnées et fichiers d’une séance.")
    show.add_argument("session_id")
    show.add_argument("--directory")
    show.add_argument("--json", action="store_true")

    rename = scommands.add_parser("rename", help="Renommer une séance sans modifier son identifiant.")
    rename.add_argument("session_id")
    rename.add_argument("title")
    rename.add_argument("--directory")

    delete = scommands.add_parser("delete", help="Supprimer une séance et ses fichiers.")
    delete.add_argument("session_id")
    delete.add_argument("--directory")
    delete.add_argument("--yes", "-y", action="store_true", help="Confirmer la suppression sans invite interactive.")

    settings = scommands.add_parser("settings", help="Lire ou modifier les options de traitement d’une séance.")
    settings.set_defaults(_session_settings_parser=settings)
    settings_commands = settings.add_subparsers(dest="session_settings_command")
    settings_show = settings_commands.add_parser("show", help="Afficher les options enregistrées.")
    settings_show.add_argument("session_id")
    settings_show.add_argument("--directory")
    settings_save = settings_commands.add_parser("save", help="Enregistrer les options depuis un fichier JSON.")
    settings_save.add_argument("session_id")
    settings_save.add_argument("--file", required=True, help="Fichier JSON contenant un objet d’options.")
    settings_save.add_argument("--directory")

    audio = scommands.add_parser("audio", help="Gérer les pistes audio d’une séance.")
    audio.set_defaults(_session_audio_parser=audio)
    audio_commands = audio.add_subparsers(dest="session_audio_command")
    audio_list = audio_commands.add_parser("list", help="Lister les pistes et leur état d’activation.")
    audio_list.add_argument("session_id")
    audio_list.add_argument("--directory")
    audio_list.add_argument("--json", action="store_true")
    for action in ("enable", "disable", "delete"):
        p = audio_commands.add_parser(action, help=f"{'Réactiver' if action == 'enable' else 'Désactiver' if action == 'disable' else 'Supprimer'} une piste audio.")
        p.add_argument("session_id")
        p.add_argument("filename")
        p.add_argument("--directory")
        if action == "delete":
            p.add_argument("--yes", "-y", action="store_true")

    artifacts = commands.add_parser("artifacts", help="Lire ou enregistrer les documents d’une séance.")
    artifacts.set_defaults(_artifacts_parser=artifacts)
    art_commands = artifacts.add_subparsers(dest="artifacts_command")
    art_show = art_commands.add_parser("show", help="Afficher la transcription ou le résumé.")
    art_show.add_argument("session_id")
    art_show.add_argument("kind", choices=("summary", "transcript"))
    art_show.add_argument("--directory")
    art_show.add_argument("--output", "-o", help="Écrire le document dans ce fichier plutôt que stdout.")
    art_save = art_commands.add_parser("save-summary", help="Enregistrer une édition du résumé existant.")
    art_save.add_argument("session_id")
    art_save.add_argument("--file", required=True, help="Fichier Markdown source.")
    art_save.add_argument("--revision", help="Révision mtime:size obtenue avec artifacts show (JSON).")
    art_save.add_argument("--force", action="store_true", help="Ignorer la protection contre une révision obsolète.")
    art_save.add_argument("--directory")

    preferences = commands.add_parser("preferences", aliases=["prefs"], help="Lire ou modifier les préférences partagées CLI/Web.")
    pcommands = preferences.add_subparsers(dest="preferences_command")
    preferences.set_defaults(_preferences_parser=preferences)
    pshow = pcommands.add_parser("show", help="Afficher les préférences.")
    pshow.add_argument("--json", action="store_true")
    psave = pcommands.add_parser("save", help="Enregistrer des préférences depuis un fichier JSON.")
    psave.add_argument("--file", required=True, help="Objet JSON complet {settings, ui}, ou objet settings.")

    jobs = commands.add_parser("jobs", help="Consulter l’historique des traitements.")
    jobs.set_defaults(_jobs_parser=jobs)
    jcommands = jobs.add_subparsers(dest="jobs_command")
    jlist = jcommands.add_parser("list", help="Lister les activités récentes.")
    jlist.add_argument("--limit", type=int, default=50)
    jlist.add_argument("--json", action="store_true")
    jshow = jcommands.add_parser("show", help="Afficher une activité par identifiant.")
    jshow.add_argument("job_id")
    jshow.add_argument("--json", action="store_true")
    jdelete = jcommands.add_parser("delete", help="Supprimer une entrée d’historique terminée.")
    jdelete.add_argument("job_id")
    jdelete.add_argument("--web-url", default=None, help="URL du serveur Web si celui-ci est actif.")
    jclear = jcommands.add_parser("clear", help="Vider l’historique terminé sans supprimer les jobs actifs.")
    jclear.add_argument("--web-url", default=None, help="URL du serveur Web si celui-ci est actif.")
    jcancel = jcommands.add_parser("cancel", help="Demander l’annulation d’un job du serveur Web en cours.")
    jcancel.add_argument("job_id")
    jcancel.add_argument("--web-url", default=None, help="URL du serveur Web (défaut: GLIMIO_WEB_URL ou port 8765).")

    devices = commands.add_parser("devices", help="Lister les périphériques audio du système.")
    devices.add_argument("--json", action="store_true")

    search = commands.add_parser("search", help="Rechercher dans les transcriptions et résumés des séances.")
    search.set_defaults(_search_parser=search)
    search.add_argument("query", nargs="?", help="Question ou termes à rechercher.")
    search.add_argument("--top-k", type=int, default=8, choices=range(1, 21), metavar="1..20")
    search.add_argument("--session", action="append", dest="session_ids", help="Limiter à une séance (répéter l’option pour plusieurs).")
    search.add_argument("--json", action="store_true", help="Afficher le résultat au format JSON.")
    search.add_argument("--synthesize-results", action="store_true", help="Générer une synthèse IA après la recherche.")
    search.add_argument("--text-provider", default=None, help="Provider de génération (défaut: préférence Glimio).")
    search.add_argument("--binary", default=None, help="Binaire du provider de génération.")
    search.add_argument("--model", default=None, help="Modèle du provider de génération.")
    search.add_argument("--context", type=int, default=None, help="Taille du contexte pour la synthèse IA.")
    search.add_argument("--output", "-o", help="Enregistrer la synthèse dans un fichier Markdown.")
    search.add_argument("--directory", help="Racine des séances.")
    search.add_argument("--list", action="store_true", dest="list_searches", help="Lister les recherches sauvegardées.")
    search.add_argument("--show", metavar="SEARCH_ID", help="Afficher une recherche sauvegardée.")
    search.add_argument("--synthesize", metavar="SEARCH_ID", help="Régénérer la synthèse d’une recherche sauvegardée.")
    search.add_argument("--excerpts", help="Numéros de sources à conserver, ex. 1,3,4 (avec --synthesize).")


def _stores(project_root: Path) -> tuple[JobStore, PreferencesStore]:
    db = SQLiteDatabase(database_path(project_root))
    db.initialize()
    return JobStore(db), PreferencesStore(db)


def _preferences(project_root: Path) -> dict[str, Any]:
    _, store = _stores(project_root)
    value = store.get()
    return value if isinstance(value, dict) else {"settings": {}, "ui": {}}


def _session_root(project_root: Path, args: argparse.Namespace) -> Path:
    override = getattr(args, "directory", None)
    if override:
        value = Path(override).expanduser()
        return (value if value.is_absolute() else project_root / value).resolve()
    saved_root = (_preferences(project_root).get("ui") or {}).get("session_root")
    return resolve_session_root(project_root, saved_root or None)


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _load_json_object(file_path: str) -> dict[str, Any]:
    path = Path(file_path).expanduser().resolve()
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionServiceError(f"Impossible de lire {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SessionServiceError("Le fichier doit contenir un objet JSON.")
    return value


def _search_history_dir(project_root: Path) -> Path:
    path = database_path(project_root).parent / "searches"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _search_history_path(project_root: Path, search_id: str) -> Path:
    if not search_id or Path(search_id).name != search_id or not search_id.replace("-", "").isalnum():
        raise SessionServiceError("Identifiant de recherche invalide.")
    path = _search_history_dir(project_root) / f"{search_id}.json"
    if not path.is_file():
        raise SessionServiceError(f"Recherche introuvable : {search_id}")
    return path


def _read_search(project_root: Path, search_id: str) -> dict[str, Any]:
    path = _search_history_path(project_root, search_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SessionServiceError(f"Recherche illisible : {search_id}") from exc
    if not isinstance(value, dict):
        raise SessionServiceError(f"Recherche illisible : {search_id}")
    return value


def _save_search(project_root: Path, value: dict[str, Any]) -> str:
    search_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    value["id"] = search_id
    value["created_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = _search_history_dir(project_root) / f"{search_id}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return search_id


def _search_summary_args(project_root: Path, args: argparse.Namespace) -> tuple[str, Path, Path, SimpleNamespace]:
    preferences = _preferences(project_root)
    settings = dict(preferences.get("settings") or {})
    provider_id = str(args.text_provider or settings.get("text_provider") or DEFAULT_TEXT_PROVIDER)
    provider_options = dict(settings.get("provider_options") or {})
    specific_options = dict(provider_options.get(provider_id) or {})
    binary_value = args.binary or specific_options.get("llama_completion") or settings.get("llama_completion") or DEFAULT_LLAMA_COMPLETION_PATH
    model_value = args.model or specific_options.get("gguf") or settings.get("gguf") or "models/llm/model.gguf"
    binary = Path(str(binary_value)).expanduser()
    model = Path(str(model_value)).expanduser()
    if not binary.is_absolute():
        binary = project_root / binary
    if not model.is_absolute():
        model = project_root / model
    context = args.context or settings.get("context") or 16384
    if int(context) < 2048 or int(context) > 131072:
        raise SessionServiceError("--context doit être compris entre 2048 et 131072.")
    return provider_id, binary, model, SimpleNamespace(context=int(context), provider_options=provider_options)


def _synthesize(project_root: Path, query: str, passages: list[dict[str, Any]], args: argparse.Namespace) -> str:
    if not passages:
        raise SessionServiceError("Aucun extrait disponible pour la synthèse.")
    provider_id, binary, model, settings = _search_summary_args(project_root, args)
    info = get_provider_info(provider_id)
    if info is None or info.task != "generation":
        # Some generation providers are exposed by factories but don't share this task label;
        # the provider constructor validates exact support and reports the actionable error.
        if provider_id not in {"llama.cpp"} and not (info and "text-generation" in info.capabilities):
            raise SessionServiceError(f"Provider de génération inconnu ou incompatible : {provider_id}")
    answer, _ = generate_search_synthesis(
        query, passages, settings, binary, model,
        provider_id=provider_id, working_directory=project_root,
        on_progress=lambda message: print(f"[search] {message}", file=sys.stderr, flush=True),
    )
    return answer


def _run_sessions(args: argparse.Namespace, project_root: Path) -> int:
    command = getattr(args, "sessions_command", None)
    root = _session_root(project_root, args)
    if command is None:
        args._sessions_parser.print_help()
        return 0
    if command == "list":
        items, count = session_core.list_sessions(root, query=args.query, filter_by=args.filter, limit=args.limit, offset=args.offset)
        if args.json:
            _print_json({"items": items, "count": count, "root": str(root)})
        else:
            print(f"Séances : {count} · racine : {root}")
            for item in items:
                flags = ", ".join(name for name, available in (("audio", item.get("audio")), ("transcription", item.get("transcript")), ("résumé", item.get("summary"))) if available) or "vide"
                print(f"{item['id']}\t{item['title']}\t[{flags}]")
        return 0
    if command == "show":
        value = session_core.get_session(root, args.session_id)
        _print_json(value) if args.json else _print_session(value)
        return 0
    if command == "rename":
        value = session_core.rename_session(project_root, root, args.session_id, args.title)
        print(f"Séance renommée : {value['title']} ({value['id']})")
        return 0
    if command == "delete":
        if not args.yes and not _confirm(f"Supprimer définitivement la séance {args.session_id} ? [y/N] "):
            print("Suppression annulée.")
            return 0
        session_core.delete_session(project_root, root, args.session_id)
        print(f"Séance supprimée : {args.session_id}")
        return 0
    if command == "settings":
        if args.session_settings_command is None:
            args._session_settings_parser.print_help()
            return 0
        if args.session_settings_command == "show":
            _print_json({"session_id": args.session_id, "settings": session_core.get_processing_settings(root, args.session_id)})
            return 0
        settings = _load_json_object(args.file)
        session_core.save_processing_settings(project_root, root, args.session_id, settings)
        print(f"Options de traitement enregistrées pour {args.session_id}.")
        return 0
    if command == "audio":
        if args.session_audio_command is None:
            args._session_audio_parser.print_help()
            return 0
        if args.session_audio_command == "list":
            detail = session_core.get_session(root, args.session_id).get("audio_tracks_detail", [])
            _print_json(detail) if args.json else [print(f"{'DÉSACTIVÉ' if item['disabled'] else 'ACTIF':<10} {item['filename']}\t{item['path']}") for item in detail]
            return 0
        if args.session_audio_command == "delete" and not args.yes and not _confirm(f"Supprimer la piste {args.filename} ? [y/N] "):
            print("Suppression annulée.")
            return 0
        if args.session_audio_command == "delete":
            result = session_core.delete_audio_track(project_root, root, args.session_id, args.filename)
        else:
            result = session_core.set_audio_track_disabled(project_root, root, args.session_id, args.filename, disabled=args.session_audio_command == "disable")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    return 2


def _print_session(item: dict[str, Any]) -> None:
    print(f"{item.get('title', item['id'])} ({item['id']})")
    print(f"Date : {item.get('started_at') or 'inconnue'}")
    print(f"Durée : {item.get('duration_seconds') or 'inconnue'}")
    print(f"Audio : {', '.join(item.get('audio_tracks') or []) or 'aucune piste'}")
    print(f"Transcription : {'oui' if item.get('transcript') else 'non'}")
    print(f"Résumé : {'oui' if item.get('summary') else 'non'}")
    if item.get("processing_settings"):
        print("Options enregistrées :")
        _print_json(item["processing_settings"])


def _run_artifacts(args: argparse.Namespace, project_root: Path) -> int:
    command = getattr(args, "artifacts_command", None)
    if command is None:
        args._artifacts_parser.print_help()
        return 0
    root = _session_root(project_root, args)
    if command == "show":
        value = session_core.read_session_artifact(root, args.session_id, args.kind)
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(value["content"], encoding="utf-8")
            print(f"{args.kind} enregistré dans {output}\nRévision : {value.get('revision', '')}")
        else:
            print(value["content"], end="" if value["content"].endswith("\n") else "\n")
        return 0
    content = Path(args.file).expanduser().read_text(encoding="utf-8-sig")
    result = session_core.save_summary(project_root, root, args.session_id, content, revision=args.revision, force=args.force)
    print(f"Résumé enregistré : {result['filename']} · révision {result['revision']}")
    return 0


def _run_preferences(args: argparse.Namespace, project_root: Path) -> int:
    command = getattr(args, "preferences_command", None)
    if command is None:
        args._preferences_parser.print_help()
        return 0
    _, store = _stores(project_root)
    if command == "show":
        value = _preferences(project_root)
        if args.json:
            _print_json(value)
        else:
            _print_json(value)
        return 0
    incoming = _load_json_object(args.file)
    current = _preferences(project_root)
    if "settings" in incoming or "ui" in incoming:
        if "settings" in incoming and not isinstance(incoming["settings"], dict):
            raise SessionServiceError("La clé settings doit contenir un objet JSON.")
        if "ui" in incoming and not isinstance(incoming["ui"], dict):
            raise SessionServiceError("La clé ui doit contenir un objet JSON.")
        merged = {**current, **incoming}
    else:
        merged = {**current, "settings": incoming}
    store.save(merged)
    print("Préférences enregistrées. Elles sont partagées entre la CLI et le Web.")
    return 0


def _job_public(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if not key.startswith("_")}


def _web_request(base_url: str, path: str, method: str = "GET", *, timeout: float = 4.0) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(url, method=method, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return json.loads(payload) if payload.strip() else {}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SessionServiceError(f"Impossible de joindre le serveur Web ({url}) : {exc}") from exc


def _run_jobs(args: argparse.Namespace, project_root: Path) -> int:
    command = getattr(args, "jobs_command", None)
    if command is None:
        args._jobs_parser.print_help()
        return 0
    job_store, _ = _stores(project_root)
    records = job_store.load_recent(limit=5000)
    by_id = {str(item.get("id")): item for item in records}
    if command == "list":
        selected = records[-max(1, min(args.limit, 5000)):]
        data = [_job_public(job) for job in reversed(selected)]
        _print_json(data) if args.json else [print(f"{item.get('id')}\t{item.get('state')}\t{item.get('kind')}\t{item.get('session_id') or '-'}\t{item.get('message') or ''}") for item in data]
        return 0
    if command == "show":
        job = by_id.get(args.job_id)
        if job is None:
            raise SessionServiceError(f"Activité introuvable : {args.job_id}")
        _print_json(_job_public(job))
        return 0
    if command == "delete":
        job = by_id.get(args.job_id)
        if job is None:
            raise SessionServiceError(f"Activité introuvable : {args.job_id}")
        if job.get("state") in ACTIVE_STATES:
            raise SessionServiceError("Impossible de supprimer une activité en cours ou en attente.")
        configured_url = args.web_url or os.environ.get("GLIMIO_WEB_URL")
        if configured_url:
            try:
                _web_request(configured_url, f"/api/jobs/{args.job_id}", method="DELETE", timeout=1.0)
            except SessionServiceError:
                # SQLite is still authoritative for history when the Web process isn't running.
                pass
        job_store.delete(args.job_id)
        print(f"Historique supprimé : {args.job_id}")
        return 0
    if command == "clear":
        configured_url = args.web_url or os.environ.get("GLIMIO_WEB_URL")
        if configured_url:
            try:
                response = _web_request(configured_url, "/api/jobs/history", method="DELETE", timeout=1.0)
                print(f"Entrées d’historique supprimées : {response.get('deleted', 0)}. Les jobs actifs sont conservés.")
                return 0
            except SessionServiceError:
                print("Serveur Web indisponible ; nettoyage de l’historique SQLite uniquement.", file=sys.stderr)
        deleted = 0
        for job in records:
            if job.get("state") not in ACTIVE_STATES:
                job_store.delete(str(job["id"]))
                deleted += 1
        print(f"Entrées d’historique supprimées : {deleted}. Les jobs actifs sont conservés.")
        return 0
    base_url = args.web_url or os.environ.get("GLIMIO_WEB_URL") or f"http://127.0.0.1:{os.environ.get('GLIMIO_WEB_PORT', '8765')}"
    if args.job_id not in by_id:
        raise SessionServiceError(f"Activité introuvable : {args.job_id}")
    result = _web_request(base_url, f"/api/jobs/{args.job_id}/cancel", method="POST")
    _print_json(result)
    return 0


def _run_devices(args: argparse.Namespace) -> int:
    try:
        from .core.devices import list_audio_devices
        value = list_audio_devices()
    except Exception as exc:
        raise session_core.SessionServiceError(f"Détection des périphériques impossible : {exc}") from exc
    _print_json(value) if args.json else (print("Microphones :"), [print(f"  {item['name']} ({item['key']})") for item in value["microphone_devices"]], print("Sorties système :"), [print(f"  {item['name']} ({item['key']})") for item in value["output_devices"]])
    return 0


def _run_search(args: argparse.Namespace, project_root: Path) -> int:
    history_dir = _search_history_dir(project_root)
    if args.list_searches:
        values = []
        for path in sorted(history_dir.glob("*.json"), reverse=True)[:100]:
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                values.append({"id": item.get("id", path.stem), "query": item.get("query", ""), "created_at": item.get("created_at"), "source_count": len(item.get("passages") or [])})
            except (OSError, ValueError):
                continue
        _print_json(values) if args.json else [print(f"{item['id']}\t{item.get('source_count', 0)} source(s)\t{item.get('query', '')}") for item in values]
        return 0
    if args.show:
        value = _read_search(project_root, args.show)
        _print_json(value) if args.json else _print_search(value)
        return 0
    if args.synthesize:
        value = _read_search(project_root, args.synthesize)
        original_passages = [dict(item) for item in value.get("passages") or []]
        passages = list(original_passages)
        if args.excerpts:
            try:
                wanted = {int(item.strip()) for item in args.excerpts.split(",") if item.strip()}
            except ValueError as exc:
                raise SessionServiceError("--excerpts doit être une liste de numéros séparés par des virgules.") from exc
            passages = [dict(item) for item in original_passages if int(item.get("source_number", -1)) in wanted]
        if not passages:
            raise SessionServiceError("Aucun extrait sélectionné pour la synthèse.")
        original_numbers = [int(item.get("source_number", index)) for index, item in enumerate(passages, start=1)]
        # Re-number retained references in the synthesis, while retaining all search hits
        # in the saved search so a later synthesis can restore previously excluded excerpts.
        for index, item in enumerate(passages, start=1):
            item["source_number"] = index
        answer = _synthesize(project_root, str(value.get("query") or ""), passages, args)
        value["synthesis_passages"] = passages
        value["synthesis_source_numbers"] = original_numbers
        value["selected_source_numbers"] = original_numbers
        value["synthesis"] = answer
        value["synthesized_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path = _search_history_path(project_root, args.synthesize)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(answer.rstrip() + "\n", encoding="utf-8")
            print(f"Synthèse enregistrée dans {output}")
        else:
            print(answer)
        return 0
    if not args.query or len(args.query.strip()) < 2:
        args._search_parser.print_help()
        return 0
    root = _session_root(project_root, args)
    passages = retrieve_passages(root, args.query, top_k=args.top_k, session_ids=set(args.session_ids or []) or None)
    record: dict[str, Any] = {"query": args.query.strip(), "session_ids": args.session_ids or [], "passages": passages, "root": str(root)}
    search_id = _save_search(project_root, record)
    if args.synthesize_results:
        answer = _synthesize(project_root, args.query.strip(), passages, args)
        record = _read_search(project_root, search_id)
        record["synthesis"] = answer
        record["synthesis_passages"] = [dict(item) for item in passages]
        record["synthesis_source_numbers"] = [int(item.get("source_number", index)) for index, item in enumerate(passages, start=1)]
        record["selected_source_numbers"] = record["synthesis_source_numbers"]
        record["synthesized_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _search_history_path(project_root, search_id).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(answer.rstrip() + "\n", encoding="utf-8")
            print(f"Synthèse enregistrée dans {output}")
        else:
            print(answer)
        print(f"Recherche sauvegardée : {search_id}", file=sys.stderr)
        return 0
    value = _read_search(project_root, search_id)
    if args.json:
        _print_json(value)
    else:
        _print_search(value)
    return 0


def _print_search(value: dict[str, Any]) -> None:
    print(f"Recherche {value.get('id', '')}: {value.get('query', '')}")
    for item in value.get("passages") or []:
        print(f"\n[{item.get('source_number')}] {item.get('title', 'Séance')} · {item.get('session_id')} · {item.get('kind')}")
        print(str(item.get("text") or "").strip())
    if value.get("synthesis"):
        print("\nSYNTHÈSE\n" + str(value["synthesis"]))


def _confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        raise SessionServiceError("Confirmez explicitement avec --yes depuis un terminal non interactif.")
    return input(prompt).strip().casefold() in {"o", "oui", "y", "yes"}


def run_application_cli_command(args: argparse.Namespace, *, project_root: str | Path) -> int | None:
    """Execute a non-processing command; return None for existing CLI actions."""
    root = Path(project_root).expanduser().resolve()
    try:
        if args.command in {"sessions", "session"}:
            return _run_sessions(args, root)
        if args.command == "artifacts":
            return _run_artifacts(args, root)
        if args.command in {"preferences", "prefs"}:
            return _run_preferences(args, root)
        if args.command == "jobs":
            return _run_jobs(args, root)
        if args.command == "devices":
            return _run_devices(args)
        if args.command == "search":
            return _run_search(args, root)
    except session_core.SessionServiceError as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Opération interrompue.", file=sys.stderr)
        return 130
    return None
