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
    html = (FRONTEND / "src" / "index.html").read_text(encoding="utf-8")
    assert "<glimio-root></glimio-root>" in html
    assert 'rel="icon"' in html and "brand/glimio.svg" in html


def test_icons_come_from_ng_heroicons_registry() -> None:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    registry = (FRONTEND / "src" / "app" / "shared" / "icon-registry.ts").read_text(encoding="utf-8")
    component = (FRONTEND / "src" / "app" / "shared" / "icon.component.ts").read_text(encoding="utf-8")
    assert "@ng-icons/core" in package["dependencies"]
    assert "@ng-icons/heroicons" in package["dependencies"]
    assert "from '@ng-icons/heroicons/outline'" in registry
    assert "NgIconComponent" in component
    assert "/static/vendor" not in component and "https://" not in component


def test_all_functional_icons_use_the_ng_icon_component() -> None:
    import re

    app = FRONTEND / "src" / "app"
    registry = (app / "shared" / "icon-registry.ts").read_text(encoding="utf-8")
    registered = set(re.findall(r"^  ([A-Za-z0-9]+):", registry, flags=re.MULTILINE)) | set(
        re.findall(r"'([a-z0-9-]+)':", registry)
    )
    used: set[str] = set()
    for template in app.rglob("*.html"):
        used |= set(re.findall(r'<glimio-icon\s+name="([^"]+)"', template.read_text(encoding="utf-8")))
    assert used
    for name in used:
        key = name if name in registered else name.replace("-x", "X").replace("-", "")
        assert name in registered or key in registered, f"icône « {name} » absente du registre @ng-icons"


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


def test_angular_components_keep_logic_and_scss_separate() -> None:
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
        scss_file = component.with_name(component.name + ".scss")
        assert ts_file.is_file(), f"fichier manquant : {ts_file}"
        assert scss_file.is_file(), f"style SCSS manquant : {scss_file}"
        source = ts_file.read_text(encoding="utf-8")
        assert "styleUrl:" in source, f"{ts_file.name} doit référencer son .scss via styleUrl"
        html_file = component.with_name(component.name + ".html")
        if html_file.is_file():
            assert "templateUrl:" in source, f"{ts_file.name} doit référencer son .html via templateUrl"
