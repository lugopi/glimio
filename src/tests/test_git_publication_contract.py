from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class GitPublicationContractTests(unittest.TestCase):
    def test_version_is_in_unreleased_zero_series_and_aligned(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        app = (ROOT / "src/web/app.py").read_text(encoding="utf-8")
        package = json.loads((ROOT / "src/web/frontend/package.json").read_text(encoding="utf-8"))
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn('version = "0.4.2"', pyproject)
        self.assertIn('version="0.4.2"', app)
        self.assertEqual(package["version"], "0.4.2")
        self.assertIn("## 0.4.2 —", changelog)
        self.assertNotRegex(changelog, r"^## 2\\.\\d+\\.\\d+", msg="Historical versions should use the 0.x development series")

    def test_gitignore_excludes_models_runtime_and_native_binaries(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in ("/models/", "/bin/", ".glimio/", "/seances/", "*.gguf", "*.onnx", "*.bin", "*.exe", "*.dll", ".env"):
            self.assertIn(entry, ignore)

    def test_model_sources_and_license_scope_are_documented(self) -> None:
        model_doc = (ROOT / "docs/MODELS.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        for model in ("LFM2.5-8B-A1B", "ggml-large-v3.bin", "nemo_en_titanet_small.onnx", "model.onnx"):
            self.assertIn(model, model_doc)
        self.assertIn("LFM Open License v1.0", model_doc)
        self.assertIn("ne remplace pas les conditions distinctes", readme)
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Remote Network Interaction", license_text)
        self.assertIn("AGPL-3.0-or-later", (ROOT / "docs/LICENSING.md").read_text(encoding="utf-8"))

    def test_git_release_docs_exist(self) -> None:
        for path in ("CONTRIBUTING.md", "SECURITY.md", "docs/GIT_PREPARATION.md", "docs/MODELS.md", "docs/LICENSING.md", "LICENSE", "NOTICE", ".gitattributes"):
            self.assertTrue((ROOT / path).is_file(), path)


    def test_local_databases_and_recordings_are_ignored(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("*.sqlite3", "*.sqlite3-wal", "*.db", "*.wav", "*.mp3", "*.mp4"):
            self.assertIn(pattern, ignore)

if __name__ == "__main__":
    unittest.main()
