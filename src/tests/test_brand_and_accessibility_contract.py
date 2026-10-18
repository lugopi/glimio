from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class BrandAndAccessibilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (ROOT / "src/web/static/index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "src/web/static/app.css").read_text(encoding="utf-8")
        cls.pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_glimio_is_the_visible_brand(self) -> None:
        self.assertIn("Glimio — Audio, transcription et notes", self.html)
        self.assertIn('class="brand-name">Glimio</strong>', self.html)
        self.assertIn('name = "glimio-notes"', self.pyproject)
        self.assertIn('glimio-web = "web.app:main"', self.pyproject)


    def test_modern_normalize_is_loaded_before_app_styles(self) -> None:
        self.assertIn('href="/static/modern-normalize.css"', self.html)
        self.assertLess(self.html.index('/static/modern-normalize.css'), self.html.index('/static/app.css'))
        normalize = (ROOT / "src/web/static/modern-normalize.css").read_text(encoding="utf-8")
        self.assertIn("modern-normalize", normalize)
        self.assertIn("License: MIT", normalize)

    def test_typography_uses_relative_units_and_readable_base_size(self) -> None:
        self.assertIn("font-size: 1rem", self.css)
        self.assertIn("font-style: italic", self.css)
        source_css = (ROOT / "src/web/frontend/src/components.css").read_text(encoding="utf-8")
        for stylesheet in (self.css, source_css):
            self.assertNotRegex(stylesheet, r"font-size\s*:[^;{}]*\b\d+(?:\.\d+)?px")
            self.assertNotRegex(stylesheet, r"(?<![-\w])font\s*:[^;{}]*\b\d+(?:\.\d+)?px")

    def test_legacy_cli_and_namespace_are_preserved(self) -> None:
        self.assertIn('seance = "seance.cli:main"', self.pyproject)
        self.assertIn('seance-web = "web.app:main"', self.pyproject)

    def test_skip_link_and_main_landmark_are_present(self) -> None:
        self.assertIn('class="skip-link" href="#main-content"', self.html)
        self.assertIn('id="main-content" tabindex="-1"', self.html)
        self.assertIn(".skip-link:focus", self.css)

    def test_global_settings_have_a_dedicated_navigation_view(self) -> None:
        self.assertIn('data-view="settings"', self.html)
        self.assertIn('id="view-settings"', self.html)
        self.assertIn('id="settings-body"', self.html)
        self.assertNotIn('id="toggle-settings"', self.html)
        self.assertNotIn('id="settings-body" hidden', self.html)

    def test_reduced_motion_preferences_are_respected(self) -> None:
        self.assertIn("prefers-reduced-motion: reduce", self.css)

    def test_readme_does_not_claim_full_aaa_conformance(self) -> None:
        self.assertIn("ACCESSIBILITY_AUDIT.md", self.readme)
        self.assertIn("n’est pas certifiée", self.readme)

    def test_documented_theme_contrast_guard_passes(self) -> None:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_theme_contrast.py")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ne certifie pas WCAG AAA", result.stdout)


if __name__ == "__main__":
    unittest.main()
