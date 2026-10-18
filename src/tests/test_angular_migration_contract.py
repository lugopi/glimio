"""Contract tests for the staged Angular 22 migration."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "src" / "web" / "frontend"


def test_angular_workspace_targets_supported_major_and_strict_templates() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    angular = json.loads((FRONTEND / "angular.json").read_text(encoding="utf-8"))
    tsconfig = json.loads((FRONTEND / "tsconfig.json").read_text(encoding="utf-8"))

    assert package["dependencies"]["@angular/core"].startswith("^22.")
    assert package["devDependencies"]["@angular/cli"].startswith("^22.")
    assert package["devDependencies"]["typescript"].startswith("~6.0.")
    assert angular["projects"]["glimio-web-ui"]["architect"]["build"]["builder"] == "@angular/build:application"
    assert tsconfig["compilerOptions"]["strict"] is True
    assert tsconfig["angularCompilerOptions"]["strictTemplates"] is True


def test_angular_uses_shared_api_and_reusable_pagination_component() -> None:
    app = FRONTEND / "src" / "app"
    assert (app / "core" / "api.service.ts").is_file()
    assert (app / "core" / "api.models.ts").is_file()
    assert (app / "shared" / "pagination.component.ts").is_file()
    assert (app / "pages" / "recording" / "recording.page.ts").is_file()
    assert (app / "pages" / "library" / "library.page.ts").is_file()
    assert (app / "pages" / "search" / "search.page.ts").is_file()
    assert (app / "pages" / "settings" / "settings.page.ts").is_file()


def test_existing_production_entrypoint_is_preserved_until_cutover() -> None:
    html = (ROOT / "src" / "web" / "static" / "index.html").read_text(encoding="utf-8")
    assert '<script type="module" src="/static/js/app.js"></script>' in html
    assert '<glimio-root>' not in html
    docs = (ROOT / "docs" / "ANGULAR_22_MIGRATION.md").read_text(encoding="utf-8")
    assert "Required gates before cutover" in docs
    assert "existing `/` entry point is deliberately unchanged" in docs


def test_heroicons_are_served_from_a_local_svg_sprite() -> None:
    sprite = ROOT / "src" / "web" / "static" / "vendor" / "heroicons" / "heroicons.svg"
    icons = sprite.read_text(encoding="utf-8")
    component = (FRONTEND / "src" / "app" / "shared" / "icon.component.ts").read_text(encoding="utf-8")
    assert '<symbol id="bars-3"' in icons
    assert '<symbol id="x-mark"' in icons
    assert "https://" not in component
    assert "/static/vendor/heroicons/heroicons.svg#" in component


def test_all_functional_icons_use_local_heroicons_sprite() -> None:
    import re

    static = ROOT / "src" / "web" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    ui = (static / "js" / "components" / "ui.js").read_text(encoding="utf-8")
    jobs = (static / "js" / "pages" / "jobs.js").read_text(encoding="utf-8")
    sprite = (static / "vendor" / "heroicons" / "heroicons.svg").read_text(encoding="utf-8")
    # The Glimio brand mark is served as a dedicated SVG image asset. Every
    # inline SVG left in the interface must therefore be a Heroicons symbol.
    assert '<img class="brand-logo" src="/static/brand/glimio.svg"' in html
    all_svgs = re.findall(r"<svg\b.*?</svg>", html, flags=re.DOTALL)
    assert all_svgs
    assert all("<use href=\"/static/vendor/heroicons/heroicons.svg#" in block for block in all_svgs)
    assert "<path" not in ui and "<circle" not in ui and "<rect" not in ui
    assert "<path" not in jobs and "<circle" not in jobs and "<rect" not in jobs
    symbols = set(re.findall(r'<symbol id="([^"]+)"', sprite))
    used = set(re.findall(r"heroicons\.svg#([a-z0-9-]+)", html + ui + jobs))
    assert used <= symbols


def test_session_library_exposes_persisted_processing_options() -> None:
    app = ROOT / "src" / "web" / "frontend" / "src" / "app"
    library = (app / "pages" / "library" / "library.page.ts").read_text(encoding="utf-8")
    library_template = (app / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    api = (app / "core" / "api.service.ts").read_text(encoding="utf-8")
    backend = (ROOT / "src" / "web" / "app.py").read_text(encoding="utf-8")
    assert "templateUrl: './library.page.html'" in library
    assert "styleUrl: './library.page.scss'" in library
    assert "Options de traitement de cette séance" in library_template
    assert "saveSessionSettings" in api
    assert '@app.put("/api/sessions/{session_id}/settings")' in backend
    assert 'metadata["processing_settings"]' in backend


def test_angular_components_keep_logic_template_and_scss_separate() -> None:
    app = FRONTEND / "src" / "app"
    components = [
        app / "app.component",
        app / "shared" / "icon.component",
        app / "shared" / "pagination.component",
        app / "pages" / "recording" / "recording.page",
        app / "pages" / "library" / "library.page",
        app / "pages" / "search" / "search.page",
        app / "pages" / "settings" / "settings.page",
    ]
    for component in components:
        ts_file = component.with_name(component.name + ".ts")
        html_file = component.with_name(component.name + ".html")
        scss_file = component.with_name(component.name + ".scss")
        assert ts_file.is_file()
        assert html_file.is_file()
        assert scss_file.is_file()
        source = ts_file.read_text(encoding="utf-8")
        assert "templateUrl:" in source
        assert "styleUrl:" in source
        assert "template: `" not in source
