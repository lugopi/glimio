from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seance.processing import minutes


class MinutesSharedEngineIntegrationTests(unittest.TestCase):
    def test_summary_pipeline_still_writes_the_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = root / "2026-10-16_10-00-00"
            session.mkdir()
            (session / "transcription.md").write_text(
                "[00:00:01–00:00:03] Le service traite les demandes.\n"
                "[00:00:04–00:00:06] Le cache réduit les accès au disque.\n"
                "[00:00:07–00:00:09] Une validation est nécessaire après la mise à jour.\n",
                encoding="utf-8",
            )
            model = root / "model.gguf"
            executable = root / "llama-completion.exe"
            model.write_bytes(b"test model marker")
            executable.write_bytes(b"test executable marker")
            args = argparse.Namespace(
                gguf=str(model), llama_completion=str(executable), context=8192,
                max_tokens=1000, analysis_tokens=1000, analysis_retries=1,
                analysis_max_splits=6, folder=str(session), directory=str(root),
                model="unused-model.bin", whisper_cli="unused-whisper.exe",
                language="fr", openvino_device=None, threads=1, ffmpeg="ffmpeg",
                format="summary", no_review=True, diarize=False,
            )

            def fake_shared_generation(*_args, **kwargs):
                stage = kwargs["stage"]
                if stage.startswith("Analyse"):
                    return (
                        "## Fonctionnement\nLe service traite les demandes et le cache réduit "
                        "les accès disque ; une validation protège la mise à jour.", False,
                    )
                if stage.startswith("Rédaction"):
                    return (
                        "# Résumé du contenu audio\n\n## Fonctionnement\nLe service traite "
                        "les demandes. Le cache réduit les accès disque.", False,
                    )
                raise AssertionError(f"Unexpected LLM stage: {stage}")

            with patch("seance.processing.minutes._run_llama_resilient", side_effect=fake_shared_generation):
                minutes.summarize(args)

            result = (session / "summary" / "resume_audio.md").read_text(encoding="utf-8")
            self.assertIn("Fonctionnement", result)
            self.assertTrue((session / "analysis" / "analyses.md").is_file())
            self.assertTrue((session / "summary" / "resume_audio_initial.md").is_file())
            self.assertTrue((session / "summary" / "compatibility" / "pv_brouillon.md").is_file())


if __name__ == "__main__":
    unittest.main()
