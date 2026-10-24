"""Framework-independent application services for the local session library.

This module intentionally imports no Web framework. Both the Web adapter and the
CLI can call these operations and therefore share path validation, metadata rules,
and destructive-operation safeguards.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from seance.layout import list_audio_paths
from seance.core.library import (
    describe_session, list_sessions_page, read_artifact, resolve_session_folder,
    summary_path, transcript_path,
)
from seance.core.job_store import JobStore
from seance.core.sqlite_db import SQLiteDatabase, database_path

ACTIVE_JOB_STATES = {"queued", "running", "stopping"}


class SessionServiceError(RuntimeError):
    """A user-facing session operation error, independent of HTTP or CLI."""


def _metadata_path(folder: Path) -> Path:
    structured = folder / "metadata" / "seance.json"
    legacy = folder / "seance.json"
    if structured.is_file() or not legacy.is_file():
        return structured
    return legacy


def read_metadata(folder: Path) -> dict[str, Any]:
    path = _metadata_path(folder)
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SessionServiceError(f"Impossible de lire les métadonnées de {folder.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise SessionServiceError(f"Les métadonnées de {folder.name} ne sont pas un objet JSON.")
    return value


def write_metadata(folder: Path, metadata: dict[str, Any]) -> None:
    if not isinstance(metadata, dict):
        raise SessionServiceError("Les métadonnées doivent être un objet JSON.")
    path = _metadata_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        raise SessionServiceError(f"Impossible d'enregistrer les métadonnées : {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _job_store(project_root: str | Path) -> JobStore:
    db = SQLiteDatabase(database_path(project_root))
    db.initialize()
    return JobStore(db)


def active_jobs_for_session(project_root: str | Path, session_id: str) -> list[dict[str, Any]]:
    """Read active jobs from the same durable SQLite store used by the Web process."""
    return [
        job for job in _job_store(project_root).load_recent(limit=5000)
        if job.get("session_id") == session_id and job.get("state") in ACTIVE_JOB_STATES
    ]


def ensure_session_idle(project_root: str | Path, session_id: str, *, action: str = "modifier cette séance") -> None:
    active = active_jobs_for_session(project_root, session_id)
    if active:
        kinds = ", ".join(dict.fromkeys(str(job.get("kind") or "traitement") for job in active))
        raise SessionServiceError(f"Impossible de {action} pendant une activité en cours ({kinds}).")


def list_sessions(
    root: str | Path,
    *, query: str = "", filter_by: str = "all", limit: int = 25, offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    try:
        return list_sessions_page(Path(root).expanduser().resolve(), query=query, filter_by=filter_by, limit=limit, offset=offset)
    except ValueError as exc:
        raise SessionServiceError(str(exc)) from exc


def get_session(root: str | Path, session_id: str) -> dict[str, Any]:
    try:
        folder = resolve_session_folder(Path(root).expanduser().resolve(), session_id)
    except (ValueError, FileNotFoundError) as exc:
        raise SessionServiceError(str(exc)) from exc
    item = describe_session(folder)
    metadata = read_metadata(folder)
    item["metadata"] = metadata
    item["files"] = {
        "summary": item.get("summary", False),
        "transcript": item.get("transcript", False),
        "audio_tracks": item.get("audio_tracks", []),
        "analysis": (folder / "analysis" / "analyses.md").is_file(),
    }
    item["processing_settings"] = metadata.get("processing_settings", {})
    disabled = metadata.get("disabled_audio_tracks", [])
    disabled_set = set(disabled) if isinstance(disabled, list) else set()
    item["audio_tracks_detail"] = [
        {"filename": path.name, "disabled": path.name in disabled_set, "path": str(path)}
        for path in list_audio_paths(folder)
    ]
    return item


def rename_session(project_root: str | Path, root: str | Path, session_id: str, title: str) -> dict[str, Any]:
    title = str(title).strip()
    if not title:
        raise SessionServiceError("Le titre ne peut pas être vide.")
    if len(title) > 120:
        raise SessionServiceError("Le titre doit contenir au maximum 120 caractères.")
    ensure_session_idle(project_root, session_id, action="renommer")
    try:
        folder = resolve_session_folder(Path(root).expanduser().resolve(), session_id)
    except (ValueError, FileNotFoundError) as exc:
        raise SessionServiceError("Séance introuvable ou identifiant invalide.") from exc
    metadata = read_metadata(folder)
    metadata["title"] = title
    metadata["title_source"] = "user"
    write_metadata(folder, metadata)
    return {"id": folder.name, "title": title, "metadata": metadata}


def delete_session(project_root: str | Path, root: str | Path, session_id: str) -> dict[str, Any]:
    ensure_session_idle(project_root, session_id, action="supprimer")
    try:
        folder = resolve_session_folder(Path(root).expanduser().resolve(), session_id)
    except (ValueError, FileNotFoundError) as exc:
        raise SessionServiceError("Séance introuvable ou identifiant invalide.") from exc
    try:
        shutil.rmtree(folder)
    except OSError as exc:
        raise SessionServiceError(f"Impossible de supprimer la séance : {exc}") from exc
    return {"deleted": True, "id": session_id}


def set_audio_track_disabled(
    project_root: str | Path, root: str | Path, session_id: str, filename: str, *, disabled: bool,
) -> dict[str, Any]:
    _validate_audio_filename(filename)
    ensure_session_idle(project_root, session_id, action="modifier une piste audio")
    folder = _resolve_session(root, session_id)
    tracks = {path.name for path in list_audio_paths(folder)}
    if filename not in tracks:
        raise SessionServiceError(f"Piste audio introuvable : {filename}")
    metadata = read_metadata(folder)
    raw_disabled = metadata.get("disabled_audio_tracks", [])
    disabled_set = {item for item in raw_disabled if isinstance(item, str)} if isinstance(raw_disabled, list) else set()
    if disabled:
        candidate = disabled_set | {filename}
        if not (tracks - candidate):
            raise SessionServiceError("Au moins une piste audio doit rester active.")
        disabled_set.add(filename)
    else:
        disabled_set.discard(filename)
    metadata["disabled_audio_tracks"] = sorted(disabled_set)
    _mark_audio_outputs_stale(folder, metadata)
    write_metadata(folder, metadata)
    return {"id": session_id, "filename": filename, "disabled_audio_tracks": sorted(disabled_set), "metadata": metadata}


def delete_audio_track(project_root: str | Path, root: str | Path, session_id: str, filename: str) -> dict[str, Any]:
    _validate_audio_filename(filename)
    ensure_session_idle(project_root, session_id, action="supprimer une piste audio")
    folder = _resolve_session(root, session_id)
    tracks = {path.name: path for path in list_audio_paths(folder)}
    path = tracks.get(filename)
    if path is None or not path.is_file():
        raise SessionServiceError(f"Piste audio introuvable : {filename}")
    metadata = read_metadata(folder)
    try:
        path.unlink()
    except OSError as exc:
        raise SessionServiceError(f"Impossible de supprimer la piste audio : {exc}") from exc
    warnings: list[str] = []
    stem = Path(filename).stem
    for candidate in (folder / "transcript" / f"{stem}.srt", folder / f"{stem}.srt"):
        try:
            candidate.unlink(missing_ok=True)
        except OSError as exc:
            warnings.append(f"La transcription individuelle {candidate.name} n'a pas pu être supprimée : {exc}")
    for field, predicate in (
        ("disabled_audio_tracks", lambda value: value != filename),
        ("audio_sources", lambda value: not (isinstance(value, dict) and value.get("filename") == filename)),
        ("captured_tracks", lambda value: value != stem),
    ):
        values = metadata.get(field)
        if isinstance(values, list):
            metadata[field] = [value for value in values if predicate(value)]
    _mark_audio_outputs_stale(folder, metadata)
    write_metadata(folder, metadata)
    return {"id": session_id, "filename": filename, "audio_tracks": [item.name for item in list_audio_paths(folder)], "metadata": metadata, "warnings": warnings}


def get_processing_settings(root: str | Path, session_id: str) -> dict[str, Any]:
    return dict(read_metadata(_resolve_session(root, session_id)).get("processing_settings") or {})


def save_processing_settings(
    project_root: str | Path, root: str | Path, session_id: str, settings: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(settings, dict):
        raise SessionServiceError("Les options doivent être un objet JSON.")
    ensure_session_idle(project_root, session_id, action="modifier les options de traitement")
    folder = _resolve_session(root, session_id)
    metadata = read_metadata(folder)
    metadata["processing_settings"] = settings
    write_metadata(folder, metadata)
    return {"id": session_id, "settings": settings, "metadata": metadata}


def read_session_artifact(root: str | Path, session_id: str, kind: str) -> dict[str, str]:
    try:
        return read_artifact(Path(root).expanduser().resolve(), session_id, kind)
    except (ValueError, FileNotFoundError) as exc:
        raise SessionServiceError(str(exc)) from exc


def save_summary(
    project_root: str | Path, root: str | Path, session_id: str, content: str,
    *, revision: str | None = None, force: bool = False,
) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise SessionServiceError("Le résumé ne peut pas être vide.")
    if len(content) > 2_000_000:
        raise SessionServiceError("Le résumé dépasse la taille maximale de 2 000 000 caractères.")
    ensure_session_idle(project_root, session_id, action="modifier le résumé")
    folder = _resolve_session(root, session_id)
    path = summary_path(folder)
    if path is None:
        raise SessionServiceError("Aucun résumé existant à modifier pour cette séance.")
    try:
        stat = path.stat()
    except OSError as exc:
        raise SessionServiceError("Le résumé n'est plus disponible.") from exc
    current_revision = f"{stat.st_mtime_ns}:{stat.st_size}"
    if revision is not None and revision != current_revision and not force:
        raise SessionServiceError("Le résumé a changé depuis son chargement. Rechargez-le avant de sauvegarder.")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="")
        temporary.replace(path)
        stat = path.stat()
    except OSError as exc:
        raise SessionServiceError(f"Impossible d'enregistrer le résumé : {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return {"session_id": session_id, "kind": "summary", "filename": path.name, "revision": f"{stat.st_mtime_ns}:{stat.st_size}", "content": content, "live": False}


def _validate_audio_filename(filename: str) -> None:
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.lower().endswith(".wav"):
        raise SessionServiceError("Nom de piste audio invalide.")


def _resolve_session(root: str | Path, session_id: str) -> Path:
    try:
        return resolve_session_folder(Path(root).expanduser().resolve(), session_id)
    except ValueError as exc:
        raise SessionServiceError("Identifiant de séance invalide.") from exc
    except FileNotFoundError as exc:
        raise SessionServiceError("Séance introuvable.") from exc


def _mark_audio_outputs_stale(folder: Path, metadata: dict[str, Any]) -> None:
    if transcript_path(folder) is not None:
        metadata["audio_transcript_stale"] = True
    if summary_path(folder) is not None:
        metadata["audio_summary_stale"] = True
