from pathlib import Path
from dataclasses import replace

import pytest

from seance.providers.contracts import ProviderInfo, ProviderResourceLink, ProviderStatus
from web.services.provider_installer import ProviderInstallManager


def provider(extra: str | None = "separation", packages: tuple[str, ...] = ("speechbrain>=1.0.0",)) -> ProviderInfo:
    return ProviderInfo(
        id="test-python-provider", name="Test", task="diarization", description="test",
        execution="embedded", python_install_extra=extra, python_install_packages=packages,
        setup_links=(ProviderResourceLink("Models", "https://example.org/models", "model"),),
        translations={"en": {"Test": "Test provider"}},
    )


def test_python_provider_metadata_exposes_safe_install_and_setup_links() -> None:
    payload = ProviderStatus(provider=provider(), ready=False, message="missing").to_dict()
    assert payload["python_install_available"] is True
    assert payload["python_install_extra"] == "separation"
    assert payload["python_install_packages"] == ["speechbrain>=1.0.0"]
    assert payload["setup_links"][0]["kind"] == "model"
    assert payload["translations"]["en"]["Test"] == "Test provider"


def test_build_command_prefers_known_project_extra(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    manager = ProviderInstallManager()
    command, cwd = manager._build_command(provider(), tmp_path)
    assert command[-2:] == ["-e", ".[separation]"]
    assert command[:3][-1] == "pip"
    assert cwd == tmp_path
    assert "shell" not in command


def test_build_command_falls_back_to_declared_package_when_no_source_tree(tmp_path: Path) -> None:
    manager = ProviderInstallManager()
    command, cwd = manager._build_command(provider(extra=None), tmp_path)
    assert command[-1] == "speechbrain>=1.0.0"
    assert cwd == tmp_path


def test_install_rejects_unknown_extra_before_starting_thread(tmp_path: Path) -> None:
    manager = ProviderInstallManager()
    untrusted = replace(provider(), python_install_extra="--no-deps")
    with pytest.raises(ValueError, match="Nom d’extra Python invalide"):
        manager.start(untrusted, project_root=tmp_path)


def test_install_rejects_frozen_runtime_with_helpful_message(tmp_path: Path) -> None:
    manager = ProviderInstallManager()
    with pytest.raises(RuntimeError, match="version empaquetée"):
        manager.start(provider(), project_root=tmp_path, frozen=True)


def test_only_catalog_declared_package_strings_are_used(tmp_path: Path) -> None:
    manager = ProviderInstallManager()
    bad = replace(provider(extra=None), python_install_packages=("--index-url https://bad.invalid",))
    with pytest.raises(ValueError, match="Liste de paquets"):
        manager.start(bad, project_root=tmp_path)


def test_provider_status_api_exposes_resource_links_and_install_capability(tmp_path: Path) -> None:
    from unittest.mock import patch
    from web.app import _default_preferences, providers

    with patch("web.app._get_preferences", return_value=_default_preferences()), patch("web.app.PROJECT_ROOT", tmp_path):
        payload = providers()

    listed = {item["id"]: item for item in payload["providers"]}
    whisper = listed["whisper.cpp"]
    assert any(link["kind"] == "binary" for link in whisper["setup_links"])
    assert any(link["kind"] == "model" for link in whisper["setup_links"])
    assert "en" in whisper["translations"]
    assert whisper["translations"]["en"]["Modèle de transcription"] == "Transcription model"
    assert whisper["python_install_available"] is False
    sepformer = listed["speechbrain-sepformer"]
    assert sepformer["python_install_available"] is True
    assert sepformer["python_install_runtime_available"] is True
    assert sepformer["python_install_extra"] == "separation"
    assert sepformer["setup_links"]


def test_install_api_only_accepts_catalogued_python_providers(tmp_path: Path) -> None:
    from unittest.mock import patch
    from fastapi import HTTPException
    from starlette.requests import Request
    from web.app import install_provider_python

    local_request = Request({
        "type": "http", "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/api/providers/speechbrain-sepformer/install-python",
        "raw_path": b"/api/providers/speechbrain-sepformer/install-python",
        "query_string": b"", "headers": [], "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 12345),
    })
    remote_request = Request({
        "type": "http", "http_version": "1.1", "method": "POST",
        "scheme": "http", "path": "/api/providers/speechbrain-sepformer/install-python",
        "raw_path": b"/api/providers/speechbrain-sepformer/install-python",
        "query_string": b"", "headers": [], "server": ("127.0.0.1", 8765),
        "client": ("192.168.1.20", 12345),
    })
    fake_install = {"id": "install-1", "provider_id": "speechbrain-sepformer", "state": "queued"}
    with patch("web.app._PROVIDER_INSTALLER.start", return_value=fake_install) as start, patch("web.app.PROJECT_ROOT", tmp_path):
        result = install_provider_python("speechbrain-sepformer", local_request)
    assert result["install"]["id"] == "install-1"
    start.assert_called_once()

    with pytest.raises(HTTPException) as raised:
        install_provider_python("speechbrain-sepformer", remote_request)
    assert raised.value.status_code == 403

    with pytest.raises(HTTPException) as raised:
        install_provider_python("whisper.cpp", local_request)
    assert raised.value.status_code == 400

    with pytest.raises(HTTPException) as raised:
        install_provider_python("made-up-provider", local_request)
    assert raised.value.status_code == 404


def test_background_install_streams_output_and_flags_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import time
    import web.services.provider_installer as installer_module

    class FakeProcess:
        stdout = iter(["Collecting speechbrain>=1.0.0\n", "Successfully installed speechbrain\n"])

        @staticmethod
        def wait() -> int:
            return 0

    monkeypatch.setattr(installer_module.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    manager = ProviderInstallManager()
    started = manager.start(provider(), project_root=tmp_path)
    deadline = time.monotonic() + 2.0
    current = manager.get(started["id"])
    while current and current["state"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = manager.get(started["id"])

    assert current is not None
    assert current["state"] == "succeeded"
    assert "Successfully installed speechbrain" in current["output"]
    assert current["restart_required"] is True
    assert current["message"] == "Installation terminée."


def test_ffmpeg_provider_requires_ffprobe_for_media_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from seance.providers.registry import get_provider_statuses
    from web.app import Settings, _default_preferences

    ffmpeg = tmp_path / "ffmpeg.exe"
    ffmpeg.write_bytes(b"test executable placeholder")
    monkeypatch.setattr(
        "seance.providers.registry.shutil.which",
        lambda command: str(ffmpeg) if command == "ffmpeg" else None,
    )
    settings = Settings(**_default_preferences()["settings"])

    statuses = {status.provider.id: status for status in get_provider_statuses(settings, project_root=tmp_path)}
    assert statuses["ffmpeg"].ready is False
    assert "ffprobe" in statuses["ffmpeg"].missing

    (tmp_path / "ffprobe.exe").write_bytes(b"test executable placeholder")
    statuses = {status.provider.id: status for status in get_provider_statuses(settings, project_root=tmp_path)}
    assert statuses["ffmpeg"].ready is True


def test_all_builtin_providers_expose_provider_owned_english_metadata() -> None:
    from seance.providers.registry import BUILTIN_PROVIDERS

    assert BUILTIN_PROVIDERS
    for info in BUILTIN_PROVIDERS:
        assert info.translations.get("en"), f"{info.id} should keep its own English metadata translations"
