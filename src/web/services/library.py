from __future__ import annotations

import json
import re
import wave
from datetime import datetime
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Callable

from seance.layout import get_transcript_path, has_audio, list_audio_paths


MAX_RETRIEVAL_CANDIDATES_PER_SESSION = 8
MIN_RETRIEVAL_CANDIDATE_POOL = 80
RETRIEVAL_CANDIDATES_PER_REQUESTED = 20

SUMMARY_CANDIDATES = (
    Path("summary/resume_audio.md"),
    Path("resume_audio.md"),
    Path("summary/compatibility/compte_rendu.md"),
    Path("summary/compte_rendu.md"),
    Path("compte_rendu.md"),
    Path("summary/compatibility/pv_brouillon.md"),
    Path("summary/pv_brouillon.md"),
    Path("pv_brouillon.md"),
)


def _read_text(path: Path, limit: int | None = None) -> str:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            return stream.read() if limit is None else stream.read(limit)
    except OSError:
        return ""


def _file_contains_query(path: Path, query: str, terms: list[str]) -> bool:
    """Search large documents incrementally, including matches across read-block edges."""
    term_patterns = [re.compile(rf"(?<!\w){re.escape(term)}(?!\w)") for term in terms]
    tail_size = max([len(query), *(len(term) for term in terms)], default=1) + 1
    carry = ""
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            while True:
                block = stream.read(64 * 1024)
                if not block:
                    return False
                folded = (carry + block).casefold()
                if query and query in folded:
                    return True
                if any(pattern.search(folded) for pattern in term_patterns):
                    return True
                carry = folded[-tail_size:] if tail_size > 0 else ""
    except OSError:
        return False


def _iter_text_chunks(path: Path, max_chars: int = 1200) -> Iterator[str]:
    """Yield bounded text chunks from the entire file without loading it all into memory."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive.")
    buffer = ""
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for raw_line in stream:
                line = raw_line.rstrip("\r\n")
                if not line.strip():
                    if buffer.strip():
                        yield buffer.strip()
                    buffer = ""
                    continue
                if len(line) > max_chars:
                    if buffer.strip():
                        yield buffer.strip()
                        buffer = ""
                    offset = 0
                    while offset < len(line):
                        end = min(len(line), offset + max_chars)
                        if end < len(line):
                            # Prefer a word boundary so retrieval does not lose keywords
                            # simply because a long Markdown paragraph is split mid-word.
                            boundary = max(line.rfind(" ", offset, end), line.rfind("\t", offset, end))
                            if boundary >= offset + max_chars // 2:
                                end = boundary
                        part = line[offset:end].strip()
                        if part:
                            yield part
                        offset = end
                        while offset < len(line) and line[offset].isspace():
                            offset += 1
                    continue
                if buffer and len(buffer) + 1 + len(line) > max_chars:
                    yield buffer.strip()
                    buffer = line
                else:
                    buffer = f"{buffer}\n{line}" if buffer else line
        if buffer.strip():
            yield buffer.strip()
    except OSError:
        return


def _metadata(folder: Path) -> dict[str, Any]:
    candidates = (folder / "metadata" / "seance.json", folder / "seance.json")
    for path in candidates:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError, UnicodeError):
            continue
    return {}


def summary_path(folder: Path) -> Path | None:
    for relative in SUMMARY_CANDIDATES:
        candidate = folder / relative
        if candidate.is_file():
            return candidate
    return None


def transcript_path(folder: Path) -> Path | None:
    try:
        candidate = get_transcript_path(folder)
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _session_datetime(folder: Path, metadata: dict[str, Any]) -> str | None:
    try:
        return datetime.strptime(folder.name, "%Y-%m-%d_%H-%M-%S").astimezone().isoformat(timespec="seconds")
    except ValueError:
        pass
    value = metadata.get("started_at")
    return value if isinstance(value, str) else None


def _summary_excerpt(path: Path | None, width: int = 320) -> str:
    if path is None:
        return ""
    text = _read_text(path, 12_000)
    lines = [line.strip(" #\t") for line in text.splitlines() if line.strip() and not line.lstrip().startswith("<!--")]
    return re.sub(r"\s+", " ", " ".join(lines))[:width]


def _audio_duration_seconds(folder: Path, metadata: dict[str, Any]) -> float | None:
    recorded = metadata.get("duration_seconds")
    if isinstance(recorded, (int, float)) and recorded >= 0:
        return float(recorded)
    durations: list[float] = []
    for path in list_audio_paths(folder):
        try:
            with wave.open(str(path), "rb") as stream:
                rate = stream.getframerate()
                if rate > 0:
                    durations.append(stream.getnframes() / rate)
        except (OSError, wave.Error, EOFError):
            continue
    return max(durations) if durations else None


def _session_record(folder: Path, query: str = "") -> dict[str, Any]:
    metadata = _metadata(folder)
    summary = summary_path(folder)
    transcript = transcript_path(folder)
    title = metadata.get("title")
    if not isinstance(title, str) or not title.strip():
        title = folder.name.replace("_", " ")
    record: dict[str, Any] = {
        "id": folder.name,
        "title": title.strip(),
        "started_at": _session_datetime(folder, metadata),
        "summary": summary is not None,
        "transcript": transcript is not None,
        "audio": has_audio(folder),
        "audio_tracks": [path.name for path in list_audio_paths(folder)],
        "duration_seconds": _audio_duration_seconds(folder, metadata),
        "summary_excerpt": _summary_excerpt(summary),
        "has_metadata": bool(metadata),
    }
    if query:
        needle = query.casefold().strip()
        terms = [term for term in re.findall(r"[\wÀ-ÿ]{2,}", needle) if term]
        term_patterns = [re.compile(rf"(?<!\w){re.escape(term)}(?!\w)") for term in terms]
        haystacks = [record["title"], folder.name, record["summary_excerpt"]]
        matched = any(
            needle in value.casefold()
            or any(pattern.search(value.casefold()) for pattern in term_patterns)
            for value in haystacks if value
        )
        if not matched:
            matched = any(
                _file_contains_query(path, needle, terms)
                for path in (summary, transcript) if path is not None
            )
        if not matched:
            record["_exclude"] = True
    return record


def _ordered_session_folders(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    try:
        folders = [path for path in root.iterdir() if path.is_dir() and not path.name.startswith(".")]
    except OSError:
        return []

    def sort_key(path: Path) -> tuple[int, float]:
        try:
            stamp = datetime.strptime(path.name, "%Y-%m-%d_%H-%M-%S")
            return (1, stamp.timestamp())
        except ValueError:
            try:
                return (0, path.stat().st_mtime)
            except OSError:
                return (0, 0.0)

    root_resolved = root.resolve()
    safe_folders: list[Path] = []
    for folder in folders:
        try:
            if folder.resolve().parent == root_resolved:
                safe_folders.append(folder)
        except OSError:
            continue
    safe_folders.sort(key=sort_key, reverse=True)
    return safe_folders


def _passes_filter(item: dict[str, Any], filter_by: str) -> bool:
    if filter_by == "summary":
        return bool(item["summary"])
    if filter_by == "transcript":
        return bool(item["transcript"])
    if filter_by == "audio":
        return bool(item["audio"])
    return True


def list_sessions_page(
    root: Path,
    *,
    query: str = "",
    filter_by: str = "all",
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return a stable page and total matching count; limit=0 means all results."""
    if filter_by not in {"all", "summary", "transcript", "audio"}:
        raise ValueError("Unsupported session filter.")
    offset = max(0, int(offset))
    limit = max(0, int(limit))
    query = query.strip()
    folders = _ordered_session_folders(root)
    matches: list[dict[str, Any]] = []
    for folder in folders:
        try:
            item = _session_record(folder, query)
        except (OSError, ValueError):
            continue
        if item.pop("_exclude", False) or not _passes_filter(item, filter_by):
            continue
        matches.append(item)

    total = len(matches)
    if limit == 0:
        return matches[offset:], total
    # Bound single-page responses; clients wanting everything explicitly use limit=0.
    limit = min(limit, 1000)
    return matches[offset:offset + limit], total


def list_sessions(root: Path, *, query: str = "", filter_by: str = "all", limit: int = 250) -> list[dict[str, Any]]:
    """Compatibility list API. Use list_sessions_page for user-facing pagination."""
    items, _ = list_sessions_page(root, query=query, filter_by=filter_by, limit=limit, offset=0)
    return items


def describe_session(folder: Path) -> dict[str, Any]:
    """Build the library record for one already validated session folder."""
    return _session_record(folder)


def resolve_session_folder(root: Path, session_id: str) -> Path:
    """Resolve a session ID strictly as one direct child of the configured root."""
    if not session_id or session_id in {".", ".."} or "/" in session_id or "\\" in session_id:
        raise ValueError("Invalid session identifier.")
    candidate = (root / session_id).resolve()
    if candidate.parent != root.resolve() or not candidate.is_dir():
        raise FileNotFoundError("Session not found.")
    return candidate


def read_artifact(root: Path, session_id: str, kind: str) -> dict[str, str]:
    folder = resolve_session_folder(root, session_id)
    if kind == "summary":
        path = summary_path(folder)
    elif kind == "transcript":
        path = transcript_path(folder)
    else:
        raise ValueError("Unsupported artifact type.")
    if path is None:
        raise FileNotFoundError(f"No {kind} found for this session.")
    return {"session_id": session_id, "kind": kind, "filename": path.name, "content": _read_text(path)}


def _rank_passages(passages: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """Return the current best distinct passages, with display reference numbers."""
    ranked = sorted(passages, key=lambda item: item["score"], reverse=True)
    chosen: list[dict[str, Any]] = []
    per_session: dict[str, int] = {}
    for item in ranked:
        sid = item["session_id"]
        if per_session.get(sid, 0) >= 3:
            continue
        chosen.append(dict(item))
        per_session[sid] = per_session.get(sid, 0) + 1
        if len(chosen) >= max(1, min(top_k, 20)):
            break
    for index, item in enumerate(chosen, start=1):
        item["source_number"] = index
    return chosen


def retrieve_passages(
    root: Path,
    query: str,
    top_k: int = 8,
    *,
    on_update: Callable[[list[dict[str, Any]], dict[str, int]], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve relevant passages locally, optionally publishing results as they are found.

    ``on_update`` receives the current ranked top-k and scan progress. ``should_stop``
    allows a caller to cancel the scan without waiting for every session to be read.
    """
    raw_terms = list(dict.fromkeys(re.findall(r"[\wÀ-ÿ]{2,}", query.casefold())))
    stop_words = {
        "que", "qui", "quoi", "dans", "avec", "pour", "des", "les", "une", "est",
        "sur", "par", "comment", "quels", "quelles", "cela", "cette", "the", "and",
        "for", "from", "that", "with", "what", "where", "when", "which", "have", "does",
    }
    query_terms = [term for term in raw_terms if term not in stop_words] or raw_terms
    term_patterns = {
        term: re.compile(rf"(?<!\w){re.escape(term)}(?!\w)")
        for term in query_terms
    }
    if not root.is_dir():
        return []

    all_passages: list[dict[str, Any]] = []
    total_matches = 0
    # Keep enough alternatives for reranking and cross-session diversity without letting
    # long transcripts consume unbounded RAM. The user-facing found count remains cumulative.
    candidate_pool_limit = max(
        MIN_RETRIEVAL_CANDIDATE_POOL,
        min(top_k, 20) * RETRIEVAL_CANDIDATES_PER_REQUESTED,
    )
    per_session_candidate_limit = MAX_RETRIEVAL_CANDIDATES_PER_SESSION
    try:
        candidate_folders = [
            folder for folder in root.iterdir()
            if folder.is_dir() and not folder.name.startswith(".")
        ]
        root_resolved = root.resolve()
        candidate_folders = [
            folder for folder in candidate_folders
            if folder.resolve().parent == root_resolved
        ]
    except OSError:
        return []

    # Timestamped session names sort naturally; newest sessions are scanned first so
    # useful results tend to appear quickly even in a large archive.
    candidate_folders.sort(key=lambda folder: folder.name, reverse=True)
    total = len(candidate_folders)
    progress = {"sessions_scanned": 0, "sessions_total": total, "passages_found": 0}

    def publish() -> None:
        if on_update is not None:
            on_update(_rank_passages(all_passages, top_k), dict(progress))

    for session_index, folder in enumerate(candidate_folders, start=1):
        if should_stop is not None and should_stop():
            break
        metadata = _metadata(folder)
        title_value = metadata.get("title")
        title = title_value.strip() if isinstance(title_value, str) and title_value.strip() else folder.name
        sources = (("summary", summary_path(folder)), ("transcript", transcript_path(folder)))
        for kind, path in sources:
            if should_stop is not None and should_stop():
                break
            if not path:
                continue
            # Scan the entire file incrementally: no arbitrary 5 MB prefix cutoff.
            for chunk in _iter_text_chunks(path, max_chars=1200):
                if should_stop is not None and should_stop():
                    break
                folded = chunk.casefold()
                counts = {term: len(pattern.findall(folded)) for term, pattern in term_patterns.items()}
                matched = [term for term, count in counts.items() if count]
                if not matched:
                    continue
                total_matches += 1
                # Prefer repeated whole-word matches, title matches, and existing summaries.
                score = sum(min(counts[term], 4) for term in matched) / max(1, len(query_terms))
                title_folded = str(title).casefold()
                if any(pattern.search(title_folded) for pattern in term_patterns.values()):
                    score += 0.75
                if kind == "summary":
                    score += 0.15
                all_passages.append({
                    "session_id": folder.name,
                    "title": str(title),
                    "kind": kind,
                    "filename": path.name,
                    "text": chunk[:1400],
                    "score": round(score, 4),
                })
                # Limit candidates per session first, then globally; always retain the best
                # scoring candidates found so far so an early verbose session cannot dominate.
                session_candidates = [candidate for candidate in all_passages if candidate["session_id"] == folder.name]
                if len(session_candidates) > per_session_candidate_limit:
                    weakest = min(
                        enumerate(session_candidates),
                        key=lambda pair: (pair[1]["score"], -pair[0]),
                    )[1]
                    all_passages.remove(weakest)
                while len(all_passages) > candidate_pool_limit:
                    weakest = min(
                        enumerate(all_passages),
                        key=lambda pair: (pair[1]["score"], -pair[0]),
                    )[1]
                    all_passages.remove(weakest)
                progress["passages_found"] = total_matches
                # Publish each of the first hits immediately. After the first handful,
                # refresh at each session boundary to avoid sorting thousands of matches
                # for every chunk in a long transcript.
                if len(all_passages) <= max(16, min(top_k, 20) * 2):
                    publish()
        progress["sessions_scanned"] = session_index
        publish()

    return _rank_passages(all_passages, top_k)
