from pathlib import Path
AUDIO_NAMES=('micro.wav','windows.wav','audio_import.wav')
TRANSCRIPT_NAMES=('micro.srt','windows.srt','audio_import.srt','transcription.json','transcription.md','speaker_diarization.json','transcription_before_diarization.json','transcription_before_diarization.md')
def ensure_session_layout(folder):
    root=Path(folder).expanduser().resolve()
    paths={k:root/v for k,v in [('root','.'),('audio','audio'),('transcript','transcript'),('analysis','analysis'),('summary','summary'),('metadata','metadata')]}
    for k,v in paths.items():
        if k!='root': v.mkdir(parents=True,exist_ok=True)
    (paths['analysis']/'parts').mkdir(parents=True,exist_ok=True); (paths['analysis']/'diagnostics').mkdir(parents=True,exist_ok=True); (paths['summary']/'compatibility').mkdir(parents=True,exist_ok=True)
    for name in AUDIO_NAMES:
        s=root/name; d=paths['audio']/name
        if s.is_file() and not d.exists(): d.parent.mkdir(parents=True,exist_ok=True); s.replace(d)
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
def get_audio_path(folder,filename):
    root=Path(folder).resolve(); a=root/'audio'/filename; l=root/filename
    return a if a.is_file() else l if l.is_file() else a
def list_audio_paths(folder): return [p for n in AUDIO_NAMES if (p:=get_audio_path(folder,n)).is_file()]
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
