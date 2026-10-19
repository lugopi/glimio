"""Command-line entry point for local Glimio session processing."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import __version__, audio, minutes, pipeline, transcription
from web.project_paths import discover_project_root


PROJECT_ROOT = discover_project_root(package_file=__file__)
DEFAULT_THREADS = max(1, (os.cpu_count() or 4) // 2)
VALID_FORMATS = ("auto", "summary", "daily", "technical", "formal", "brainstorm")

APP_VERSION = __version__


def _project_path(value: str) -> str:
    path = Path(value).expanduser()
    return str(path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve())


def _add_processing_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", nargs="?", help="Fichier audio/vidéo ou dossier d’une séance (par défaut : dernière séance admissible).")
    parser.add_argument("--directory", default=str(PROJECT_ROOT / "seances"), help="Dossier des séances (défaut : seances/).")
    parser.add_argument("--whisper-cli", default="bin/asr/whisper-cli.exe", help="Chemin vers whisper-cli.")
    parser.add_argument("--model", default="models/asr/model.bin", help="Chemin vers le modèle Whisper.")
    parser.add_argument("--language", default="auto", help="Langue de transcription (ex. fr, en ou auto).")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS, help="Nombre de threads CPU pour Whisper.")
    parser.add_argument("--openvino-device", choices=("CPU", "GPU", "NPU"), default=None)
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Commande ou chemin vers FFmpeg.")
    parser.add_argument("--diarize", action="store_true", help="Activer la diarisation (requiert l’édition avec diarisation et ses modèles).")
    parser.add_argument("--segmentation-model", default="models/diarization/segmentation/segmentation.onnx")
    parser.add_argument("--embedding-model", default="models/diarization/embedding/embedding.onnx")
    parser.add_argument("--speakers", type=int, default=-1, help="Nombre d’interlocuteurs, -1 pour automatique.")
    parser.add_argument("--diarization-threshold", type=float, default=0.5)
    parser.add_argument("--llama-completion", default="bin/llm/llama-completion.exe", help="Chemin vers llama-completion.")
    parser.add_argument("--gguf", default="models/llm/model.gguf", help="Chemin vers le modèle GGUF.")
    parser.add_argument("--context", type=int, default=16384)
    parser.add_argument("--max-tokens", type=int, default=6000)
    parser.add_argument("--analysis-tokens", type=int, default=3500)
    parser.add_argument("--analysis-retries", type=int, default=3)
    parser.add_argument("--analysis-max-splits", type=int, default=6)
    parser.add_argument("--format", choices=VALID_FORMATS, default="auto", help="Format de compte rendu.")
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

    return parser


def _args_namespace(args: argparse.Namespace) -> argparse.Namespace:
    values = vars(args).copy()
    values["folder"] = values.pop("target")
    values["directory"] = _project_path(values["directory"])
    path_fields = {
        "whisper_cli": "whisper_cli",
        "model": "model",
        "segmentation_model": "diarization_segmentation_model",
        "embedding_model": "diarization_embedding_model",
        "llama_completion": "llama_completion",
        "gguf": "gguf",
    }
    for source, target in path_fields.items():
        values[target] = _project_path(values.pop(source))
    values["ffmpeg"] = _project_path(values["ffmpeg"]) if "/" in values["ffmpeg"] or "\\" in values["ffmpeg"] else values["ffmpeg"]
    values["diarization_num_speakers"] = values.pop("speakers")
    return argparse.Namespace(**values)


def main() -> None:
    args = build_parser().parse_args()
    namespace = _args_namespace(args)
    try:
        if args.command == "record":
            namespace.capture_windows = namespace.windows_audio
            namespace.microphone = getattr(args, "microphone", None)
            namespace.output = getattr(args, "output", None)
            audio.record(namespace)
        elif args.command == "transcribe":
            transcription.transcribe(namespace)
        elif args.command == "summarize":
            minutes.summarize(namespace)
        else:
            pipeline.process(namespace)
    except KeyboardInterrupt:
        raise SystemExit("Traitement interrompu.") from None


if __name__ == "__main__":
    main()
