from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import threading
import wave
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np

from ..common import log
from ..layout import ensure_session_layout, metadata_output_path

SAMPLE_RATE = 16_000
CHUNK_SECONDS = 2
PCM_BITRATE_SAMPLE_RATES = {128: 8_000, 256: 16_000, 384: 24_000, 512: 32_000, 768: 48_000}


def sample_rate_for_bitrate(bitrate_kbps: int) -> int:
    """Map mono 16-bit PCM WAV bitrates to their matching sample rates."""
    try:
        return PCM_BITRATE_SAMPLE_RATES[int(bitrate_kbps)]
    except (KeyError, TypeError, ValueError) as exc:
        allowed = ", ".join(str(value) for value in PCM_BITRATE_SAMPLE_RATES)
        raise ValueError(f"Unsupported PCM bitrate {bitrate_kbps!r}; choose one of {allowed} kbps.") from exc


@contextmanager
def audio_com_apartment() -> Iterator[None]:
    """Initialize COM on the current Windows thread while using SoundCard.

    SoundCard's Windows backend uses WASAPI/COM. Its module-level COM setup happens
    on the import thread, but FastAPI routes and capture workers run on other threads.
    Every such thread must initialize COM independently. On threads already initialized
    with another apartment model, match SoundCard's own behaviour and do not uninitialize
    a COM apartment that this context did not create.
    """
    if os.name != "nt":
        yield
        return

    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    co_initialize_ex = ole32.CoInitializeEx
    co_initialize_ex.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    co_initialize_ex.restype = ctypes.c_long
    co_uninitialize = ole32.CoUninitialize
    co_uninitialize.argtypes = ()
    co_uninitialize.restype = None

    # COINIT_MULTITHREADED matches SoundCard's Windows mediafoundation backend.
    hr = int(co_initialize_ex(None, 0x0)) & 0xFFFFFFFF
    initialized_here = hr in (0x00000000, 0x00000001)  # S_OK / S_FALSE
    if not initialized_here and hr != 0x80010106:  # RPC_E_CHANGED_MODE: already initialized differently
        raise OSError(f"CoInitializeEx failed with HRESULT 0x{hr:08X}")

    try:
        yield
    finally:
        if initialized_here:
            co_uninitialize()


def _soundcard():
    try:
        import soundcard as sc
    except ImportError as exc:
        raise SystemExit(
            "Audio dependency is missing. Install the project with "
            "`python -m pip install -e .`."
        ) from exc
    return sc


def _resolve_named_device(devices: list[Any], requested: str | None, kind: str) -> Any | None:
    """Resolve a UI-selected device without silently taking the first fuzzy match.

    SoundCard exposes display names for the microphone and speaker collections.
    Exact, case-insensitive matching is preferred. A partial match is retained for
    compatibility with older saved preferences only when it identifies one device.
    """
    if not requested:
        return None
    wanted = str(requested).strip().casefold()
    if not wanted:
        return None

    exact = [device for device in devices if str(getattr(device, "name", "")).strip().casefold() == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise SystemExit(
            f"Several {kind} devices have the exact name {requested!r}. "
            "Rename or disconnect duplicate device endpoints, then choose again."
        )

    partial = [device for device in devices if wanted in str(getattr(device, "name", "")).casefold()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        matches = ", ".join(sorted({str(getattr(device, "name", "")) for device in partial}))
        raise SystemExit(
            f"The selected {kind} name {requested!r} matches several devices ({matches}). "
            "Choose the full device name in Glimio."
        )
    return None


def _resolve_device_id(devices: list[Any], requested_id: str | None, requested_name: str | None, kind: str) -> Any | None:
    """Resolve a selected endpoint by its backend ID first, with safe name fallback."""
    wanted_id = str(requested_id or "").strip()
    if wanted_id:
        matches = [device for device in devices if str(getattr(device, "id", "")).strip() == wanted_id]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SystemExit(f"Several {kind} endpoints expose the same device ID {wanted_id!r}.")
        if not requested_name:
            raise SystemExit(f"The selected {kind} device is no longer available. Refresh the device list.")
    if requested_name:
        resolved = _resolve_named_device(devices, requested_name, kind)
        if resolved is None:
            raise SystemExit(f"The selected {kind} device {requested_name!r} is no longer available. Refresh the device list.")
        return resolved
    return None


def list_devices() -> None:
    # Import SoundCard before opening our scoped COM apartment. Its Windows backend
    # initializes COM at module import time and expects that initialization to succeed.
    sc = _soundcard()
    with audio_com_apartment():
        print("Microphones:", flush=True)
        for mic in sc.all_microphones(include_loopback=False):
            print(f"  {mic.name}", flush=True)

        print("\nWindows outputs (loopback):", flush=True)
        for mic in sc.all_microphones(include_loopback=True):
            if getattr(mic, "isloopback", False):
                print(f"  {mic.name}", flush=True)


def _pcm_payload(data: np.ndarray) -> tuple[bytes, int]:
    """Convert one captured float block into mono PCM16 bytes without session-sized copies."""
    audio = np.asarray(data, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, np.newaxis]
    if audio.ndim != 2:
        raise RuntimeError(f"Unexpected audio format: {audio.shape}")
    if audio.shape[1] > 1:
        audio = audio.mean(axis=1, keepdims=True)
    if audio.shape[0] == 0:
        return b"", 0
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    return pcm.tobytes(), int(pcm.shape[0])


def _write_audio_chunk(output: wave.Wave_write, data: np.ndarray) -> int:
    """Write one captured block to an already configured WAV and return its frame count."""
    payload, frame_count = _pcm_payload(data)
    if payload:
        output.writeframesraw(payload)
    return frame_count


def _level_dbfs(amplitude: float) -> float | None:
    """Convert a PCM16 absolute amplitude or RMS value to dBFS."""
    if amplitude <= 0:
        return None
    return 20.0 * math.log10(float(amplitude) / 32768.0)


def _wav_pcm16_stats(path: Path) -> dict[str, float | int | None]:
    """Measure a finalized mono PCM16 WAV in blocks, without loading it all into RAM."""
    peak = 0
    sum_squares = 0.0
    sample_count = 0
    with wave.open(str(path), "rb") as reader:
        if reader.getnchannels() != 1 or reader.getsampwidth() != 2 or reader.getcomptype() != "NONE":
            raise RuntimeError(f"Expected mono PCM16 WAV for level analysis: {path}")
        while True:
            payload = reader.readframes(SAMPLE_RATE * 10)
            if not payload:
                break
            samples = np.frombuffer(payload, dtype="<i2")
            if not samples.size:
                continue
            wide = samples.astype(np.int32)
            peak = max(peak, int(np.max(np.abs(wide))))
            as_float = samples.astype(np.float64)
            sum_squares += float(np.dot(as_float, as_float))
            sample_count += int(samples.size)
    rms = math.sqrt(sum_squares / sample_count) if sample_count else 0.0
    return {
        "frames": sample_count,
        "peak_code": peak,
        "rms_code": rms,
        "peak_dbfs": _level_dbfs(peak),
        "rms_dbfs": _level_dbfs(rms),
    }


def _normalize_wav_peak(
    path: Path,
    *,
    enabled: bool = True,
    target_peak_dbfs: float = -6.0,
    max_gain_db: float = 30.0,
) -> dict[str, Any]:
    """Raise a quiet mono PCM16 WAV toward a target peak without clipping.

    This is a two-pass, block-based operation: measure levels first, then write a
    temporary WAV with linear gain and atomically replace the original. It never
    attenuates a track that is already above the target. Gain is capped to avoid
    excessively boosting near-silence/noise. If disabled, the WAV is measured only.
    """
    if not math.isfinite(target_peak_dbfs) or target_peak_dbfs >= 0:
        raise ValueError("target_peak_dbfs must be a finite value below 0 dBFS")
    if not math.isfinite(max_gain_db) or not 0.0 <= max_gain_db <= 30.0:
        raise ValueError("max_gain_db must be a finite value between 0 and 30 dB")

    before = _wav_pcm16_stats(path)
    peak_db = before["peak_dbfs"]
    rms_db = before["rms_dbfs"]
    info: dict[str, Any] = {
        "enabled": bool(enabled),
        "target_peak_dbfs": target_peak_dbfs,
        "max_gain_db": max_gain_db,
        "gain_applied_db": 0.0,
        "peak_before_dbfs": round(peak_db, 2) if peak_db is not None else None,
        "rms_before_dbfs": round(rms_db, 2) if rms_db is not None else None,
        "peak_after_dbfs": round(peak_db, 2) if peak_db is not None else None,
        "rms_after_dbfs": round(rms_db, 2) if rms_db is not None else None,
        "frames": before["frames"],
        "status": "disabled" if not enabled else "unchanged",
    }
    if not before["frames"]:
        info["status"] = "empty"
        return info
    if peak_db is None:
        info["status"] = "silence"
        return info
    if not enabled:
        return info
    if peak_db >= target_peak_dbfs:
        info["status"] = "already_at_or_above_target"
        return info

    requested_gain_db = target_peak_dbfs - peak_db
    applied_gain_db = min(requested_gain_db, max_gain_db)
    if applied_gain_db <= 0.01:
        info["status"] = "unchanged"
        return info

    gain = 10.0 ** (applied_gain_db / 20.0)
    temp_path = path.with_name(f".{path.name}.normalizing.tmp")
    try:
        with wave.open(str(path), "rb") as reader, wave.open(str(temp_path), "wb") as writer:
            writer.setnchannels(reader.getnchannels())
            writer.setsampwidth(reader.getsampwidth())
            writer.setframerate(reader.getframerate())
            while True:
                payload = reader.readframes(SAMPLE_RATE * 10)
                if not payload:
                    break
                samples = np.frombuffer(payload, dtype="<i2").astype(np.float64)
                adjusted = np.rint(samples * gain)
                adjusted = np.clip(adjusted, -32768, 32767).astype("<i2")
                writer.writeframesraw(adjusted.tobytes())
        temp_path.replace(path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    after = _wav_pcm16_stats(path)
    peak_after = after["peak_dbfs"]
    rms_after = after["rms_dbfs"]
    info.update({
        "gain_applied_db": round(applied_gain_db, 2),
        "peak_after_dbfs": round(peak_after, 2) if peak_after is not None else None,
        "rms_after_dbfs": round(rms_after, 2) if rms_after is not None else None,
        "status": "gain_capped" if requested_gain_db > max_gain_db else "normalized",
    })
    return info


def _write_wav(path: Path, chunks: list[np.ndarray]) -> None:
    """Compatibility helper for callers with in-memory chunks; recording itself streams."""
    if not chunks:
        raise RuntimeError(f"No audio samples received for {path.name}.")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        frames = sum(_write_audio_chunk(output, chunk) for chunk in chunks)
    if frames == 0:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"No audio samples received for {path.name}.")


def _record_impl(
    args: argparse.Namespace,
    *,
    stop_event: threading.Event | None = None,
    on_session_created: Callable[[Path], None] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> None:
    """Record microphone and Windows loopback tracks.

    ``stop_event``, ``on_session_created`` and ``on_status`` are optional hooks for
    the web UI. When omitted, the regular CLI behaviour (Ctrl+C to stop) remains unchanged.
    """
    session_title = str(getattr(args, "title", None) or "").strip() or None
    # PCM WAV bitrate = sample rate * 16 bits * one mono channel. Preserve
    # the historical 16 kHz / 256 kbps default while letting users choose a rate.
    bitrate_kbps = int(getattr(args, "audio_bitrate_kbps", 256) or 256)
    try:
        sample_rate = sample_rate_for_bitrate(bitrate_kbps)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    legacy_capture_microphone = bool(getattr(args, "capture_microphone", True))
    legacy_capture_windows = bool(getattr(args, "capture_windows", True))
    normalize_windows_arg = getattr(args, "normalize_windows", None)
    if normalize_windows_arg is None:
        env_value = os.environ.get("SEANCE_NORMALIZE_WINDOWS", "1").strip().casefold()
        normalize_windows = env_value not in {"0", "false", "no", "off", "disabled"}
    else:
        normalize_windows = bool(normalize_windows_arg)
    max_gain_arg = getattr(args, "normalize_windows_max_gain_db", None)
    if max_gain_arg is None:
        try:
            max_gain_db = float(os.environ.get("SEANCE_NORMALIZE_WINDOWS_MAX_GAIN_DB", "30"))
        except ValueError:
            max_gain_db = 30.0
            log("Invalid SEANCE_NORMALIZE_WINDOWS_MAX_GAIN_DB; using +30 dB.", error=True)
    else:
        max_gain_db = float(max_gain_arg)
    if not math.isfinite(max_gain_db) or not 0.0 <= max_gain_db <= 30.0:
        raise SystemExit("Windows normalization maximum gain must be between 0 and 30 dB.")

    sc = _soundcard()
    all_microphones = sc.all_microphones(include_loopback=False)
    all_speakers = sc.all_speakers()
    loopback_microphones = [mic for mic in sc.all_microphones(include_loopback=True) if getattr(mic, "isloopback", False)]
    requested_sources = getattr(args, "audio_sources", None)
    selected_sources: list[dict[str, Any]] = []

    if requested_sources is not None:
        if not isinstance(requested_sources, (list, tuple)) or not requested_sources:
            raise SystemExit("At least one audio source must be selected.")
        seen_sources: set[tuple[str, str]] = set()
        for raw_source in requested_sources:
            source = raw_source.model_dump() if hasattr(raw_source, "model_dump") else raw_source
            if not isinstance(source, dict):
                raise SystemExit("Invalid audio source selection.")
            kind = str(source.get("kind", "")).strip().casefold()
            if kind not in {"microphone", "output"}:
                raise SystemExit(f"Unsupported audio source type: {kind!r}.")
            device_id = str(source.get("device_id") or "").strip()
            device_name = str(source.get("device_name") or "").strip()
            if kind == "microphone":
                device = _resolve_device_id(all_microphones, device_id, device_name, "microphone") if (device_id or device_name) else sc.default_microphone()
            else:
                speaker = _resolve_device_id(all_speakers, device_id, device_name, "Windows output") if (device_id or device_name) else sc.default_speaker()
                if speaker is None:
                    raise SystemExit("Windows output not found. Refresh the device list and choose another source.")
                speaker_id = str(getattr(speaker, "id", "") or "")
                try:
                    device = _resolve_device_id(loopback_microphones, speaker_id, str(speaker.name), "Windows loopback")
                except SystemExit:
                    raise
                if device is None:
                    raise SystemExit(f"Could not map output {speaker.name!r} to a Windows loopback input.")
                device_id = speaker_id or device_id
                device_name = str(speaker.name)
            if device is None:
                label = "microphone" if kind == "microphone" else "Windows output"
                raise SystemExit(f"{label.capitalize()} not found. Refresh the device list and choose another source.")
            resolved_id = str(getattr(device, "id", "") or device_id or "")
            resolved_name = str(getattr(device, "name", "") or device_name or "Périphérique par défaut")
            source_identity = resolved_id or resolved_name.casefold()
            identity = (kind, source_identity)
            if identity in seen_sources:
                raise SystemExit(f"The same {kind} device is selected more than once: {resolved_name}.")
            seen_sources.add(identity)
            selected_sources.append({"kind": kind, "device_id": resolved_id, "name": resolved_name, "device": device})
    else:
        # Compatibility path for the original CLI and saved preferences.
        microphone = (
            _resolve_named_device(all_microphones, getattr(args, "microphone", None), "microphone")
            if getattr(args, "microphone", None)
            else (sc.default_microphone() if legacy_capture_microphone else None)
        )
        speaker = (
            _resolve_named_device(all_speakers, getattr(args, "output", None), "Windows output")
            if getattr(args, "output", None)
            else (sc.default_speaker() if legacy_capture_windows else None)
        )
        if legacy_capture_microphone and microphone is None:
            raise SystemExit("Microphone not found. Run `glimio devices` or choose another source.")
        if legacy_capture_windows and speaker is None:
            raise SystemExit("Audio output not found. Run `glimio devices` or choose another source.")
        if legacy_capture_microphone and microphone is not None:
            selected_sources.append({"kind": "microphone", "device_id": str(getattr(microphone, "id", "") or ""), "name": str(microphone.name), "device": microphone})
        if legacy_capture_windows and speaker is not None:
            speaker_id = str(getattr(speaker, "id", "") or "")
            try:
                loopback = _resolve_device_id(loopback_microphones, speaker_id, str(speaker.name), "Windows loopback")
            except SystemExit:
                loopback = None
            if loopback is None:
                try:
                    loopback = sc.get_microphone(id=speaker_id or str(speaker.name), include_loopback=True)
                except Exception as exc:
                    raise SystemExit(f"Could not open Windows output {speaker.name}: {exc}") from exc
            selected_sources.append({"kind": "output", "device_id": speaker_id, "name": str(speaker.name), "device": loopback})

    if not selected_sources:
        raise SystemExit("At least one audio source must be selected.")
    capture_microphone = any(source["kind"] == "microphone" for source in selected_sources)
    capture_windows = any(source["kind"] == "output" for source in selected_sources)
    normalize_windows = normalize_windows and capture_windows

    # Keep the classic micro.wav / windows.wav names for the first stream of each type.
    # Additional endpoints get stable numbered names, allowing N independent tracks.
    kind_indices: dict[str, int] = {"microphone": 0, "output": 0}
    for source in selected_sources:
        kind = source["kind"]
        kind_indices[kind] += 1
        base = "micro" if kind == "microphone" else "windows"
        number = kind_indices[kind]
        source["filename"] = f"{base}.wav" if number == 1 else f"{base}-{number}.wav"

    started = datetime.now().astimezone()
    root = Path(args.directory).resolve()
    folder = root / started.strftime("%Y-%m-%d_%H-%M-%S")
    try:
        folder.mkdir(parents=True, exist_ok=False)
        layout = ensure_session_layout(folder)
    except OSError as exc:
        raise SystemExit(f"Could not create session folder {folder}: {exc}") from exc

    if on_session_created is not None:
        try:
            on_session_created(folder)
        except Exception:
            # A UI callback is advisory; it must not abort creation of the audio tracks.
            pass

    stop = stop_event if stop_event is not None else threading.Event()
    errors: list[str] = []
    errors_lock = threading.Lock()
    frame_counts: dict[str, int] = {source["filename"]: 0 for source in selected_sources}
    track_paths = {source["filename"]: layout["audio"] / source["filename"] for source in selected_sources}
    source_by_filename = {source["filename"]: source for source in selected_sources}

    def capture(name: str, device: Any) -> None:
        try:
            # COM initialization is per-thread on Windows; the API/recording worker's
            # apartment does not automatically apply to these dedicated capture threads.
            with audio_com_apartment():
                # Each capture thread owns a writer. The Wave module finalizes its header
                # when closed, so RAM use is bounded by one captured block per track.
                with wave.open(str(track_paths[name]), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(sample_rate)
                    with device.recorder(
                        samplerate=sample_rate,
                        channels=1,
                        blocksize=sample_rate * CHUNK_SECONDS,
                    ) as recorder:
                        while not stop.is_set():
                            data = recorder.record(numframes=sample_rate * CHUNK_SECONDS)
                            if data is not None and len(data):
                                frame_counts[name] += _write_audio_chunk(output, np.asarray(data, dtype=np.float32))
        except Exception as exc:
            with errors_lock:
                errors.append(f"{name}: {exc}")
            stop.set()

    capture_targets: list[tuple[str, Any]] = [(source["filename"], source["device"]) for source in selected_sources]
    threads = [
        threading.Thread(
            target=capture,
            args=(filename, device),
            name=f"capture-{Path(filename).stem}",
            daemon=True,
        )
        for filename, device in capture_targets
    ]
    for thread in threads:
        thread.start()

    def update_status(message: str) -> None:
        if on_status is not None:
            try:
                on_status(message)
            except Exception:
                # UI reporting must never break or stop an audio capture.
                pass

    display_sources = [f"{'microphone' if source['kind'] == 'microphone' else 'audio Windows'} · {source['name']}" for source in selected_sources]
    update_status("Enregistrement en cours · capture de " + " + ".join(display_sources))
    log(f"Session folder: {folder}")
    for source in selected_sources:
        log(f"{'Microphone' if source['kind'] == 'microphone' else 'Windows output / loopback'}: {source['name']} -> {source['filename']}")
    microphone_names = [source["name"] for source in selected_sources if source["kind"] == "microphone"]
    output_names = [source["name"] for source in selected_sources if source["kind"] == "output"]
    for mic_name in microphone_names:
        if any(mic_name.casefold() == output_name.casefold() for output_name in output_names):
            log(
                f"Microphone and Windows output share the display name {mic_name!r}. "
                "The endpoints are selected separately by ID; inspect their saved tracks if the headset routes the same signal to both."
            )
    log("Recording. Press Ctrl+C to stop.")

    try:
        while any(thread.is_alive() for thread in threads):
            if stop.is_set():
                break
            for thread in threads:
                thread.join(timeout=0.25)
    except KeyboardInterrupt:
        log("Stop requested.")
    except BaseException:
        # An unexpected error (or a shutdown-raised SystemExit) in this
        # controlling thread must not leave capture threads recording forever:
        # signal stop and join them, so the cleanup below sees settled writers.
        stop.set()
        for thread in threads:
            thread.join(timeout=CHUNK_SECONDS + 3)
        raise
    finally:
        update_status("Finalisation des pistes WAV…")
        stop.set()
        for thread in threads:
            thread.join(timeout=CHUNK_SECONDS + 3)

        write_errors: list[str] = []
        live_capture_threads = {thread.name for thread in threads if thread.is_alive()}
        for thread in threads:
            if thread.is_alive():
                write_errors.append(
                    f"{thread.name}: capture did not stop within {CHUNK_SECONDS + 3} seconds; "
                    "automatic processing was skipped to avoid reading an unfinished WAV."
                )
        windows_normalization: dict[str, Any] = {
            "enabled": normalize_windows,
            "target_peak_dbfs": -6.0,
            "max_gain_db": max_gain_db,
            "gain_applied_db": 0.0,
            "status": "not_captured" if not capture_windows else "no_samples",
        }
        normalization_tracks: list[dict[str, Any]] = []
        for source in selected_sources:
            filename = source["filename"]
            path = track_paths[filename]
            thread_name = f"capture-{Path(filename).stem}"
            if frame_counts[filename] > 0 and path.is_file():
                normalization_info = None
                if source["kind"] == "output" and thread_name not in live_capture_threads:
                    try:
                        normalization_info = _normalize_wav_peak(path, enabled=normalize_windows, max_gain_db=max_gain_db)
                        peak_before = normalization_info.get("peak_before_dbfs")
                        peak_after = normalization_info.get("peak_after_dbfs")
                        rms_before = normalization_info.get("rms_before_dbfs")
                        rms_after = normalization_info.get("rms_after_dbfs")
                        gain_db = float(normalization_info.get("gain_applied_db", 0.0))
                        if gain_db > 0.01:
                            log(f"{filename} raised by +{gain_db:.1f} dB (peak {peak_before} -> {peak_after} dBFS; RMS {rms_before} -> {rms_after} dBFS).")
                        elif normalization_info.get("status") == "already_at_or_above_target":
                            log(f"{filename} level already sufficient (peak {peak_before} dBFS); no gain applied.")
                        elif normalization_info.get("status") == "silence":
                            log(f"{filename} is silent; normalization skipped.", error=True)
                        elif not normalize_windows:
                            log(f"Normalization disabled for {filename} (peak {peak_before} dBFS; RMS {rms_before} dBFS).")
                    except Exception as exc:
                        normalization_info = {"status": "failed", "error": str(exc), "enabled": normalize_windows, "max_gain_db": max_gain_db}
                        log(f"Normalization failed for {filename}; preserving original track: {exc}", error=True)
                elif source["kind"] == "output":
                    normalization_info = {"status": "skipped_capture_thread_still_active", "error": "WAV was not normalized because its capture thread did not stop cleanly."}
                if normalization_info is not None:
                    normalization_info["filename"] = filename
                    normalization_info["device_name"] = source["name"]
                    normalization_tracks.append(normalization_info)
                    if filename == "windows.wav" or (source["kind"] == "output" and not windows_normalization.get("filename")):
                        windows_normalization = dict(normalization_info)
                log(f"Saved track: {path} ({frame_counts[filename]} frames)")
            else:
                # An opened writer with no samples leaves an empty WAV; don't expose it as a real track.
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    write_errors.append(f"{filename}: could not remove empty track: {exc}")

        audio_source_metadata = [
            {"kind": source["kind"], "device_id": source["device_id"], "name": source["name"], "filename": source["filename"]}
            for source in selected_sources
            if frame_counts[source["filename"]] > 0
        ]
        metadata = {
            "title": session_title or "Session",
            "title_source": "user" if session_title else "default",
            "started_at": started.isoformat(timespec="seconds"),
            "timezone": str(started.tzinfo),
            "sample_rate": sample_rate,
            "audio_bitrate_kbps": bitrate_kbps,
            "duration_seconds": max((frames / sample_rate for frames in frame_counts.values()), default=0),
            "microphone": microphone_names[0] if len(microphone_names) == 1 else microphone_names or None,
            "windows_output": output_names[0] if len(output_names) == 1 else output_names or None,
            "capture_microphone": capture_microphone,
            "capture_windows": capture_windows,
            "audio_sources": audio_source_metadata,
            "captured_tracks": [Path(filename).stem for filename, frames in frame_counts.items() if frames > 0],
            "windows_normalization": windows_normalization,
            "audio_normalization": normalization_tracks,
            "capture_errors": errors,
        }
        try:
            metadata_output_path(folder).write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            write_errors.append(f"metadata/seance.json: {exc}")

    if errors or write_errors:
        raise SystemExit(
            "Errors during recording:\n- " + "\n- ".join(errors + write_errors)
        )
    if not any(frame_counts.values()):
        raise SystemExit(f"No audio recorded in {folder}.")

    log(f"Recording finished: {folder}")
    update_status("Pistes WAV finalisées · préparation du traitement demandé…")

    # Automation intentionally runs only after the WAV files have been finalized.
    if getattr(args, "auto_pv", False):
        from ..processing.pipeline import process_folder

        process_folder(folder, args, on_status=update_status if on_status is not None else None)
    elif getattr(args, "auto_transcribe", False):
        from ..processing.pipeline import transcribe_folder

        transcribe_folder(folder, args, on_status=update_status if on_status is not None else None)
    else:
        update_status("Enregistrement terminé · aucun traitement automatique demandé")
        log(f'To transcribe later: seance transcribe "{folder}"')



def record(
    args: argparse.Namespace,
    *,
    stop_event: threading.Event | None = None,
    on_session_created: Callable[[Path], None] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> None:
    """Run recording with COM initialized on the calling thread and capture threads.

    Keeps the historical CLI API intact while making it safe to invoke from FastAPI
    worker threads, which do not inherit COM initialization from the main thread.
    """
    requested_sources = getattr(args, "audio_sources", None)
    capture_microphone = bool(getattr(args, "capture_microphone", True))
    capture_windows = bool(getattr(args, "capture_windows", True))
    if requested_sources is not None:
        if not isinstance(requested_sources, (list, tuple)) or not requested_sources:
            raise SystemExit("At least one audio source must be selected.")
    elif not capture_microphone and not capture_windows:
        raise SystemExit("At least one audio source must be enabled: microphone or Windows audio.")

    # SoundCard's Windows module initializes COM during import; do that before our
    # per-thread CoInitializeEx call. The API worker thread then gets its own apartment.
    _soundcard()
    with audio_com_apartment():
        _record_impl(
            args,
            stop_event=stop_event,
            on_session_created=on_session_created,
            on_status=on_status,
        )
