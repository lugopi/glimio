from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from seance.providers.registry import get_provider_statuses


def _whisper_status(tmp_path: Path, *, vad_mode: str, include_vad_model: bool = False):
    model = tmp_path / "whisper-model.bin"
    executable = tmp_path / "whisper-cli"
    model.write_bytes(b"model-placeholder")
    executable.write_bytes(b"executable-placeholder")
    options = {
        "model": str(model),
        "whisper_cli": str(executable),
        "vad_mode": vad_mode,
        "vad_model": "models/asr/ggml-silero-v6.2.0.bin",
    }
    if include_vad_model:
        vad_model = tmp_path / "models" / "asr" / "ggml-silero-v6.2.0.bin"
        vad_model.parent.mkdir(parents=True)
        vad_model.write_bytes(b"vad-placeholder")
    settings = SimpleNamespace(provider_options={"whisper.cpp": options})
    return next(
        status for status in get_provider_statuses(settings, project_root=tmp_path)
        if status.provider.id == "whisper.cpp"
    )


def test_auto_vad_warns_when_model_is_missing_but_keeps_whisper_ready(tmp_path: Path) -> None:
    status = _whisper_status(tmp_path, vad_mode="auto")

    assert status.ready
    assert status.details["vad_model_available"] is False
    assert status.details["warnings"] == [
        "Modèle VAD Silero introuvable : le mode automatique désactive temporairement le VAD."
    ]


def test_required_vad_model_blocks_readiness_when_missing(tmp_path: Path) -> None:
    status = _whisper_status(tmp_path, vad_mode="on")

    assert not status.ready
    assert any("ggml-silero-v6.2.0.bin" in item for item in status.missing)
    assert "warnings" not in status.details


def test_disabled_vad_does_not_warn_about_an_unused_model(tmp_path: Path) -> None:
    status = _whisper_status(tmp_path, vad_mode="off")

    assert status.ready
    assert status.details["vad_model_available"] is False
    assert "warnings" not in status.details


def test_auto_vad_is_quiet_when_model_is_present(tmp_path: Path) -> None:
    status = _whisper_status(tmp_path, vad_mode="auto", include_vad_model=True)

    assert status.ready
    assert status.details["vad_model_available"] is True
    assert "warnings" not in status.details
