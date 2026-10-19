from __future__ import annotations

import unittest
from pydantic import ValidationError

from web.app import Settings, UIPreferences


class WebSettingsContractTests(unittest.TestCase):
    def test_rejects_processing_limits_below_supported_minimum(self) -> None:
        invalid_settings = (
            {"context": 1024},
            {"max_tokens": 400},
            {"analysis_tokens": 80},
        )
        for values in invalid_settings:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Settings(**values)

    def test_accepts_supported_summary_format_and_themes(self) -> None:
        self.assertEqual(Settings(format="daily").format, "daily")
        self.assertEqual(UIPreferences(theme="dracula").theme, "dracula")
        self.assertEqual(UIPreferences(theme="monokai").theme, "monokai")


if __name__ == "__main__":
    unittest.main()
