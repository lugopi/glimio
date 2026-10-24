from pathlib import Path
import re

AUDIO_NAMES = ('micro.wav', 'windows.wav', 'audio_import.wav')
_DYNAMIC_AUDIO_NAME = re.compile(r'^(?:micro|windows|audio_import)(?:-\d+)?(?:-ch\d+)?\.wav$', re.IGNORECASE)
TRANSCRIPT_NAMES = ('micro.srt','windows.srt','audio_import.srt','transcription.json','transcription.md','speaker_diarization.json','transcription_before_diarization.json','transcription_before_diarization.md')


def ensure_session_layout(folder):
    root=Path(folder).expanduser().resolve()
    paths={k:root/v for k,v in [('root','.'),('audio','audio'),('transcript','transcript'),('analysis','analysis'),('summary','summary'),('metadata','metadata')]}
    for k,v in paths.items():
        if k!='root': v.mkdir(parents=True,exist_ok=True)
    (paths['analysis']/'parts').mkdir(parents=True,exist_ok=True); (paths['analysis']/'diagnostics').mkdir(parents=True,exist_ok=True); (paths['summary']/'compatibility').mkdir(parents=True,exist_ok=True)
    # Migrate familiar tracks plus numbered/imported tracks created by newer versions.
    for s in root.glob("*.wav"):
        if _valid_audio_name(s.name):
            d = paths["audio"] / s.name
            if s.is_file() and not d.exists():
                d.parent.mkdir(parents=True, exist_ok=True)
                s.replace(d)
    for name in TRANSCRIPT_NAMES:
        s=root/name; d=paths['transcript']/name
        if s.is_file() and not d.exists(): d.parent.mkdir(parents=True,exist_ok=True); s.replace(d)
    for name in ('resume_audio.md','resume_audio_initial.md'):
        s=root/name; d=paths['summary']/name
        if s.is_file() and not d.exists(): s.replace(d)
    for name in ('compte_rendu.md','pv_brouillon.md','pv_brouillon_initial.md'):
        s=root/name; d=paths['summary']/'compatibility'/name
        if s.is_file() and not d.exists(): s.replace(d)
    for name in ('seance.json',):
        s=root/name; d=paths['metadata']/name
        if s.is_file() and not d.exists(): s.replace(d)
    return paths


def _valid_audio_name(filename: str) -> bool:
    return filename in AUDIO_NAMES or bool(_DYNAMIC_AUDIO_NAME.fullmatch(filename))


def get_audio_path(folder,filename):
    if not isinstance(filename, str) or not _valid_audio_name(filename) or Path(filename).name != filename:
        return Path(folder).resolve() / 'audio' / '__invalid_audio_filename__'
    root=Path(folder).resolve(); a=root/'audio'/filename; l=root/filename
    return a if a.is_file() else l if l.is_file() else a


def list_audio_paths(folder):
    root=Path(folder).resolve()
    audio_dir=root/'audio'
    candidates: dict[str, Path] = {}
    # Keep a stable order for familiar tracks, then numbered endpoints, then imports.
    if audio_dir.is_dir():
        for path in audio_dir.glob('*.wav'):
            if _valid_audio_name(path.name) and path.is_file():
                candidates[path.name] = path
    for name in AUDIO_NAMES:
        legacy=root/name
        if legacy.is_file(): candidates.setdefault(name, legacy)
    if not candidates:
        return []
    def sort_key(name: str):
        stem = name[:-4]
        base, _, suffix = stem.partition('-')
        channel = 0
        if "-ch" in suffix:
            suffix, channel_suffix = suffix.split("-ch", 1)
            channel = int(channel_suffix or 0)
        number = int(suffix) if suffix.isdigit() else 0
        if base == "micro": return (0, number, channel)
        if base == "windows": return (1, number, channel)
        if base == "audio_import": return (2, number, channel)
        return (3, name)
    return [candidates[name] for name in sorted(candidates, key=sort_key)]


def has_audio(folder): return bool(list_audio_paths(folder))
def get_transcript_path(folder,filename='transcription.md'):
    root=Path(folder).resolve(); a=root/'transcript'/filename; l=root/filename
    return a if a.is_file() else l if l.is_file() else a
def has_transcript(folder): return get_transcript_path(folder).is_file()
def analysis_output_path(folder,filename,*,subdir=None):
    p=Path(folder).resolve()/'analysis'
    if subdir: p=p/subdir
    p.mkdir(parents=True,exist_ok=True); return p/filename
def summary_output_path(folder,filename,*,compatibility=False):
    p=Path(folder).resolve()/'summary'
    if compatibility: p=p/'compatibility'
    p.mkdir(parents=True,exist_ok=True); return p/filename
def metadata_output_path(folder,filename='seance.json'):
    p=Path(folder).resolve()/'metadata'; p.mkdir(parents=True,exist_ok=True); return p/filename
def transcript_output_path(folder,filename):
    p=Path(folder).resolve()/'transcript'; p.mkdir(parents=True,exist_ok=True); return p/filename


def disabled_audio_names(folder):
    """Return track filenames explicitly excluded from future transcription/diarization."""
    root = Path(folder).expanduser().resolve()
    candidates = (root / 'metadata' / 'seance.json', root / 'seance.json')
    for path in candidates:
        if not path.is_file():
            continue
        try:
            import json
            value = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, ValueError):
            continue
        raw = value.get('disabled_audio_tracks', []) if isinstance(value, dict) else []
        if isinstance(raw, list):
            return {name for name in raw if isinstance(name, str) and Path(name).name == name}
    return set()


def list_enabled_audio_paths(folder):
    """List usable audio files, respecting soft-disabled track choices."""
    disabled = disabled_audio_names(folder)
    return [path for path in list_audio_paths(folder) if path.name not in disabled]
