"""whisper.cpp transcription adapter."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from ..runtime import acquire_ai_engine, AI_ENGINE_LOCK
from .contracts import ProviderEvent, ProviderInfo, TranscriptSegment, TranscriptionRequest
from .events import emit_provider_event
from .srt import read_srt


WHISPER_CPP_INFO = ProviderInfo(
    id="whisper.cpp",
    name="Whisper.cpp",
    task="transcription",
    description="Transcription locale via whisper-cli.",
    execution="system_executable",
    capabilities=("timestamps", "srt", "language-selection", "cancellation"),
)


class WhisperCppTranscriptionProvider:
    """Run whisper.cpp and translate its SRT output into Glimio segments."""

    info = WHISPER_CPP_INFO

    def __init__(
        self,
        executable: str | Path,
        *,
        cancel_event: threading.Event | None = None,
        openvino_device: str | None = None,
    ) -> None:
        self.executable = Path(executable).expanduser().resolve()
        self.cancel_event = cancel_event
        self.openvino_device = openvino_device

    def transcribe(
        self,
        request: TranscriptionRequest,
        *,
        on_event=None,
    ) -> list[TranscriptSegment]:
        audio = Path(request.audio_path).expanduser().resolve()
        model = Path(request.model_path).expanduser().resolve()
        output_base = Path(request.output_prefix).expanduser().resolve()
        output_base.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.executable), "-m", str(model), "-f", str(audio),
            "-l", request.language, "-osrt", "-of", str(output_base),
            "-t", str(request.threads), "-bs", "5", "-mc", "512",
        ]
        if self.openvino_device:
            command.extend(["--ov-e-device", self.openvino_device])

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
