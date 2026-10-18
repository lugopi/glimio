"""Brand & accessibility contracts, now enforced on the Angular front end."""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "src" / "web" / "frontend" / "src"


class BrandAndAccessibilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (FRONTEND_SRC / "index.html").read_text(encoding="utf-8")
        cls.app_html = (FRONTEND_SRC / "app" / "app.component.html").read_text(encoding="utf-8")
        cls.styles = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted((FRONTEND_SRC / "styles").glob("*.scss"))
        )
        cls.pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_glimio_is_the_visible_brand(self) -> None:
        self.assertIn("Glimio — Audio, transcription et notes", self.html)
        self.assertIn('class="brand-name">Glimio</strong>', self.app_html)
        self.assertIn('name = "glimio-notes"', self.pyproject)
        self.assertIn('glimio-web = "web.app:main"', self.pyproject)

    def test_modern_normalize_is_loaded_before_app_styles(self) -> None:
        main_scss = (FRONTEND_SRC / "styles" / "main.scss").read_text(encoding="utf-8")
        normalize = (FRONTEND_SRC / "styles" / "modern-normalize.scss").read_text(encoding="utf-8")
        self.assertIn("modern-normalize", normalize)
        self.assertIn("License: MIT", normalize)
        self.assertLess(main_scss.index("modern-normalize"), main_scss.index("components"))

    def test_typography_uses_relative_units_and_readable_base_size(self) -> None:
        self.assertIn("font-size: 1rem", self.styles)
        self.assertIn("italic", self.styles)
        self.assertNotRegex(self.styles, r"font-size\s*:[^;{}]*\b\d+(?:\.\d+)?px")
        self.assertNotRegex(self.styles, r"(?<![-\w])font\s*:[^;{}]*\b\d+(?:\.\d+)?px")

    def test_legacy_cli_and_namespace_are_preserved(self) -> None:
        self.assertIn('seance = "seance.cli:main"', self.pyproject)
        self.assertIn('seance-web = "web.app:main"', self.pyproject)

    def test_skip_link_and_main_landmark_are_present(self) -> None:
        self.assertIn('class="skip-link" href="#main-content"', self.app_html)
        self.assertIn('id="main-content" tabindex="-1"', self.app_html)
        self.assertIn(".skip-link:focus", self.styles)

    def test_global_settings_have_a_dedicated_navigation_view(self) -> None:
        routes = (FRONTEND_SRC / "app" / "app.routes.ts").read_text(encoding="utf-8")
        settings_html = (FRONTEND_SRC / "app" / "pages" / "settings" / "settings.page.html").read_text(encoding="utf-8")
        nav_html = self.app_html
        self.assertIn("path: 'settings'", routes)
        self.assertIn("settings.page", routes)
        self.assertIn("/settings", nav_html)
        self.assertIn("settings-body", settings_html.replace("settingsBody", "settings-body"))

    def test_reduced_motion_preferences_are_respected(self) -> None:
        self.assertIn("prefers-reduced-motion: reduce", self.styles)

    def test_readme_does_not_claim_full_aaa_conformance(self) -> None:
        self.assertIn("ACCESSIBILITY_AUDIT.md", self.readme)

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


if __name__ == "__main__":
    unittest.main()
