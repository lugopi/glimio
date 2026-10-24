from __future__ import annotations

import json
from pathlib import Path

import pytest

from seance.cli import build_parser
from seance.providers.cli import run_provider_command


def test_root_cli_help_includes_provider_management(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["--help"])
    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "providers" in output
    assert "transcribe" in output


def test_provider_subcommand_help_works_without_web_app(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as raised:
        parser.parse_args(["providers", "--help"])
    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "list" in output
    assert "info" in output
    assert "install" in output
    assert "doctor" in output


def test_cli_can_print_provider_owned_help_without_starting_web(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["providers", "info", "speechbrain-ecapa"])
    result = run_provider_command(args, project_root=tmp_path)
    output = capsys.readouterr().out

    assert result == 0
    assert "speechbrain-ecapa" in output
    assert "Paquets catalogue" in output
    assert "Modèle ECAPA" in output
    assert "Installer PyTorch" in output


def test_cli_provider_list_json_is_machine_readable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["providers", "list", "--json"])
    result = run_provider_command(args, project_root=tmp_path)
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    providers = {item["id"]: item for item in payload}
    assert "sherpa-onnx" in providers
    assert "speechbrain-ecapa" in providers
    assert "python_install_available" in providers["speechbrain-ecapa"]


def test_provider_list_human_readable_does_not_require_web_app(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = build_parser().parse_args(["providers", "list"])
    result = run_provider_command(args, project_root=tmp_path)
    output = capsys.readouterr().out

    assert result == 0
    assert "PROVIDER" in output
    assert "sherpa-onnx" in output
    assert "speechbrain-ecapa" in output
    assert "installables à la demande" in output
