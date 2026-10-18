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

from .common import log
from .layout import ensure_session_layout, metadata_output_path

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
    capture_microphone = bool(getattr(args, "capture_microphone", True))
    capture_windows = bool(getattr(args, "capture_windows", True))
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
    normalize_windows = normalize_windows and capture_windows
    if not capture_microphone and not capture_windows:
        raise SystemExit("At least one audio source must be enabled: microphone or Windows audio.")

    sc = _soundcard()
    microphones = sc.all_microphones(include_loopback=False) if capture_microphone else []
    speakers = sc.all_speakers() if capture_windows else []

    microphone = (
        next(
            (m for m in microphones if args.microphone.casefold() in m.name.casefold()),
            None,
        )
        if getattr(args, "microphone", None)
        else (sc.default_microphone() if capture_microphone else None)
    )
    speaker = (
        next(
            (s for s in speakers if args.output.casefold() in s.name.casefold()),
            None,
        )
        if getattr(args, "output", None)
        else (sc.default_speaker() if capture_windows else None)
    )

    if capture_microphone and microphone is None:
        raise SystemExit("Microphone not found. Run `glimio devices` or choose another source.")
    if capture_windows and speaker is None:
        raise SystemExit("Audio output not found. Run `glimio devices` or choose another source.")

    loopback = None
    if capture_windows:
        try:
            loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        except Exception as exc:
            raise SystemExit(
                f"Could not open Windows output {speaker.name}: {exc}"
            ) from exc

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
    frame_counts: dict[str, int] = {"micro": 0, "windows": 0}
    track_paths = {
        "micro": layout["audio"] / "micro.wav",
        "windows": layout["audio"] / "windows.wav",
    }

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

    capture_targets: list[tuple[str, Any]] = []
    if capture_microphone:
        capture_targets.append(("micro", microphone))
    if capture_windows:
        capture_targets.append(("windows", loopback))
    threads = [
        threading.Thread(
            target=capture,
            args=(name, device),
            name=f"capture-{name}",
            daemon=True,
        )
        for name, device in capture_targets
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

    selected_sources = []
    if capture_microphone:
        selected_sources.append("microphone")
    if capture_windows:
        selected_sources.append("audio Windows")
    update_status("Enregistrement en cours · capture de " + " + ".join(selected_sources))
    log(f"Session folder: {folder}")
    if microphone is not None:
        log(f"Microphone: {microphone.name}")
    else:
        log("Microphone capture disabled.")
    if speaker is not None:
        log(f"Windows audio: {speaker.name}")
    else:
        log("Windows audio capture disabled.")
    log("Recording. Press Ctrl+C to stop.")

    try:
        while any(thread.is_alive() for thread in threads):
            if stop.is_set():
                break
            for thread in threads:
                thread.join(timeout=0.25)
    except KeyboardInterrupt:
        log("Stop requested.")
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
        for source, filename in (("micro", "micro.wav"), ("windows", "windows.wav")):
            path = track_paths[source]
            if frame_counts[source] > 0 and path.is_file():
                if source == "windows" and "capture-windows" not in live_capture_threads:
                    try:
                        windows_normalization = _normalize_wav_peak(
                            path, enabled=normalize_windows, max_gain_db=max_gain_db
                        )
                        peak_before = windows_normalization.get("peak_before_dbfs")
                        peak_after = windows_normalization.get("peak_after_dbfs")
                        rms_before = windows_normalization.get("rms_before_dbfs")
                        rms_after = windows_normalization.get("rms_after_dbfs")
                        gain_db = float(windows_normalization.get("gain_applied_db", 0.0))
                        if gain_db > 0.01:
                            log(
                                f"Windows audio level raised by +{gain_db:.1f} dB "
                                f"(peak {peak_before} -> {peak_after} dBFS; "
                                f"RMS {rms_before} -> {rms_after} dBFS; target peak -6 dBFS, "
                                f"maximum gain +{max_gain_db:.0f} dB)."
                            )
                        elif windows_normalization.get("status") == "already_at_or_above_target":
                            log(f"Windows audio level already sufficient (peak {peak_before} dBFS); no gain applied.")
                        elif windows_normalization.get("status") == "silence":
                            log("Windows audio track is silent; normalization skipped.", error=True)
                        elif not normalize_windows:
                            log(
                                f"Windows audio normalization disabled (peak {peak_before} dBFS; "
                                f"RMS {rms_before} dBFS)."
                            )
                    except Exception as exc:
                        # Keep the original finalized WAV if normalization fails; audio is more
                        # important than the optional gain step, so don't block transcription.
                        windows_normalization.update({"status": "failed", "error": str(exc)})
                        log(f"Windows audio normalization failed; preserving the WAV as recorded: {exc}", error=True)
                elif source == "windows":
                    windows_normalization.update({
                        "status": "skipped_capture_thread_still_active",
                        "error": "WAV was not normalized because its capture thread did not stop cleanly.",
                    })
                log(f"Saved track: {path} ({frame_counts[source]} frames)")
            else:
                # An opened writer with no samples leaves an empty WAV; don't expose it
                # as a real track in the library.
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    write_errors.append(f"{filename}: could not remove empty track: {exc}")

        metadata = {
            "title": session_title or "Session",
            "title_source": "user" if session_title else "default",
            "started_at": started.isoformat(timespec="seconds"),
            "timezone": str(started.tzinfo),
            "sample_rate": sample_rate,
            "audio_bitrate_kbps": bitrate_kbps,
            "microphone": microphone.name if microphone is not None else None,
            "windows_output": speaker.name if speaker is not None else None,
            "capture_microphone": capture_microphone,
            "capture_windows": capture_windows,
            "captured_tracks": [
                name for name, filename in (("micro", "micro.wav"), ("windows", "windows.wav"))
                if frame_counts[name] > 0
            ],
            "windows_normalization": windows_normalization,
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
    if not frame_counts["micro"] and not frame_counts["windows"]:
        raise SystemExit(f"No audio recorded in {folder}.")

    log(f"Recording finished: {folder}")
    update_status("Pistes WAV finalisées · préparation du traitement demandé…")

    # Automation intentionally runs only after the WAV files have been finalized.
    if getattr(args, "auto_pv", False):
        from .pipeline import process_folder

        process_folder(folder, args, on_status=update_status if on_status is not None else None)
    elif getattr(args, "auto_transcribe", False):
        from .pipeline import transcribe_folder

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
    capture_microphone = bool(getattr(args, "capture_microphone", True))
    capture_windows = bool(getattr(args, "capture_windows", True))
    if not capture_microphone and not capture_windows:
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
