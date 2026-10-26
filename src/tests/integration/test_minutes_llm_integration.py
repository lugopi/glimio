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


    def test_assembled_summary_is_reviewed_when_it_fits_in_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = root / "2026-10-16_10-00-00"
            session.mkdir()
            (session / "transcription.md").write_text(
                "Le service calcule la réponse puis valide et stocke le résultat.\n" * 180,
                encoding="utf-8",
            )
            model = root / "model.gguf"
            executable = root / "llama-completion.exe"
            model.write_bytes(b"test model marker")
            executable.write_bytes(b"test executable marker")
            args = argparse.Namespace(
                gguf=str(model), llama_completion=str(executable), context=8192,
                max_tokens=1000, analysis_tokens=1000, analysis_retries=0,
                analysis_max_splits=2, folder=str(session), directory=str(root),
                model="unused-model.bin", whisper_cli="unused-whisper.exe",
                language="fr", openvino_device=None, threads=1, ffmpeg="ffmpeg",
                format="summary", no_review=False, diarize=False,
            )
            stages: list[str] = []
            detailed_notes = "## Fonctionnement\n\n" + "Le service valide le résultat avant de le stocker. " * 18
            section_draft = "## Fonctionnement\n\n" + "Le service calcule puis valide le résultat. " * 18

            def fake_shared_generation(*_args, **kwargs):
                stage = kwargs["stage"]
                stages.append(stage)
                if stage.startswith("Analyse"):
                    return detailed_notes, False
                if stage.startswith("Rédaction"):
                    return section_draft, False
                if stage.startswith("Synthèse globale"):
                    return "Le résumé décrit le calcul, la validation et le stockage du résultat.", False
                if stage == "Relecture du résumé":
                    prompt = _args[4]
                    return prompt.split("BROUILLON À RELIRE :\n", 1)[1], False
                raise AssertionError(f"Unexpected LLM stage: {stage}")

            with patch("seance.processing.minutes._run_llama_resilient", side_effect=fake_shared_generation):
                from seance.processing import minutes
                minutes.summarize(args)

            self.assertTrue(any(stage.startswith("Rédaction 1/") for stage in stages))
            self.assertIn("Relecture du résumé", stages)
            result = (session / "summary" / "resume_audio.md").read_text(encoding="utf-8")
            self.assertIn("Fonctionnement", result)


if __name__ == "__main__":
    unittest.main()
