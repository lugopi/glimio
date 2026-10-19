from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from seance.layout import get_audio_path, list_audio_paths
from web.services.library import _audio_duration_seconds, _session_record


class DynamicAudioTrackLayoutTests(unittest.TestCase):
    def test_lists_numbered_microphones_and_outputs_in_stable_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "audio"
            audio.mkdir()
            for name in ("windows-2.wav", "micro-3.wav", "windows.wav", "micro.wav", "micro-2.wav", "audio_import.wav"):
                (audio / name).write_bytes(b"test")

            self.assertEqual(
                [path.name for path in list_audio_paths(root)],
                ["micro.wav", "micro-2.wav", "micro-3.wav", "windows.wav", "windows-2.wav", "audio_import.wav"],
            )

    def test_get_audio_path_accepts_numbered_tracks_but_rejects_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "audio"
            audio.mkdir()
            expected = audio / "micro-2.wav"
            expected.write_bytes(b"test")
            self.assertEqual(get_audio_path(root, "micro-2.wav"), expected)
            self.assertEqual(get_audio_path(root, "../micro-2.wav").name, "__invalid_audio_filename__")
            self.assertEqual(get_audio_path(root, "arbitrary.wav").name, "__invalid_audio_filename__")

    def test_library_exposes_session_duration_from_recorded_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "2026-10-19_12-00-00"
            audio = root / "audio"
            audio.mkdir(parents=True)
            target = audio / "micro.wav"
            with wave.open(str(target), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16_000)
                output.writeframes(np.zeros(40_000, dtype="<i2").tobytes())

            self.assertEqual(_audio_duration_seconds(root, {}), 2.5)
            self.assertEqual(_session_record(root)["duration_seconds"], 2.5)


if __name__ == "__main__":
    unittest.main()
