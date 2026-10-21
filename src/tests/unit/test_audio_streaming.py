from __future__ import annotations

import tempfile
import unittest
import argparse
import wave
from types import SimpleNamespace
from pathlib import Path

import numpy as np

from seance.media.audio import SAMPLE_RATE, _resolve_device_id, _resolve_named_device, _write_audio_chunk, record


class StreamingWaveTests(unittest.TestCase):
    def test_device_resolution_prefers_case_insensitive_exact_name(self) -> None:
        exact = SimpleNamespace(name="Bluetooth Headset")
        partial = SimpleNamespace(name="Bluetooth Headset Hands-Free")
        self.assertIs(_resolve_named_device([partial, exact], "bluetooth headset", "microphone"), exact)

    def test_stable_device_id_wins_when_display_names_are_identical(self) -> None:
        first = SimpleNamespace(id="input-1", name="Bluetooth Headset")
        second = SimpleNamespace(id="input-2", name="Bluetooth Headset")
        self.assertIs(_resolve_device_id([first, second], "input-2", "Bluetooth Headset", "microphone"), second)

    def test_device_resolution_rejects_ambiguous_partial_match(self) -> None:
        devices = [
            SimpleNamespace(name="Bluetooth Headset Hands-Free"),
            SimpleNamespace(name="Bluetooth Headset Stereo"),
        ]
        with self.assertRaisesRegex(SystemExit, "matches several devices"):
            _resolve_named_device(devices, "Bluetooth Headset", "microphone")

    def test_device_resolution_rejects_duplicate_exact_names(self) -> None:
        devices = [SimpleNamespace(name="USB Audio"), SimpleNamespace(name="USB Audio")]
        with self.assertRaisesRegex(SystemExit, "exact name"):
            _resolve_named_device(devices, "USB Audio", "Windows output")

    def test_record_rejects_disabling_both_sources_before_loading_audio_backend(self) -> None:
        with self.assertRaisesRegex(SystemExit, "At least one audio source"):
            record(argparse.Namespace(capture_microphone=False, capture_windows=False))

    def test_writes_multiple_blocks_as_one_valid_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "stream.wav"
            first = np.array([[-1.0], [0.0]], dtype=np.float32)
            second = np.array([[0.5], [1.0]], dtype=np.float32)
            with wave.open(str(target), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(SAMPLE_RATE)
                self.assertEqual(_write_audio_chunk(writer, first), 2)
                self.assertEqual(_write_audio_chunk(writer, second), 2)
            with wave.open(str(target), "rb") as reader:
                self.assertEqual(reader.getnchannels(), 1)
                self.assertEqual(reader.getsampwidth(), 2)
                self.assertEqual(reader.getframerate(), SAMPLE_RATE)
                self.assertEqual(reader.getnframes(), 4)
                samples = np.frombuffer(reader.readframes(4), dtype="<i2")
            self.assertEqual(samples.tolist(), [-32767, 0, 16383, 32767])

    def test_downmixes_stereo_block_to_mono(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "mono.wav"
            stereo = np.array([[0.5, -0.5], [1.0, 0.0]], dtype=np.float32)
            with wave.open(str(target), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(SAMPLE_RATE)
                self.assertEqual(_write_audio_chunk(writer, stereo), 2)
            with wave.open(str(target), "rb") as reader:
                self.assertEqual(reader.getnchannels(), 1)
                samples = np.frombuffer(reader.readframes(2), dtype="<i2")
            self.assertEqual(samples.tolist(), [0, 16383])


if __name__ == "__main__":
    unittest.main()
