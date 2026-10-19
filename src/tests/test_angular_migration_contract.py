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
    pagination_ts = (app / "shared" / "pagination.component.ts").read_text(encoding="utf-8")
    assert (app / "shared" / "pagination.component.ts").is_file()
    assert "import { IconComponent } from './icon.component';" in pagination_ts
    assert "imports: [IconComponent]" in pagination_ts
    assert (app / "pages" / "recording" / "recording.page.ts").is_file()
    assert (app / "pages" / "library" / "library.page.ts").is_file()
    assert (app / "pages" / "search" / "search.page.ts").is_file()
    assert (app / "pages" / "settings" / "settings.page.ts").is_file()


def test_existing_production_entrypoint_is_preserved_until_cutover() -> None:
    html = (FRONTEND / "src" / "index.html").read_text(encoding="utf-8")
    assert "<glimio-root></glimio-root>" in html
    assert 'rel="icon"' in html and 'href="favicon.svg"' in html
    assert (FRONTEND / "public" / "favicon.svg").is_file()


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


def test_library_polls_and_exposes_terminal_job_states_in_list_and_detail() -> None:
    app = ROOT / "src" / "web" / "frontend" / "src" / "app"
    library = (app / "pages" / "library" / "library.page.ts").read_text(encoding="utf-8")
    template = (app / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    styles = (ROOT / "src" / "web" / "frontend" / "src" / "styles" / "components.scss").read_text(encoding="utf-8")
    assert "interval(2000)" in library and "exhaustMap" in library
    assert "this.api.sessions(options)" in library and "this.api.session(id)" in library
    assert "processingStateLabel" in template
    assert "processing.state === 'completed'" in template
    assert "processing.state === 'error'" in template
    assert 'class="detail-processing-status"' in template and 'aria-live="polite"' in template
    # The terminal/live status is placed in the detail header, before the document panel.
    assert template.index('class="detail-header"') < template.index('class="detail-processing-status"')
    assert template.index('class="detail-processing-status"') < template.index('class="detail-section available-documents"')
    # The session card uses a button with phrasing-content children; status is its sibling.
    assert '<article class="session-card"' in template
    assert '<button class="session-card-select"' in template
    assert ".session-card-select:focus-visible" in styles


def test_brand_svg_keeps_dynamic_fill_layers_without_editor_metadata() -> None:
    svg = (ROOT / "src" / "web" / "frontend" / "public" / "brand" / "glimio.svg").read_text(encoding="utf-8")
    assert 'id="layer3"' in svg and 'id="layer2"' in svg
    assert 'fill="currentColor"' in svg
    assert 'data-layer="wave"' in svg
    assert 'fill-opacity="0.25"' in svg
    assert 'viewBox="0 -12 512 524"' in svg
    assert 'var(--brand-shadow' not in svg
    assert "inkscape:" not in svg and "sodipodi:" not in svg and "namedview" not in svg


def test_library_documents_precede_audio_status_and_settings() -> None:
    library_template = (ROOT / "src" / "web" / "frontend" / "src" / "app" / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    positions = [
        library_template.index('class="detail-header"'),
        library_template.index('class="detail-processing-status"'),
        library_template.index('class="detail-section available-documents"'),
        library_template.index('id="session-audio-title"'),
        library_template.index('class="detail-section session-processing-options"'),
    ]
    assert positions == sorted(positions)
    for name in ("document-text", "sparkles", "play", "bars-3", "pencil-square", "arrow-path", "trash"):
        assert f'name="{name}"' in library_template


def test_settings_page_has_open_source_license_notice() -> None:
    settings = (ROOT / "src" / "web" / "frontend" / "src" / "app" / "pages" / "settings" / "settings.page.html").read_text(encoding="utf-8")
    assert 'class="license-notice"' in settings
    assert "AGPL-3.0-or-later" in settings
    assert 'https://www.gnu.org/licenses/agpl-3.0.html' in settings


def test_brand_logo_uses_all_of_its_responsive_container() -> None:
    styles = (ROOT / "src" / "web" / "frontend" / "src" / "styles" / "components.scss").read_text(encoding="utf-8")
    assert ".brand-mark { overflow: visible; flex: 0 0 auto; }" in styles
    assert "width: 100%;\n    height: 100%;" in styles


def test_library_and_recording_share_accessible_pagination_and_page_buttons() -> None:
    app = ROOT / "src" / "web" / "frontend" / "src" / "app"
    pagination = (app / "shared" / "pagination.component.html").read_text(encoding="utf-8")
    pagination_scss = (app / "shared" / "pagination.component.scss").read_text(encoding="utf-8")
    recording = (app / "pages" / "recording" / "recording.page.html").read_text(encoding="utf-8")
    library = (app / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    assert 'attr.aria-current' in pagination and "token === page() ? 'page' : null" in pagination
    assert 'Page précédente' in pagination and 'Page suivante' in pagination
    assert 'Page ' + "' + token" in pagination
    assert 'pagination-summary' in pagination and 'Page {{' not in pagination
    assert 'focus-visible' in pagination_scss
    icon_component = (app / 'shared' / 'icon.component.ts').read_text(encoding='utf-8')
    icon_styles = (app / 'shared' / 'icon.component.scss').read_text(encoding='utf-8')
    assert "size() === 'fill'" in icon_component and '.icon--fill { width: 100%; height: 100%;' in icon_styles
    assert 'glimio-pagination' in recording and 'glimio-pagination' in library


def test_recording_supports_multiple_sources_and_accessible_file_dropzone() -> None:
    app = ROOT / "src" / "web" / "frontend" / "src" / "app"
    recording_ts = (app / "pages" / "recording" / "recording.page.ts").read_text(encoding="utf-8")
    recording_html = (app / "pages" / "recording" / "recording.page.html").read_text(encoding="utf-8")
    api_models = (app / "core" / "api.models.ts").read_text(encoding="utf-8")
    api_service = (app / "core" / "api.service.ts").read_text(encoding="utf-8")
    backend = (ROOT / "src" / "web" / "app.py").read_text(encoding="utf-8")
    assert 'selectedAudioSources' in recording_ts and 'addAudioSource' in recording_ts
    assert 'remove-audio-source' in recording_html and 'file-dropzone' in recording_html
    assert 'AudioSourceSelection' in api_models and 'sources?: AudioSourceSelection[]' in api_service
    assert 'sources: list[AudioSourceSelection] | None' in backend
    assert 'Ajoutez au moins une source audio' in recording_ts


def test_library_artifact_switcher_obeys_keyboard_tab_pattern() -> None:
    app = ROOT / "src" / "web" / "frontend" / "src" / "app"
    template = (app / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    component = (app / "pages" / "library" / "library.page.ts").read_text(encoding="utf-8")
    assert 'role="tablist"' in template and 'role="tab"' in template and 'role="tabpanel"' in template
    assert 'aria-controls="artifact-content-pane"' in template and 'attr.aria-labelledby' in template
    assert 'ArrowRight' in component and 'ArrowLeft' in component and 'event.preventDefault()' in component
    assert 'onArtifactTabKeydown' in template


def test_library_template_avoids_redundant_audio_tracks_coalescing() -> None:
    template = (FRONTEND / "src" / "app" / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    assert "@for (track of session.audio_tracks; track track)" in template
    assert "session.audio_tracks ?? []" not in template


def test_markdown_tables_are_rendered_in_a_responsive_scroll_region() -> None:
    app = FRONTEND / "src" / "app"
    library = (app / "pages" / "library" / "library.page.ts").read_text(encoding="utf-8")
    global_styles = (FRONTEND / "src" / "styles" / "components.scss").read_text(encoding="utf-8")
    assert "isTableSeparator" in library and "<table><thead>" in library
    assert 'class="artifact-table-wrap"' in library and 'tabindex="0"' in library
    assert ".artifact-rendered .artifact-table-wrap" in global_styles


def test_model_downloads_are_manual_official_links_and_sensitive_models_are_gated() -> None:
    app = FRONTEND / "src" / "app"
    settings = (app / "pages" / "settings" / "settings.page.html").read_text(encoding="utf-8")
    component = (app / "pages" / "settings" / "settings.page.ts").read_text(encoding="utf-8")
    assert "github.com/ggml-org/llama.cpp/releases" in settings
    assert "huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-q5_0.bin" in settings
    assert "lfmLicenseReviewed()" in settings and "segmentationLicenseReviewed()" in settings
    assert "embeddingLicenseReviewed()" in settings
    assert "setSegmentationLicenseReviewed" in component and "setEmbeddingLicenseReviewed" in component
    assert "Glimio n’exécute pas automatiquement des binaires tiers" in settings


def test_final_audio_track_deletion_warns_that_reprocessing_will_need_import() -> None:
    app = FRONTEND / "src" / "app"
    library_ts = (app / "pages" / "library" / "library.page.ts").read_text(encoding="utf-8")
    library_html = (app / "pages" / "library" / "library.page.html").read_text(encoding="utf-8")
    settings = (app / "pages" / "settings" / "settings.page.html").read_text(encoding="utf-8")
    assert "dernière piste audio" in library_ts and "réimportez une source audio" in library_ts
    assert "Aucune piste audio n’est conservée" in library_html
    # Interactive links must not be nested inside a label's accessible checkbox target.
    assert "J’ai lu et j’accepte la LFM Open License v1.0 pour mon usage." in settings
    assert '<span>J’ai lu et j’accepte la <a href=' not in settings
