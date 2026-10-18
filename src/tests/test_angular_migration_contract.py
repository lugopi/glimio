"""Contract tests for the finished Angular 22 cutover (full-Angular front end)."""
from __future__ import annotations

import json
import re
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


def test_angular_is_the_only_served_entrypoint() -> None:
    """After the cutover, `/` serves the Angular index and no legacy JS remains."""
    html = (FRONTEND / "src" / "index.html").read_text(encoding="utf-8")
    assert "<glimio-root>" in html
    static = ROOT / "src" / "web" / "static"
    assert not (static / "js").exists()
    assert not (static / "vendor").exists()
    served_index = static / "index.html"
    if served_index.is_file():
        assert "<glimio-root>" in served_index.read_text(encoding="utf-8")
    backend = (ROOT / "src" / "web" / "app.py").read_text(encoding="utf-8")
    assert "/angular/" not in backend


def test_icons_come_from_ng_heroicons_not_a_static_sprite() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    assert "@ng-icons/core" in package["dependencies"]
    assert "@ng-icons/heroicons" in package["dependencies"]
    component = (FRONTEND / "src" / "app" / "shared" / "icon.component.ts").read_text(encoding="utf-8")
    registry = (FRONTEND / "src" / "app" / "shared" / "icon-registry.ts").read_text(encoding="utf-8")
    assert "NgIcon" in component
    assert "heroicons.svg" not in component + registry
    assert "https://" not in component + registry
    for import_line in re.findall(r"from '([^']+)'", registry):
        assert import_line.startswith("@ng-icons/") or import_line == "rxjs", import_line


def test_all_functional_icons_use_the_glimio_icon_component() -> None:
    app = FRONTEND / "src" / "app"
    used: set[str] = set()
    for template in app.rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        assert "<svg" not in text, f"inline SVG left in {template.name}"
        used.update(re.findall(r'<glimio-icon\s+name="([a-z0-9-]+)"', text))
    registry = (app / "shared" / "icon-registry.ts").read_text(encoding="utf-8")
    assert used, "no icons found in templates"
    for name in used:
        assert f"'{name}'" in registry, f"icon '{name}' missing from icon-registry.ts"


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


def test_library_offers_regenerate_summary_action() -> None:
    app = ROOT / "src" / "web" / "frontend" / "src" / "app"
    library_template = (app / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    library_ts = (app / "pages" / "library" / "library.page.ts").read_text(encoding="utf-8")
    api = (app / "core" / "api.service.ts").read_text(encoding="utf-8")
    backend = (ROOT / "src" / "web" / "app.py").read_text(encoding="utf-8")
    assert "Refaire le résumé" in library_template
    assert "runJob('summarize', true)" in library_template
    assert "force" in library_ts and "force" in api
    assert "force" in backend


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
