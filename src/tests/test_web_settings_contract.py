from __future__ import annotations

import unittest
from pathlib import Path
import re
from pydantic import ValidationError

from web.app import (
    DEFAULT_WHISPER_MODEL, DEFAULT_WHISPER_CLI, DEFAULT_GGUF, DEFAULT_LLAMA_COMPLETION, Settings,
)


class WebSettingsContractTests(unittest.TestCase):
    def test_rejects_context_below_minutes_engine_minimum(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(context=1024)

    def test_rejects_output_budget_below_minutes_engine_minimum(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(max_tokens=400)

    def test_rejects_analysis_budget_below_minutes_engine_minimum(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(analysis_tokens=80)


    def test_settings_form_paths_match_backend_defaults(self) -> None:
        # Full-Angular cutover : le front ne codera plus en dur les chemins de
        # modèles — il affiche ceux renvoyés par l'API (source de vérité).
        from fastapi.testclient import TestClient
        from web.app import app

        client = TestClient(app)
        payload = client.get("/api/preferences").json()
        settings = payload["settings"]
        expected = {
            "model": DEFAULT_WHISPER_MODEL,
            "whisper_cli": DEFAULT_WHISPER_CLI,
            "gguf": DEFAULT_GGUF,
            "llama_completion": DEFAULT_LLAMA_COMPLETION,
            "diarization_segmentation_model": "models/diarization/segmentation/segmentation.onnx",
            "diarization_embedding_model": "models/diarization/embedding/embedding.onnx",
        }
        for key, path in expected.items():
            self.assertIn(key, settings, f"Champ manquant dans /api/preferences : {key}")
            self.assertEqual(settings[key], path, f"Défaut divergent pour {key}")

    def test_daily_format_is_exposed_by_api_and_accepted_by_settings(self) -> None:
        from fastapi.testclient import TestClient
        from web.app import app, UIPreferences

        client = TestClient(app)
        config = client.get("/api/config").json()
        self.assertIn("daily", config["formats"])
        self.assertEqual(Settings(format="daily").format, "daily")
        self.assertEqual(UIPreferences(theme="dracula").theme, "dracula")
        self.assertEqual(UIPreferences(theme="monokai").theme, "monokai")

    def test_cli_fallbacks_use_upstream_executable_names(self) -> None:
        src_root = Path(__file__).parents[1]
        pipeline = (src_root / "seance" / "pipeline.py").read_text(encoding="utf-8")
        minutes = (src_root / "seance" / "minutes.py").read_text(encoding="utf-8")
        self.assertIn('"bin/asr/whisper-cli.exe"', pipeline)
        self.assertIn('"bin/asr/whisper-cli.exe"', minutes)
        self.assertIn('"bin/llm/llama-completion.exe"', pipeline)
        app_source = (src_root / "web" / "app.py").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_WHISPER_CLI = "bin/asr/whisper-cli.exe"', app_source)
        self.assertIn('DEFAULT_LLAMA_COMPLETION = "bin/llm/llama-completion.exe"', app_source)


if __name__ == "__main__":
    unittest.main()
