"""Media toolchain providers: probe, track extraction and chunk extraction.

The FFmpeg adapter keeps the historical command lines and diagnostics. The
native adapter handles PCM WAV with the standard library only, so a session can
be transcribed without any external executable. Neither adapter imports the
media or processing packages: use cases own the business rules (normalization,
fallback policy, session layout).
"""
from __future__ import annotations

import array
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..executables import resolve_command, resolve_ffprobe
from .plugins import plugins_for_task
from .contracts import (
    AudioChunkRequest, AudioStreamInfo, AudioTrackRequest, MediaCancelled,
    MediaToolchainError, MediaToolchainUnavailable, ProviderInfo, ProviderOption,
    ProviderResourceLink,
)


FFMPEG_TRANSLATIONS_EN = {'en': {'Décodage et conversion des formats audio/vidéo importés.': 'Decoding and conversion of imported '
                                                                    'audio and video formats.',
        'Commande FFmpeg': 'FFmpeg command',
        'Commande ou chemin vers FFmpeg.': 'Command or path to FFmpeg.',
        'Commande ffprobe': 'ffprobe command',
        'Commande ou chemin vers ffprobe. Laissez « ffprobe » pour le détecter à côté de FFmpeg ou dans le PATH.': 'Command or path to ffprobe. Leave “ffprobe” to detect it beside FFmpeg or on the PATH.',
        'Télécharger FFmpeg': 'Download FFmpeg',
        'Installez FFmpeg et vérifiez que ffmpeg et ffprobe sont accessibles.': 'Install FFmpeg and make '
                                                                                'sure ffmpeg and ffprobe are '
                                                                                'available.',
        'Guide Windows': 'Windows guide',
        'Builds Windows populaires ; vérifiez leur provenance et leurs conditions.': 'Popular Windows '
                                                                                     'builds; check their '
                                                                                     'provenance and terms.',
        'Documentation FFmpeg': 'FFmpeg documentation'}}

NATIVE_TRANSLATIONS_EN = {'en': {
    'Extraction et découpage de fichiers WAV PCM sans outil externe.': 'Extraction and chunking of PCM WAV files without an external tool.',
    'Extraction de pistes et découpage audio WAV PCM.': 'PCM WAV track extraction and audio chunking.',
    'Aucun exécutable externe : format WAV PCM 16 bits à 16 kHz requis pour l’import.': 'No external executable: WAV PCM 16-bit at 16 kHz is required for import.',
}}


FFMPEG_MEDIA_INFO = ProviderInfo(
    id="ffmpeg", name="FFmpeg", task="media",
    description="Décodage et conversion des formats audio/vidéo importés.",
    execution="system_executable",
    capabilities=("audio-video-import", "audio-chunking"),
    setup_links=(
        ProviderResourceLink("Télécharger FFmpeg", "https://ffmpeg.org/download.html", "binary", "Installez FFmpeg et vérifiez que ffmpeg et ffprobe sont accessibles."),
        ProviderResourceLink("Guide Windows", "https://www.gyan.dev/ffmpeg/builds/", "binary", "Builds Windows populaires ; vérifiez leur provenance et leurs conditions."),
        ProviderResourceLink("Documentation FFmpeg", "https://ffmpeg.org/documentation.html", "documentation"),
    ),
    options=(ProviderOption(
        key="ffmpeg", label="Commande FFmpeg", type="text", default="ffmpeg",
        description="Commande ou chemin vers FFmpeg.", required=True, advanced=True,
    ), ProviderOption(
        key="ffprobe", label="Commande ffprobe", type="text", default="ffprobe",
        description="Commande ou chemin vers ffprobe. Laissez « ffprobe » pour le détecter à côté de FFmpeg ou dans le PATH.",
        required=True, advanced=True,
    )),

    translations=FFMPEG_TRANSLATIONS_EN,
)

NATIVE_MEDIA_INFO = ProviderInfo(
    id="native", name="Natif · WAV PCM", task="media",
    description="Extraction et découpage de fichiers WAV PCM sans outil externe.",
    execution="embedded",
    capabilities=("wav-pcm16", "audio-chunking"),
    requires=(),
    options=(),

    translations=NATIVE_TRANSLATIONS_EN,
)


def _options(options: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(options or {})


def _resolved_path(value: str | Path | None, root: Path) -> Path | None:
    if value is None or not str(value).strip():
        return None
    path = Path(str(value)).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _has_path_separator(value: str) -> bool:
    return "/" in value or "\\" in value


def _ffmpeg_settings(options: Mapping[str, Any] | None) -> tuple[str, str]:
    values = _options(options)
    ffmpeg = str(values.get("ffmpeg", "ffmpeg") or "ffmpeg").strip() or "ffmpeg"
    ffprobe = str(values.get("ffprobe", "ffprobe") or "ffprobe").strip() or "ffprobe"
    return ffmpeg, ffprobe


def _ffmpeg_resolved(
    options: Mapping[str, Any] | None, root: Path,
) -> tuple[str | None, str | None, str, str]:
    """Return resolved FFmpeg/ffprobe executables plus the configured settings."""
    ffmpeg_setting, ffprobe_setting = _ffmpeg_settings(options)
    ffmpeg_candidate = _resolved_path(ffmpeg_setting, root) if _has_path_separator(ffmpeg_setting) else None
    ffmpeg_found: str | None = str(ffmpeg_candidate) if ffmpeg_candidate is not None else resolve_command(ffmpeg_setting, default="ffmpeg")
    ffprobe_candidate = _resolved_path(ffprobe_setting, root) if _has_path_separator(ffprobe_setting) else None
    ffprobe_found = resolve_ffprobe(
        ffmpeg_found if ffmpeg_found is not None else ffmpeg_setting,
        str(ffprobe_candidate) if ffprobe_candidate is not None else ffprobe_setting,
    )
    return ffmpeg_found, ffprobe_found, ffmpeg_setting, ffprobe_setting


def _ffmpeg_status(
    options: Mapping[str, Any] | None, root: Path,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    ffmpeg_found, ffprobe_found, ffmpeg_setting, ffprobe_setting = _ffmpeg_resolved(options, root)
    missing: list[str] = []
    if not ffmpeg_found or not Path(ffmpeg_found).is_file():
        missing.append(ffmpeg_setting)
    if not ffprobe_found or not Path(ffprobe_found).is_file():
        missing.append(ffprobe_setting)
    details = {
        "executable": str(ffmpeg_found) if ffmpeg_found else ffmpeg_setting,
        "ffprobe_executable": str(ffprobe_found) if ffprobe_found else None,
    }
    return tuple(missing), details


def media_toolchain_status(
    info: ProviderInfo,
    options: Mapping[str, Any] | None = None,
    project_root: str | Path = ".",
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Return missing resources and diagnostics for one media provider."""
    root = Path(project_root).expanduser().resolve()
    if info.id == "ffmpeg":
        return _ffmpeg_status(options, root)
    from .plugins import check_plugin_readiness, get_provider_plugin
    plugin = get_provider_plugin(info.id)
    if plugin is not None and plugin.info is info and plugin.readiness is not None:
        return check_plugin_readiness(plugin, _options(options), root)
    if info.id == "native":
        # The native backend depends only on the standard library.
        return (), {}
    # Validate required path/text fields generically for third-party providers.
    missing: list[str] = []
    details: dict[str, Any] = {}
    values = _options(options)
    for option in info.options:
        value = values.get(option.key, option.default)
        if option.type == "path":
            raw_text = str(value).strip() if value is not None else ""
            raw_path = Path(raw_text).expanduser() if raw_text else None
            is_bare_executable = (
                option.path_role == "executable"
                and raw_path is not None
                and not raw_path.is_absolute()
                and not _has_path_separator(raw_text)
            )
            if is_bare_executable:
                executable = shutil.which(raw_text)
                details[option.key] = executable or raw_text
                if option.required and executable is None:
                    missing.append(raw_text or option.label)
            else:
                path = _resolved_path(value, root)
                details[option.key] = str(path) if path else None
                if option.required and (path is None or not path.is_file()):
                    missing.append(str(path or option.label))
        elif option.required and (value is None or (isinstance(value, str) and not value.strip())):
            missing.append(option.label)
    return tuple(missing), details


def media_toolchain_readiness(
    info: ProviderInfo,
    options: Mapping[str, Any] | None = None,
    project_root: str | Path = ".",
) -> tuple[bool, tuple[str, ...]]:
    missing, _details = media_toolchain_status(info, options, project_root)
    return not missing, missing


def ensure_media_toolchain_ready(
    info: ProviderInfo,
    options: Mapping[str, Any] | None = None,
    project_root: str | Path = ".",
) -> None:
    """Raise an actionable domain error before a session directory is created."""
    if info.id == "ffmpeg":
        root = Path(project_root).expanduser().resolve()
        ffmpeg_found, ffprobe_found, ffmpeg_setting, ffprobe_setting = _ffmpeg_resolved(options, root)
        if not ffmpeg_found or not Path(ffmpeg_found).is_file():
            raise MediaToolchainUnavailable(
                f"FFmpeg introuvable : « {ffmpeg_setting} ». Installez FFmpeg ou configurez son chemin "
                "dans les paramètres (provider FFmpeg), puis réessayez."
            )
        if not ffprobe_found or not Path(ffprobe_found).is_file():
            raise MediaToolchainUnavailable(
                f"ffprobe introuvable : « {ffprobe_setting} ». Installez ffprobe ou configurez son chemin "
                "dans les paramètres (provider FFmpeg) ; ffprobe doit provenir de la même distribution que FFmpeg."
            )
        return
    ready, missing = media_toolchain_readiness(info, options, project_root)
    if not ready:
        raise MediaToolchainUnavailable(
            f"Le provider média {info.id} n’est pas disponible : {', '.join(missing)}."
        )


def _run_ffmpeg(
    command: list[str],
    *,
    cwd: Path | None = None,
    cancel_event: Any = None,
    cancel_message: str,
    launch_message: str,
) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg while polling cancellation, preserving the historical loop."""
    if cancel_event is not None and cancel_event.is_set():
        raise MediaCancelled(cancel_message)
    try:
        process = subprocess.Popen(
            command, cwd=str(cwd) if cwd is not None else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        raise MediaToolchainUnavailable(f"{launch_message} ({exc})") from exc
    while True:
        if cancel_event is not None and cancel_event.is_set():
            process.terminate()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise MediaCancelled(cancel_message)
        try:
            stdout, stderr = process.communicate(timeout=0.25)
            return subprocess.CompletedProcess(command, process.returncode or 0, stdout, stderr)
        except subprocess.TimeoutExpired:
            continue


class FFmpegMediaToolchain:
    """FFmpeg/ffprobe adapter; commands are resolved only when the provider runs."""

    info = FFMPEG_MEDIA_INFO

    def __init__(self, options: Mapping[str, Any] | None = None) -> None:
        self.options = _options(options)

    def _ffmpeg_executable(self) -> str:
        setting, _ = _ffmpeg_settings(self.options)
        executable = resolve_command(setting, default="ffmpeg")
        if not executable:
            raise MediaToolchainUnavailable(
                f"FFmpeg introuvable : « {setting} ». Installez FFmpeg ou configurez son chemin "
                "dans les paramètres (provider FFmpeg), puis réessayez."
            )
        return executable

    def _probe_executable(self, ffmpeg: str) -> str:
        _, setting = _ffmpeg_settings(self.options)
        executable = resolve_ffprobe(ffmpeg, setting)
        if not executable:
            raise MediaToolchainUnavailable(
                "ffprobe est requis pour inspecter les pistes audio sans en perdre. "
                f"La commande configurée est « {setting} ». Installez ffprobe depuis la même "
                "distribution que FFmpeg ou configurez son chemin, puis réessayez."
            )
        return executable

    def probe_audio_streams(self, source: str) -> list[AudioStreamInfo]:
        ffmpeg = self._ffmpeg_executable()
        executable = self._probe_executable(ffmpeg)
        command = [
            executable, "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index,channels", "-of", "json", str(source),
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=20,
            )
            if result.returncode != 0:
                detail = (result.stderr or "aucun détail").strip()
                raise MediaToolchainError(f"Impossible d'inspecter les flux audio avec ffprobe : {detail[-2000:]}")
            payload = json.loads(result.stdout or "{}")
            streams = payload.get("streams", []) if isinstance(payload, dict) else []
            discovered = [
                AudioStreamInfo(
                    stream_index=int(item.get("index", index)),
                    audio_index=index,
                    channels=max(1, int(item.get("channels") or 1)),
                )
                for index, item in enumerate(streams) if isinstance(item, dict)
            ]
            if not discovered:
                raise MediaToolchainError("Aucun flux audio exploitable n'a été trouvé dans ce fichier.")
            return discovered
        except MediaToolchainError:
            raise
        except (OSError, ValueError, TypeError, subprocess.SubprocessError) as exc:
            raise MediaToolchainError(
                f"Impossible d'inspecter le fichier pour conserver toutes ses pistes audio : {exc}"
            ) from exc

    def extract_track(self, request: AudioTrackRequest) -> None:
        executable = self._ffmpeg_executable()
        source = Path(request.source).expanduser().resolve()
        output = Path(request.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [
            executable, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vn", "-map", f"0:a:{int(request.audio_index)}",
        ]
        if request.channel is not None:
            command.extend(["-af", f"pan=mono|c0=c{int(request.channel)}"])
        command.extend(["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)])
        result = _run_ffmpeg(
            command, cancel_event=request.cancel_event,
            cancel_message="Import annulé.",
            launch_message=f"Impossible de lancer FFmpeg pour la piste {int(request.audio_index) + 1}",
        )
        if result.returncode != 0 or not output.is_file() or output.stat().st_size <= 44:
            detail = (result.stderr or result.stdout or "aucune piste audio exploitable").strip()
            label = f"flux {int(request.audio_index) + 1}"
            if request.channel is not None:
                label += f", canal {int(request.channel) + 1}"
            raise MediaToolchainError(f"Impossible de convertir le {label} avec FFmpeg : {detail[-3000:]}")

    def extract_chunk(self, request: AudioChunkRequest) -> None:
        executable = self._ffmpeg_executable()
        source = Path(request.source).expanduser().resolve()
        target = Path(request.target).expanduser()
        duration = max(0.1, float(request.end_seconds) - float(request.start_seconds))
        command = [
            executable, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{float(request.start_seconds):.3f}",
            "-i", str(source), "-t", f"{duration:.3f}", "-c", "copy", str(target),
        ]
        result = _run_ffmpeg(
            command, cwd=source.parent, cancel_event=request.cancel_event,
            cancel_message="Traitement annulé.",
            launch_message="FFmpeg n'a pas pu être lancé",
        )
        if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            detail = (result.stderr or result.stdout or str(result.returncode)).strip()[-2000:]
            raise MediaToolchainError(f"Could not extract audio chunk from {source.name}: {detail}")


_NATIVE_FORMAT_MESSAGE = (
    "Le provider média natif ne prend en charge que les fichiers WAV PCM 16 bits à 16 kHz. "
    "Convertissez « {name} » dans ce format ou choisissez un autre provider média."
)


def _pcm16_samples(payload: bytes) -> array.array:
    samples = array.array("h")
    samples.frombytes(payload)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def _pcm16_bytes(samples: array.array) -> bytes:
    if sys.byteorder == "big":
        samples = array.array("h", samples)
        samples.byteswap()
    return samples.tobytes()


def _read_wav_header(path: Path) -> tuple[int, int, int, str]:
    try:
        with wave.open(str(path), "rb") as reader:
            return (
                reader.getnchannels(),
                reader.getsampwidth(),
                reader.getframerate(),
                reader.getcomptype(),
            )
    except (OSError, wave.Error, EOFError) as exc:
        raise MediaToolchainUnavailable(_NATIVE_FORMAT_MESSAGE.format(name=path.name)) from exc


def _require_pcm16_16k(path: Path) -> int:
    channels, sample_width, rate, compression = _read_wav_header(path)
    if compression != "NONE" or sample_width != 2 or rate != 16000 or channels < 1:
        raise MediaToolchainUnavailable(_NATIVE_FORMAT_MESSAGE.format(name=path.name))
    return channels


def _downmix(samples: array.array, channels: int) -> array.array:
    """Average interleaved PCM16 frames to mono in bounded numpy blocks.

    The historical Python loop is equivalent but far too slow on long recordings.
    Accumulating in int32 avoids int16 overflow; clipping keeps the same saturation
    behaviour as the sample-by-sample implementation.
    """
    if channels <= 1:
        return samples
    frame_count = len(samples) // channels
    if frame_count <= 0:
        return array.array("h")
    frames = np.frombuffer(samples, dtype=np.int16, count=frame_count * channels)
    mixed = frames.reshape(frame_count, channels).astype(np.int32).sum(axis=1) // channels
    np.clip(mixed, -32768, 32767, out=mixed)
    return array.array("h", mixed.astype(np.int16).tobytes())


class NativeMediaToolchain:
    """Standard-library WAV backend; no external executable is ever launched."""

    info = NATIVE_MEDIA_INFO

    def __init__(self, options: Mapping[str, Any] | None = None) -> None:
        self.options = _options(options)

    def probe_audio_streams(self, source: str) -> list[AudioStreamInfo]:
        channels = _require_pcm16_16k(Path(source).expanduser().resolve())
        return [AudioStreamInfo(stream_index=0, audio_index=0, channels=channels)]

    def extract_track(self, request: AudioTrackRequest) -> None:
        source = Path(request.source).expanduser().resolve()
        target = Path(request.output).expanduser()
        channels = _require_pcm16_16k(source)
        channel = request.channel
        if channel is not None and not 0 <= int(channel) < channels:
            raise MediaToolchainError(
                f"Le canal {int(channel) + 1} n'existe pas dans « {source.name} » ({channels} canal/canaux)."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        block_frames = 16000
        cancelled = False
        with wave.open(str(source), "rb") as reader, wave.open(str(target), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(16000)
            while True:
                if request.cancel_event is not None and request.cancel_event.is_set():
                    cancelled = True
                    break
                payload = reader.readframes(block_frames)
                if not payload:
                    break
                samples = _pcm16_samples(payload)
                if channel is not None:
                    converted = samples[int(channel)::channels]
                elif channels == 1:
                    converted = samples
                else:
                    converted = _downmix(samples, channels)
                writer.writeframes(_pcm16_bytes(converted))
        if cancelled:
            target.unlink(missing_ok=True)
            raise MediaCancelled("Import annulé.")

    def extract_chunk(self, request: AudioChunkRequest) -> None:
        source = Path(request.source).expanduser().resolve()
        target = Path(request.target).expanduser()
        if request.cancel_event is not None and request.cancel_event.is_set():
            raise MediaCancelled("Traitement annulé.")
        try:
            with wave.open(str(source), "rb") as reader:
                rate = reader.getframerate()
                if rate <= 0:
                    raise MediaToolchainUnavailable(
                        f"Le provider média natif ne peut pas découper « {source.name} » : taux d'échantillonnage invalide."
                    )
                channels = reader.getnchannels()
                sample_width = reader.getsampwidth()
                total_frames = reader.getnframes()
                start_frame = min(total_frames, max(0, int(float(request.start_seconds) * rate)))
                end_frame = min(total_frames, max(start_frame, int(float(request.end_seconds) * rate)))
                # Match the FFmpeg path, which always extracts at least 0.1 s when possible.
                minimum_frames = max(1, int(round(0.1 * rate)))
                end_frame = min(total_frames, max(end_frame, start_frame + minimum_frames))
                frame_count = max(0, end_frame - start_frame)
                reader.setpos(start_frame)
                data = reader.readframes(frame_count)
                if request.cancel_event is not None and request.cancel_event.is_set():
                    target.unlink(missing_ok=True)
                    raise MediaCancelled("Traitement annulé.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(target), "wb") as writer:
                    writer.setparams((channels, sample_width, rate, frame_count, "NONE", "not compressed"))
                    writer.writeframes(data)
            if not target.is_file() or target.stat().st_size == 0:
                raise MediaToolchainError(f"Le découpage natif n'a produit aucun WAV exploitable : {target}")
        except MediaToolchainError:
            raise
        except (OSError, wave.Error, EOFError) as exc:
            target.unlink(missing_ok=True)
            raise MediaToolchainUnavailable(_NATIVE_FORMAT_MESSAGE.format(name=source.name)) from exc


_BUILTIN_MEDIA_PROVIDER_FACTORIES = {
    "ffmpeg": FFmpegMediaToolchain,
    "native": NativeMediaToolchain,
}
_MEDIA_PLUGIN_FACTORIES = {
    plugin.info.id: plugin.factory
    for plugin in plugins_for_task("media")
    if plugin.info.id not in _BUILTIN_MEDIA_PROVIDER_FACTORIES
}
MEDIA_PROVIDER_FACTORIES = {**_BUILTIN_MEDIA_PROVIDER_FACTORIES, **_MEDIA_PLUGIN_FACTORIES}
MEDIA_PROVIDER_IDS = tuple(MEDIA_PROVIDER_FACTORIES)
DEFAULT_MEDIA_PROVIDER = "ffmpeg"


def media_toolchain_provider_infos() -> tuple[ProviderInfo, ...]:
    builtins = (FFMPEG_MEDIA_INFO, NATIVE_MEDIA_INFO)
    return (*builtins, *(plugin.info for plugin in plugins_for_task("media") if plugin.info.id not in {item.id for item in builtins}))


def create_media_provider(provider_id: str, options: Mapping[str, Any] | None = None):
    try:
        factory = MEDIA_PROVIDER_FACTORIES[provider_id]
    except KeyError as exc:
        raise ValueError(f"Provider média inconnu : {provider_id}") from exc
    return factory(_options(options))
