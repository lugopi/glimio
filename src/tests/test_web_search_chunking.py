from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from web import app as web_app


class SearchChunkingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = web_app.Settings(context=8192, max_tokens=6000)
        self.binary = Path("fake-llama.exe")
        self.model = Path("fake-model.gguf")

    @staticmethod
    def passages(count: int) -> list[dict[str, object]]:
        return [
            {
                "source_number": index,
                "title": f"Séance {index}",
                "session_id": f"2026-10-17_10-00-{index:02d}",
                "filename": "transcription.md",
                "kind": "transcript",
                "text": f"Le passage {index} donne des informations sur le sujet de test numéro {index}.",
            }
            for index in range(1, count + 1)
        ]

    def test_many_passages_are_synthesized_in_batches_then_merged(self) -> None:
        sources = self.passages(8)
        stages: list[str] = []

        def fake_runner(_binary, _model, _cwd, _system, prompt, **kwargs):
            stage = kwargs["stage"]
            stages.append(stage)
            if stage.startswith("Notes de recherche"):
                numbers = re.findall(r"(?m)^SOURCE \[(\d+)\]$", prompt)
                self.assertLessEqual(len(numbers), 3)
                citations = " ".join(f"[{number}]" for number in numbers)
                return (f"Les extraits de ce groupe présentent le sujet de test. {citations}", False)
            if stage == "Synthèse finale transversale des séances":
                return ("## Synthèse générale\nLes séances décrivent le sujet de test sous plusieurs angles [1] [3] [8].", False)
            raise AssertionError(f"Unexpected stage: {stage}")

        with patch.object(web_app, "run_completion_resilient", side_effect=fake_runner):
            answer, hit_limit = web_app._generate_search_synthesis(
                "Que disent les séances sur le sujet de test ?", sources,
                self.settings, self.binary, self.model,
            )

        self.assertFalse(hit_limit)
        self.assertIn("Synthèse générale", answer)
        self.assertEqual(sum(stage.startswith("Notes de recherche") for stage in stages), 3)
        self.assertIn("Synthèse finale transversale des séances", stages)

    def test_generation_limit_falls_back_to_recursive_source_chunks(self) -> None:
        sources = self.passages(3)
        stages: list[str] = []

        def fake_runner(_binary, _model, _cwd, _system, prompt, **kwargs):
            stage = kwargs["stage"]
            stages.append(stage)
            if stage == "Synthèse transversale des séances":
                return ("réponse coupée", True)
            if stage.startswith("Notes de recherche"):
                numbers = re.findall(r"(?m)^SOURCE \[(\d+)\]$", prompt)
                # First try for the full 3-item group is truncated; split calls complete.
                if len(numbers) == 3:
                    return ("réponse coupée", True)
                return ("Note concise fondée sur " + " ".join(f"[{number}]" for number in numbers), False)
            if stage == "Synthèse finale transversale des séances":
                return ("## Synthèse générale\nLes sources montrent des éléments complémentaires [1] [2] [3].", False)
            raise AssertionError(f"Unexpected stage: {stage}")

        with patch.object(web_app, "run_completion_resilient", side_effect=fake_runner):
            answer, hit_limit = web_app._generate_search_synthesis(
                "Résume le sujet de test.", sources,
                self.settings, self.binary, self.model,
            )

        self.assertFalse(hit_limit)
        self.assertIn("[3]", answer)
        self.assertGreaterEqual(sum(stage.startswith("Notes de recherche") for stage in stages), 3)

    def test_final_unknown_citation_is_detected_after_chunk_synthesis(self) -> None:
        sources = self.passages(4)

        def fake_runner(_binary, _model, _cwd, _system, prompt, **kwargs):
            stage = kwargs["stage"]
            if stage.startswith("Notes de recherche"):
                numbers = re.findall(r"(?m)^SOURCE \[(\d+)\]$", prompt)
                return ("Note sourcée " + " ".join(f"[{number}]" for number in numbers), False)
            if stage == "Synthèse finale transversale des séances":
                return ("## Synthèse générale\nUne affirmation non fondée [99].", False)
            if stage.startswith("Consolidation des notes"):
                return ("Notes condensées [1] [2] [3] [4].", False)
            raise AssertionError(f"Unexpected stage: {stage}")

        with patch.object(web_app, "run_completion_resilient", side_effect=fake_runner):
            with self.assertRaises(web_app.LLMError):
                web_app._generate_search_synthesis(
                    "Résume le sujet de test.", sources,
                    self.settings, self.binary, self.model,
                )


if __name__ == "__main__":
    unittest.main()
