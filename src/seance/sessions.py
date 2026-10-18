from pathlib import Path
from datetime import datetime
from .layout import has_audio, has_transcript
def latest_session(directory='seances', *, require=None):
    root=Path(directory).resolve()
    candidates=[p for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    if require=='audio': candidates=[p for p in candidates if has_audio(p)]
    elif require=='transcript': candidates=[p for p in candidates if has_transcript(p)]
    elif require=='processable': candidates=[p for p in candidates if has_audio(p) or has_transcript(p)]
    if not candidates: raise SystemExit('No session found')
    return max(candidates, key=lambda p:p.name)
def resolve_session(folder, directory, *, require=None):
    p=Path(folder).expanduser().resolve() if folder else latest_session(directory, require=require)
    if not p.is_dir(): raise SystemExit(f'Session not found: {p}')
    return p
