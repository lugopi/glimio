"""Command-line entry point for local Glimio session processing."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from pathlib import Path

from . import __version__
from .media import audio
from .processing import minutes, pipeline, transcription
from .processing.report_formats import REPORT_FORMATS
from .summary_languages import SUMMARY_LANGUAGE_CODES
from .project_paths import (
    DEFAULT_LLAMA_COMPLETION_PATH, DEFAULT_WHISPER_CLI_PATH, discover_project_root,
)
from .providers.events import reset_provider_event_callback, set_provider_event_callback
from .providers import (
    DEFAULT_DIARIZATION_PROVIDER, DEFAULT_TEXT_PROVIDER, DEFAULT_TRANSCRIPTION_PROVIDER,
    DIARIZATION_PROVIDER_IDS, TEXT_PROVIDER_IDS, TRANSCRIPTION_PROVIDER_IDS,
)
from .providers.selection import reset_text_provider, set_text_provider
from .providers.audio_processing import (
    ENHANCEMENT_PROVIDER_FACTORIES, SEPARATION_PROVIDER_FACTORIES, EMBEDDING_PROVIDER_FACTORIES,
)
from .providers.media_tools import DEFAULT_MEDIA_PROVIDER, MEDIA_PROVIDER_IDS
from .providers.cli import add_provider_cli_parser, run_provider_command
from .cli_commands import add_application_cli_parsers, run_application_cli_command


PROJECT_ROOT = discover_project_root(package_file=__file__)
DEFAULT_THREADS = max(1, (os.cpu_count() or 4) // 2)
VALID_FORMATS = REPORT_FORMATS

APP_VERSION = __version__


def _project_path(value: str) -> str:
    path = Path(value).expanduser()
    return str(path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve())


def _add_processing_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", nargs="?", help="Fichier audio/vidéo ou dossier d’une séance (par défaut : dernière séance admissible).")
    parser.add_argument("--directory", default=str(PROJECT_ROOT / "seances"), help="Dossier des séances (défaut : seances/).")
    parser.add_argument("--whisper-cli", default=DEFAULT_WHISPER_CLI_PATH, help="Chemin vers whisper-cli.")
    parser.add_argument("--model", default="models/asr/model.bin", help="Chemin vers le modèle Whisper.")
    parser.add_argument("--language", default="auto", help="Langue de transcription (ex. fr, en ou auto).")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS, help="Nombre de threads CPU pour Whisper.")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Commande ou chemin vers FFmpeg (alias des options du provider ffmpeg).")
    parser.add_argument("--ffprobe", default="ffprobe", help="Commande ou chemin vers ffprobe (alias des options du provider ffmpeg).")
    parser.add_argument("--media-provider", choices=MEDIA_PROVIDER_IDS, default=DEFAULT_MEDIA_PROVIDER,
                        help="Provider de la chaîne média (import et découpage audio).")
    parser.add_argument(
        "--speech-enhancement", choices=("auto", "off", "ffmpeg", "deepfilter"), default=None,
        help="Alias historique du provider d’amélioration audio.",
    )
    parser.add_argument("--audio-enhancement-provider", choices=tuple(ENHANCEMENT_PROVIDER_FACTORIES), default="ffmpeg-denoise", help="Provider indépendant de prétraitement audio.")
    parser.add_argument("--source-separation-provider", choices=tuple(SEPARATION_PROVIDER_FACTORIES), default="no-separation", help="Provider facultatif de séparation des voix superposées.")
    parser.add_argument("--speaker-embedding-provider", choices=tuple(EMBEDDING_PROVIDER_FACTORIES), default="speechbrain-ecapa", help="Provider facultatif de rapprochement global des voix; SepFormer exige ECAPA.")
    parser.add_argument("--provider-options-file", default=None, help="Fichier JSON contenant les options provider par identifiant (aide : glimio providers info ID).")
    parser.add_argument("--ecapa-model-dir", default=None, help="Dossier local du modèle SpeechBrain ECAPA.")
    parser.add_argument("--sepformer-model-dir", default=None, help="Dossier local du modèle SpeechBrain SepFormer.")
    parser.add_argument("--provider-device", choices=("auto", "cpu", "cuda"), default=None, help="Périphérique pour les providers audio qui le déclarent (auto, cpu ou cuda).")
    parser.add_argument("--sepformer-chunk-seconds", type=int, choices=(10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60), default=None, help="Longueur des blocs SepFormer en secondes.")
    parser.add_argument("--deep-filter-executable", default=None, help="Chemin vers le binaire DeepFilterNet installé séparément.")
    parser.add_argument("--deep-filter-model", default=None, help="Chemin vers l’archive modèle DeepFilterNet .tar.gz téléchargée séparément.")
    parser.add_argument("--vad-mode", choices=("auto", "on", "off"), default=None, help="Détection de parole Whisper.cpp : auto si le modèle est installé, on ou off.")
    parser.add_argument("--vad-model", default=None, help="Chemin vers le modèle VAD Silero de whisper.cpp.")
    parser.add_argument("--vad-threshold", type=float, default=None, help="Seuil VAD entre 0.05 et 0.95 (défaut : 0.5).")
    parser.add_argument("--diarize", action="store_true", help="Activer la diarisation avec le provider sélectionné.")
    parser.add_argument("--diarization-provider", choices=DIARIZATION_PROVIDER_IDS, default=DEFAULT_DIARIZATION_PROVIDER,
                        help="Provider de diarisation (options dans --provider-options-file).")
    parser.add_argument("--segmentation-model", default="models/diarization/segmentation/segmentation.onnx")
    parser.add_argument("--embedding-model", default="models/diarization/embedding/embedding.onnx")
    parser.add_argument("--speakers", type=int, default=-1, help="Nombre d’interlocuteurs, -1 pour automatique.")
    parser.add_argument("--diarization-threshold", type=float, default=0.5)
    parser.add_argument("--llama-completion", default=DEFAULT_LLAMA_COMPLETION_PATH, help="Chemin vers llama-completion.")
    parser.add_argument("--text-provider", choices=TEXT_PROVIDER_IDS, default=DEFAULT_TEXT_PROVIDER, help="Provider de génération.")
    parser.add_argument("--transcription-provider", choices=TRANSCRIPTION_PROVIDER_IDS, default=DEFAULT_TRANSCRIPTION_PROVIDER, help="Provider de transcription.")
    parser.add_argument("--gguf", default="models/llm/model.gguf", help="Chemin vers le modèle GGUF.")
    parser.add_argument("--context", type=int, default=16384)
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--analysis-tokens", type=int, default=3500)
    parser.add_argument("--analysis-retries", type=int, default=3)
    parser.add_argument("--analysis-max-splits", type=int, default=6)
    parser.add_argument("--format", choices=VALID_FORMATS, default="auto", help="Format de compte rendu.")
    parser.add_argument("--summary-language", choices=SUMMARY_LANGUAGE_CODES, default="auto", help="Langue de rédaction du résumé (auto suit la langue dominante de la transcription).")
    parser.add_argument("--no-review", action="store_true", help="Désactiver la révision finale du compte rendu.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glimio",
        description="Transcrire et résumer localement un fichier audio ou une séance Glimio.",
    )
    parser.add_argument("--version", action="version", version=f"Glimio {APP_VERSION}")
    commands = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("record", "Enregistrer le microphone et/ou le son Windows (Ctrl+C pour arrêter)."),
        ("transcribe", "Transcrire un fichier audio ou une séance."),
        ("summarize", "Créer un compte rendu à partir d’une transcription ou d’un audio."),
        ("process", "Transcrire si nécessaire, puis créer un compte rendu."),
    ):
        command = commands.add_parser(name, help=help_text, description=help_text)
        _add_processing_options(command)
        if name == "record":
            command.add_argument("--title", help="Titre de la séance.")
            command.add_argument("--microphone", dest="capture_microphone", action=argparse.BooleanOptionalAction, default=True,
                                 help="Capturer le microphone (défaut : oui). Utiliser --no-microphone pour le désactiver.")
            command.add_argument("--windows-audio", action=argparse.BooleanOptionalAction, default=True,
                                 help="Capturer le son système Windows (défaut : oui). Utiliser --no-windows-audio pour le désactiver.")
            command.add_argument("--microphone-name", dest="microphone", help="Nom du microphone à utiliser.")
            command.add_argument("--output-name", dest="output", help="Nom de la sortie audio Windows à capturer.")
            command.add_argument("--bitrate", dest="audio_bitrate_kbps", type=int, choices=(128, 256, 384, 512, 768), default=256)
            command.add_argument("--normalize-windows", action=argparse.BooleanOptionalAction, default=None)
            command.add_argument("--max-gain-db", dest="normalize_windows_max_gain_db", type=float, default=None)
            workflow = command.add_mutually_exclusive_group()
            workflow.add_argument("--auto-transcribe", action="store_true", help="Transcrire après l’enregistrement.")
            workflow.add_argument("--auto-process", dest="auto_pv", action="store_true",
                                  help="Transcrire puis créer un résumé après l’enregistrement.")

    import_parser = commands.add_parser("import", help="Importer un fichier audio/vidéo dans la bibliothèque locale.")
    _add_processing_options(import_parser)
    import_parser.add_argument("--title", help="Titre de la séance importée.")
    import_parser.add_argument("--normalize", action=argparse.BooleanOptionalAction, default=False,
                               help="Normaliser le volume au maximum configuré (défaut : désactivé).")
    import_parser.add_argument("--max-gain-db", type=float, default=30.0,
                               help="Gain maximal de normalisation entre 0 et 30 dB.")
    import_parser.add_argument("--split-channels", action=argparse.BooleanOptionalAction, default=True,
                               help="Conserver les canaux séparés dans des pistes mono (défaut : oui).")
    import_parser.add_argument("--import-action", choices=("none", "transcribe", "process"), default="none",
                               help="Après import : ne rien lancer, transcrire, ou traiter complètement.")

    add_provider_cli_parser(commands)
    add_application_cli_parsers(commands)
    return parser


def _read_provider_options_file(value: str | None) -> dict[str, dict[str, object]]:
    if not value:
        return {}
    options_path = Path(_project_path(value))
    try:
        payload = json.loads(options_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Impossible de lire le fichier d’options provider {options_path}: {exc}") from exc
    if not isinstance(payload, dict) or any(not isinstance(key, str) or not isinstance(item, dict) for key, item in payload.items()):
        raise SystemExit("Le fichier provider-options doit être un objet JSON dont chaque valeur est un objet d’options.")
    return {str(key): dict(item) for key, item in payload.items()}


def _args_namespace(args: argparse.Namespace) -> argparse.Namespace:
    values = vars(args).copy()
    values["folder"] = values.pop("target")
    values["directory"] = _project_path(values["directory"])
    provider_options = _read_provider_options_file(values.pop("provider_options_file", None))
    ecapa_model_dir = values.pop("ecapa_model_dir", None)
    sepformer_model_dir = values.pop("sepformer_model_dir", None)
    provider_device = values.pop("provider_device", None)
    sepformer_chunk_seconds = values.pop("sepformer_chunk_seconds", None)
    if ecapa_model_dir:
        provider_options.setdefault("speechbrain-ecapa", {})["model_dir"] = ecapa_model_dir
    if sepformer_model_dir:
        provider_options.setdefault("speechbrain-sepformer", {})["model_dir"] = sepformer_model_dir
    if provider_device:
        for provider_id in ("speechbrain-ecapa", "speechbrain-sepformer"):
            provider_options.setdefault(provider_id, {})["device"] = provider_device
    if sepformer_chunk_seconds is not None:
        provider_options.setdefault("speechbrain-sepformer", {})["chunk_seconds"] = sepformer_chunk_seconds
    values["provider_options"] = provider_options
    path_fields = {
        "whisper_cli": "whisper_cli",
        "model": "model",
        "segmentation_model": "diarization_segmentation_model",
        "embedding_model": "diarization_embedding_model",
        "llama_completion": "llama_completion",
        "gguf": "gguf",
        "deep_filter_executable": "deep_filter_executable",
        "deep_filter_model": "deep_filter_model",
        "vad_model": "vad_model",
    }
    path_provider_ids = {
        "whisper_cli": (getattr(args, "transcription_provider", None), "whisper.cpp"),
        "model": (getattr(args, "transcription_provider", None), "whisper.cpp"),
        "segmentation_model": (getattr(args, "diarization_provider", None), "sherpa-onnx"),
        "embedding_model": (getattr(args, "diarization_provider", None), "sherpa-onnx"),
        "llama_completion": (getattr(args, "text_provider", None), "llama.cpp"),
        "gguf": (getattr(args, "text_provider", None), "llama.cpp"),
        "deep_filter_executable": ("deepfilternet", "deepfilternet"),
        "deep_filter_model": ("deepfilternet", "deepfilternet"),
        "vad_model": (getattr(args, "transcription_provider", None), "whisper.cpp"),
    }
    from .providers import get_provider_info
    from .providers.options import resolve_provider_option_paths
    for source, target in path_fields.items():
        raw_value = values.pop(source)
        if not raw_value:
            values[target] = None
            continue
        active_id, fallback_id = path_provider_ids.get(source, (None, None))
        info = get_provider_info(str(active_id or ""))
        if info is None or target not in {option.key for option in info.options}:
            info = get_provider_info(str(fallback_id or ""))
        if info is not None and target in {option.key for option in info.options}:
            values[target] = resolve_provider_option_paths(info, {target: raw_value}, PROJECT_ROOT)[target]
        else:
            values[target] = _project_path(raw_value)
    values["ffmpeg"] = _project_path(values["ffmpeg"]) if "/" in values["ffmpeg"] or "\\" in values["ffmpeg"] else values["ffmpeg"]
    values["ffprobe"] = _project_path(values["ffprobe"]) if "/" in values["ffprobe"] or "\\" in values["ffprobe"] else values["ffprobe"]
    values["media_provider"] = str(values.get("media_provider") or DEFAULT_MEDIA_PROVIDER)
    if values["media_provider"] == "ffmpeg":
        # Historical flags remain aliases for the ffmpeg provider options.
        media_options = provider_options.setdefault("ffmpeg", {})
        if isinstance(media_options, dict):
            media_options["ffmpeg"] = values["ffmpeg"]
            media_options["ffprobe"] = values["ffprobe"]
    values["diarization_num_speakers"] = values.pop("speakers")
    return argparse.Namespace(**values)


def main() -> None:
    # Required by the spawn-based diarization child in frozen (PyInstaller) builds.
    mp.freeze_support()
    args = build_parser().parse_args()
    provider_result = run_provider_command(args, project_root=PROJECT_ROOT)
    if provider_result is not None:
        raise SystemExit(provider_result)
    application_result = run_application_cli_command(args, project_root=PROJECT_ROOT)
    if application_result is not None:
        raise SystemExit(application_result)
    namespace = _args_namespace(args)
    event_token = set_provider_event_callback(
        lambda event: print(f"[{event.provider_id}] {event.message}", flush=True)
    )
    provider_token = set_text_provider(
        getattr(namespace, "text_provider", None),
        (getattr(namespace, "provider_options", {}) or {}).get(getattr(namespace, "text_provider", ""), {}),
    )
    try:
        if args.command == "record":
            namespace.capture_windows = namespace.windows_audio
            namespace.microphone = getattr(args, "microphone", None)
            namespace.output = getattr(args, "output", None)
            audio.record(namespace)
        elif args.command == "transcribe":
            transcription.transcribe(namespace)
        elif args.command == "import":
            from .media.audio_import import import_audio_file
            from .core.sessions import read_metadata, write_metadata
            source = Path(str(args.target)).expanduser().resolve() if args.target else None
            if source is None or not source.is_file():
                raise SystemExit("Indiquez un fichier audio/vidéo existant à importer.")
            if not 0 <= float(args.max_gain_db) <= 30:
                raise SystemExit("--max-gain-db doit être compris entre 0 et 30.")
            imported = import_audio_file(
                source, namespace.directory,
                media_provider=namespace.media_provider,
                media_options=(namespace.provider_options or {}).get(namespace.media_provider, {}),
                ffmpeg=namespace.ffmpeg,
                ffprobe=namespace.ffprobe,
                normalize=bool(args.normalize), max_gain_db=float(args.max_gain_db),
                split_channels=bool(args.split_channels),
            )
            if args.title and args.title.strip():
                metadata = read_metadata(imported)
                metadata["title"] = args.title.strip()[:120]
                metadata["title_source"] = "user"
                write_metadata(imported, metadata)
            namespace.folder = str(imported)
            print(f"Fichier importé dans la séance : {imported}", flush=True)
            if args.import_action == "transcribe":
                transcription.transcribe(namespace)
            elif args.import_action == "process":
                pipeline.process(namespace)
        elif args.command == "summarize":
            minutes.summarize(namespace)
        else:
            pipeline.process(namespace)
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        raise SystemExit(str(exc).strip() or f"Échec : {type(exc).__name__}") from None
    except KeyboardInterrupt:
        raise SystemExit("Traitement interrompu.") from None
    finally:
        reset_text_provider(provider_token)
        reset_provider_event_callback(event_token)


if __name__ == "__main__":
    main()
