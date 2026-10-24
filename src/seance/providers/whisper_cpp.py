"""whisper.cpp transcription adapter."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from ..runtime import acquire_ai_engine, AI_ENGINE_LOCK
from .contracts import ProviderEvent, ProviderInfo, ProviderOption, ProviderOptionChoice, ProviderResourceLink, TranscriptSegment, TranscriptionRequest
from .events import emit_provider_event
from .srt import read_srt


WHISPER_CPP_TRANSLATIONS_EN = {'en': {'Transcription locale via whisper-cli.': 'Local transcription with whisper-cli.',
        'Modèle de transcription': 'Transcription model',
        'Modèle de reconnaissance vocale Whisper déjà téléchargé.': 'Downloaded Whisper speech recognition '
                                                                    'model.',
        'Moteur de transcription': 'Transcription engine',
        'Exécutable whisper-cli fourni avec l’installation.': 'whisper-cli executable included with the '
                                                              'installation.',
        'Recherche de transcription': 'Transcription search',
        'Compare davantage d’hypothèses pour améliorer la transcription, au prix du temps de calcul.': 'Compare '
                                                                                                       'more '
                                                                                                       'hypotheses '
                                                                                                       'to '
                                                                                                       'improve '
                                                                                                       'the '
                                                                                                       'transcript, '
                                                                                                       'at '
                                                                                                       'the '
                                                                                                       'cost '
                                                                                                       'of '
                                                                                                       'processing '
                                                                                                       'time.',
        'Rapide': 'Fast',
        'Équilibrée': 'Balanced',
        'Précise': 'Accurate',
        'Très précise': 'Very accurate',
        'Utiliser OpenVINO': 'Use OpenVINO',
        'Facultatif. Demande un whisper.cpp compilé avec OpenVINO et un modèle d’encodeur OpenVINO converti.': 'Optional. '
                                                                                                               'Requires '
                                                                                                               'whisper.cpp '
                                                                                                               'built '
                                                                                                               'with '
                                                                                                               'OpenVINO '
                                                                                                               'and '
                                                                                                               'a '
                                                                                                               'converted '
                                                                                                               'OpenVINO '
                                                                                                               'encoder '
                                                                                                               'model.',
        'Périphérique OpenVINO': 'OpenVINO device',
        'OpenVINO accélère l’encodeur sur CPU ou GPU Intel.': 'OpenVINO accelerates the encoder on Intel '
                                                              'CPUs or GPUs.',
        'Détection de parole (VAD)': 'Voice activity detection (VAD)',
        "Évite de transcrire de longs silences et réduit les hallucinations. Auto l'active uniquement si le modèle local existe.": 'Avoids '
                                                                                                                                   'transcribing '
                                                                                                                                   'long '
                                                                                                                                   'silences '
                                                                                                                                   'and '
                                                                                                                                   'reduces '
                                                                                                                                   'hallucinations. '
                                                                                                                                   'Auto '
                                                                                                                                   'mode '
                                                                                                                                   'enables '
                                                                                                                                   'it '
                                                                                                                                   'only '
                                                                                                                                   'when '
                                                                                                                                   'the '
                                                                                                                                   'local '
                                                                                                                                   'model '
                                                                                                                                   'exists.',
        'Automatique si modèle présent': 'Automatic when model is present',
        'Activée (obligatoire)': 'Enabled (required)',
        'Désactivée': 'Disabled',
        'Modèle VAD Silero': 'Silero VAD model',
        'Modèle VAD pour whisper.cpp, à télécharger séparément.': 'VAD model for whisper.cpp; download '
                                                                  'separately.',
        'Seuil VAD': 'VAD threshold',
        'Augmenter le seuil filtre plus de bruit, mais peut couper des voix faibles.': 'A higher threshold '
                                                                                       'filters more noise '
                                                                                       'but may cut quiet '
                                                                                       'speech.',
        'Binaires whisper.cpp': 'whisper.cpp binaries',
        'Téléchargez la version correspondant à votre système puis configurez whisper-cli.': 'Download the '
                                                                                             'version for '
                                                                                             'your operating '
                                                                                             'system and '
                                                                                             'configure '
                                                                                             'whisper-cli.',
        'Modèles Whisper GGML': 'Whisper GGML models',
        'Téléchargez un fichier modèle .bin et renseignez son chemin ci-dessous.': 'Download a .bin model '
                                                                                   'file and enter its path '
                                                                                   'below.',
        'Modèles VAD Silero': 'Silero VAD models',
        'Téléchargement direct du fichier VAD Silero attendu par la configuration par défaut.': 'Direct '
                                                                                                'download of '
                                                                                                'the Silero '
                                                                                                'VAD file '
                                                                                                'expected by '
                                                                                                'the default '
                                                                                                'configuration.',
        'Documentation whisper.cpp': 'whisper.cpp documentation'}}


WHISPER_CPP_INFO = ProviderInfo(
    id="whisper.cpp",
    name="Whisper.cpp",
    task="transcription",
    description="Transcription locale via whisper-cli.",
    execution="system_executable",
    capabilities=("timestamps", "srt", "language-selection", "vad", "cancellation"),
    setup_links=(
        ProviderResourceLink("Binaires whisper.cpp", "https://github.com/ggml-org/whisper.cpp/releases", "binary", "Téléchargez la version correspondant à votre système puis configurez whisper-cli."),
        ProviderResourceLink("Modèles Whisper GGML", "https://huggingface.co/ggerganov/whisper.cpp/tree/main", "model", "Téléchargez un fichier modèle .bin et renseignez son chemin ci-dessous."),
        ProviderResourceLink("Modèles VAD Silero", "https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin", "model", "Téléchargement direct du fichier VAD Silero attendu par la configuration par défaut."),
        ProviderResourceLink("Documentation whisper.cpp", "https://github.com/ggml-org/whisper.cpp", "documentation"),
    ),
    options=(
        ProviderOption(
            key="model", label="Modèle de transcription", type="path",
            default="models/asr/model.bin",
            description="Modèle de reconnaissance vocale Whisper déjà téléchargé.",
            required=True,
        ),
        ProviderOption(
            key="whisper_cli", label="Moteur de transcription", type="path",
            default="bin/asr/whisper-cli.exe",
            description="Exécutable whisper-cli fourni avec l’installation.",
            required=True, advanced=True,
        ),
        ProviderOption(
            key="beam_size", label="Recherche de transcription", type="select",
            default="5", description="Compare davantage d’hypothèses pour améliorer la transcription, au prix du temps de calcul.",
            choices=(ProviderOptionChoice("1", "Rapide"), ProviderOptionChoice("3", "Équilibrée"),
                     ProviderOptionChoice("5", "Précise"), ProviderOptionChoice("8", "Très précise")),
            advanced=True, per_job=True,
        ),
        ProviderOption(
            key="openvino_enabled", label="Utiliser OpenVINO", type="boolean",
            default=False,
            description="Facultatif. Demande un whisper.cpp compilé avec OpenVINO et un modèle d’encodeur OpenVINO converti.",
            advanced=True,
        ),
        ProviderOption(
            key="openvino_device", label="Périphérique OpenVINO", type="select",
            default="CPU", description="OpenVINO accélère l’encodeur sur CPU ou GPU Intel.",
            choices=(ProviderOptionChoice("CPU", "CPU"), ProviderOptionChoice("GPU", "GPU")),
            advanced=True, depends_on="openvino_enabled",
        ),
        ProviderOption(
            key="vad_mode", label="Détection de parole (VAD)", type="select",
            default="auto",
            description="Évite de transcrire de longs silences et réduit les hallucinations. Auto l'active uniquement si le modèle local existe.",
            choices=(ProviderOptionChoice("auto", "Automatique si modèle présent"),
                     ProviderOptionChoice("on", "Activée (obligatoire)"),
                     ProviderOptionChoice("off", "Désactivée")),
            advanced=True, per_job=True,
        ),
        ProviderOption(
            key="vad_model", label="Modèle VAD Silero", type="path",
            default="models/asr/ggml-silero-v6.2.0.bin",
            description="Modèle VAD pour whisper.cpp, à télécharger séparément.",
            advanced=True,
        ),
        ProviderOption(
            key="vad_threshold", label="Seuil VAD", type="number", default=0.5,
            minimum=0.05, maximum=0.95, step=0.05,
            description="Augmenter le seuil filtre plus de bruit, mais peut couper des voix faibles.",
            advanced=True,
        ),
    ),

    translations=WHISPER_CPP_TRANSLATIONS_EN,
)


class WhisperCppTranscriptionProvider:
    """Run whisper.cpp and translate its SRT output into Glimio segments."""

    info = WHISPER_CPP_INFO

    def __init__(
        self,
        executable: str | Path,
        *,
        cancel_event: threading.Event | None = None,
        options: dict | None = None,
    ) -> None:
        self.options = options or {}
        self.executable = Path(self.options.get("whisper_cli", executable)).expanduser().resolve()
        self.cancel_event = cancel_event
        self.openvino_enabled = bool(self.options.get("openvino_enabled", False))
        self.openvino_device = self.options.get("openvino_device", "CPU")
        self.beam_size = int(self.options.get("beam_size", 5))
        self.vad_mode = str(self.options.get("vad_mode", "auto")).strip().lower()
        self.vad_model = Path(self.options.get("vad_model", "models/asr/ggml-silero-v6.2.0.bin")).expanduser()
        self.vad_threshold = float(self.options.get("vad_threshold", 0.5))

    def transcribe(
        self,
        request: TranscriptionRequest,
        *,
        on_event=None,
    ) -> list[TranscriptSegment]:
        audio = Path(request.audio_path).expanduser().resolve()
        model = Path(self.options.get("model", request.model_path)).expanduser().resolve()
        output_base = Path(request.output_prefix).expanduser().resolve()
        output_base.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.executable), "-m", str(model), "-f", str(audio),
            "-l", request.language, "-osrt", "-of", str(output_base),
            "-t", str(request.threads), "-bs", str(self.beam_size), "-mc", "512",
        ]
        if self.openvino_enabled:
            command.extend(["--ov-e-device", self.openvino_device])

        if self.vad_mode not in {"auto", "on", "off"}:
            raise SystemExit("Le réglage VAD doit être auto, on ou off.")
        if not 0.05 <= self.vad_threshold <= 0.95:
            raise SystemExit("Le seuil VAD doit être compris entre 0,05 et 0,95.")
        if self.vad_mode != "off":
            if self.vad_model.is_file():
                command.extend([
                    "--vad", "--vad-model", str(self.vad_model.resolve()),
                    "--vad-threshold", str(self.vad_threshold),
                    "--vad-min-speech-duration-ms", "250",
                    "--vad-min-silence-duration-ms", "150",
                    "--vad-speech-pad-ms", "100",
                    "--vad-samples-overlap", "0.10",
                ])
            elif self.vad_mode == "on":
                raise SystemExit(
                    f"Modèle VAD introuvable : {self.vad_model}. Téléchargez le modèle Silero de whisper.cpp "
                    "ou réglez la détection de parole sur Automatique/Désactivée."
                )

        emit_provider_event(ProviderEvent(
            provider_id=self.info.id, task="transcription", stage="starting",
            message=f"Transcription · {audio.name} · démarrage du moteur…",
            details={"audio_file": audio.name},
        ), on_event)
        if not self.executable.is_file():
            raise SystemExit(f"Whisper executable not found: {self.executable}")
        if not model.is_file():
            raise SystemExit(f"Whisper model not found: {model}")
        if request.threads < 1:
            raise SystemExit("--threads must be at least 1.")
        if not acquire_ai_engine(self.cancel_event):
            raise SystemExit("Traitement annulé avant le démarrage de Whisper.")

        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(
                command, cwd=str(audio.parent), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=False,
            )
            while True:
                if self.cancel_event is not None and self.cancel_event.is_set():
                    process.terminate()
                    try:
                        process.communicate(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()
                    raise SystemExit("Traitement annulé.")
                try:
                    stdout, stderr = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except OSError as exc:
            raise SystemExit(f"Could not run {self.executable}: {exc}") from exc
        finally:
            AI_ENGINE_LOCK.release()

        if process.returncode != 0:
            detail = (stderr or stdout or "Erreur sans détail".encode("utf-8")).decode("utf-8", errors="replace")
            raise SystemExit(f"whisper.cpp a échoué (code {process.returncode}).\n{detail[-12000:]}")
        srt_path = output_base.with_suffix(".srt")
        segments = [TranscriptSegment(start, end, text) for start, end, text in read_srt(srt_path)]
        emit_provider_event(ProviderEvent(
            provider_id=self.info.id, task="transcription", stage="completed",
            message=f"Transcription · {audio.name} · {len(segments)} segment(s) reconnus",
            details={"audio_file": audio.name, "segments": len(segments)},
        ), on_event)
        return segments
