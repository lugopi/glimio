from __future__ import annotations

import argparse
import json
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from seance.audio import _normalize_wav_peak, _wav_pcm16_stats, record


def write_pcm16(path: Path, samples: np.ndarray, *, sample_rate: int = 16_000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(np.asarray(samples, dtype="<i2").tobytes())




class _FakeRecorder:
    def __init__(self, stop_event: threading.Event) -> None:
        self.stop_event = stop_event
        self.sent_block = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def record(self, *, numframes: int) -> np.ndarray:
        if self.sent_block:
            return np.zeros((0, 1), dtype=np.float32)
        self.sent_block = True
        # A low-level loopback block similar to the dBFS values reported by the user.
        data = np.full((numframes, 1), 0.03, dtype=np.float32)
        self.stop_event.set()
        return data


class _FakeLoopbackDevice:
    name = "Default Windows output"

    def __init__(self, stop_event: threading.Event) -> None:
        self.stop_event = stop_event

    def recorder(self, **_kwargs):
        return _FakeRecorder(self.stop_event)


class _FakeSpeaker:
    name = "Default Windows output"


class _FakeSoundCard:
    def __init__(self, stop_event: threading.Event) -> None:
        self.speaker = _FakeSpeaker()
        self.loopback = _FakeLoopbackDevice(stop_event)

    def all_microphones(self, include_loopback=False):
        return [self.loopback] if include_loopback else []

    def all_speakers(self):
        return [self.speaker]

    def default_speaker(self):
        return self.speaker

    def get_microphone(self, *, id: str, include_loopback: bool):
        assert id == self.speaker.name and include_loopback
        return self.loopback


class WindowsAudioNormalizationTests(unittest.TestCase):
    def test_quiet_track_is_raised_to_minus_six_dbfs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "windows.wav"
            samples = np.zeros(32_000, dtype="<i2")
            samples[::32] = 1000
            write_pcm16(path, samples)

            before = _wav_pcm16_stats(path)
            result = _normalize_wav_peak(path)
            after = _wav_pcm16_stats(path)

            self.assertEqual(result["status"], "normalized")
            self.assertGreater(result["gain_applied_db"], 20)
            self.assertAlmostEqual(after["peak_dbfs"], -6.0, delta=0.1)
            self.assertGreater(after["rms_dbfs"], before["rms_dbfs"] + 20)
            self.assertEqual(after["frames"], before["frames"])
            with wave.open(str(path), "rb") as reader:
                self.assertEqual(reader.getframerate(), 16_000)
                self.assertEqual(reader.getnchannels(), 1)
                self.assertEqual(reader.getsampwidth(), 2)

    def test_loud_enough_track_is_not_attenuated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "windows.wav"
            samples = np.array([0, 20_000, -15_000, 4, -4], dtype="<i2")
            write_pcm16(path, samples)
            original = path.read_bytes()

            result = _normalize_wav_peak(path)

            self.assertEqual(result["status"], "already_at_or_above_target")
            self.assertEqual(result["gain_applied_db"], 0.0)
            self.assertEqual(path.read_bytes(), original)

    def test_silence_is_not_amplified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "windows.wav"
            write_pcm16(path, np.zeros(4096, dtype="<i2"))
            original = path.read_bytes()

            result = _normalize_wav_peak(path)

            self.assertEqual(result["status"], "silence")
            self.assertEqual(result["gain_applied_db"], 0.0)
            self.assertEqual(path.read_bytes(), original)

    def test_disabled_normalization_only_measures_levels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "windows.wav"
            write_pcm16(path, np.array([0, 1000, -500, 20], dtype="<i2"))
            original = path.read_bytes()

            result = _normalize_wav_peak(path, enabled=False)

            self.assertEqual(result["status"], "disabled")
            self.assertIsNotNone(result["peak_before_dbfs"])
            self.assertEqual(path.read_bytes(), original)

    def test_gain_is_capped_for_extremely_quiet_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "windows.wav"
            samples = np.zeros(4096, dtype="<i2")
            samples[::64] = 100
            write_pcm16(path, samples)

            result = _normalize_wav_peak(path, max_gain_db=20.0)
            after = _wav_pcm16_stats(path)

            self.assertEqual(result["status"], "gain_capped")
            self.assertAlmostEqual(result["gain_applied_db"], 20.0, delta=0.01)
            self.assertLess(after["peak_dbfs"], -29.0)
            self.assertGreater(after["peak_dbfs"], -31.0)

    def test_invalid_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "windows.wav"
            write_pcm16(path, np.array([1000, -1000], dtype="<i2"))
            with self.assertRaisesRegex(ValueError, "below 0 dBFS"):
                _normalize_wav_peak(path, target_peak_dbfs=0.0)
            with self.assertRaisesRegex(ValueError, "between 0 and 30 dB"):
                _normalize_wav_peak(path, max_gain_db=31.0)

    def test_recording_pipeline_normalizes_windows_track_before_metadata_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            stop_event = threading.Event()
            fake_soundcard = _FakeSoundCard(stop_event)
            args = argparse.Namespace(
                directory=str(root), title="loopback level test", microphone=None, output=None,
                capture_microphone=False, capture_windows=True,
                normalize_windows=True, normalize_windows_max_gain_db=30.0,
                auto_pv=False, auto_transcribe=False,
            )
            with patch("seance.audio._soundcard", return_value=fake_soundcard):
                record(args, stop_event=stop_event)

            sessions = [path for path in root.iterdir() if path.is_dir()]
            self.assertEqual(len(sessions), 1)
            folder = sessions[0]
            wav_path = folder / "audio" / "windows.wav"
            self.assertTrue(wav_path.is_file())
            measured = _wav_pcm16_stats(wav_path)
            self.assertAlmostEqual(measured["peak_dbfs"], -6.0, delta=0.1)
            metadata = json.loads((folder / "metadata" / "seance.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["windows_normalization"]["status"], "normalized")
            self.assertGreater(metadata["windows_normalization"]["gain_applied_db"], 20.0)


if __name__ == "__main__":
    unittest.main()
