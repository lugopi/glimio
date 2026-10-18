"""Check the WCAG AAA text contrast for Glimio's primary theme token pairs.

This guard covers the named token pairs documented in ACCESSIBILITY_AUDIT.md only.
It is deliberately not advertised as a whole-site WCAG conformance checker.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TOKENS = Path(__file__).resolve().parents[1] / "src" / "web" / "frontend" / "src" / "tokens.css"
TEXT_KEYS = ("--c-text", "--c-muted", "--c-subtle", "--c-success", "--c-warning", "--c-danger")


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _themes(css: str) -> dict[str, dict[str, str]]:
    pattern = re.compile(
        r'(?s)(:root(?:\s*,\s*:root\[data-theme="dark"\])?|'
        r':root\[data-theme="(light|midnight|forest)"\])\s*\{([^}]+)\}'
    )
    found: dict[str, dict[str, str]] = {}
    for match in pattern.finditer(css):
        selectors, named_theme, body = match.groups()
        theme = named_theme or ("dark" if 'data-theme="dark"' in selectors else "dark")
        tokens = dict(re.findall(r'(--c-[\w-]+)\s*:\s*(#[\da-fA-F]{6})\s*;', body))
        if theme in found:
            # The stylesheet's base :root and dark declaration are equivalent; prefer the explicit dark theme.
            if theme == "dark" and 'data-theme="dark"' in selectors:
                found[theme] = tokens
        else:
            found[theme] = tokens
    return found


def check(css: str) -> tuple[bool, list[str]]:
    themes = _themes(css)
    failures: list[str] = []
    required = {"dark", "light", "midnight", "forest"}
    missing = sorted(required - set(themes))
    if missing:
        failures.append(f"Thèmes absents ou non analysés : {', '.join(missing)}")
    for theme, tokens in themes.items():
        bg = tokens.get("--c-surface-raised")
        if not bg:
            failures.append(f"{theme}: --c-surface-raised absent")
            continue
        for key in TEXT_KEYS:
            fg = tokens.get(key)
            if not fg:
                failures.append(f"{theme}: {key} absent")
                continue
            ratio = contrast_ratio(fg, bg)
            if ratio < 7:
                failures.append(f"{theme}: {key} / --c-surface-raised = {ratio:.2f}:1 (minimum 7:1)")
        accent, accent_text = tokens.get("--c-accent"), tokens.get("--c-accent-contrast")
        if accent and accent_text:
            ratio = contrast_ratio(accent_text, accent)
            if ratio < 7:
                failures.append(f"{theme}: bouton primaire = {ratio:.2f}:1 (minimum 7:1)")
        else:
            failures.append(f"{theme}: couleur accent ou texte du bouton absente")
    return not failures, failures


def main() -> int:
    css = TOKENS.read_text(encoding="utf-8")
    passed, failures = check(css)
    for failure in failures:
        print(f"ÉCHEC: {failure}")
    if not passed:
        return 1
    print("OK — les paires de jetons textuelles documentées dépassent 7:1 sur la surface élevée dans les quatre thèmes.")
    print("Limite : ce contrôle ne mesure pas tous les éléments/states du site et ne certifie pas WCAG AAA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
