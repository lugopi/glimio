from __future__ import annotations

from pathlib import Path

from seance.media.speech_enhancement import enhance_for_transcription


class FakeProcess:
    def __init__(self, command, on_output=None, returncode=0, stdout="", stderr=""):
        self.command = command
        self._on_output = on_output
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def communicate(self, timeout=None):
        if self._on_output is not None:
            self._on_output(self.command)
        return self.stdout, self.stderr

    def terminate(self):
        pass

    def kill(self):
        pass


def test_ffmpeg_mode_creates_separate_enhanced_file_and_uses_conservative_denoising(tmp_path, monkeypatch):
    source = tmp_path / "original.wav"
    source.write_bytes(b"original remains unchanged")
    target = tmp_path / "enhanced.wav"
    commands = []

    def fake_popen(command, *args, **kwargs):
        commands.append(command)
        return FakeProcess(command, on_output=lambda cmd: Path(cmd[-1]).write_bytes(b"enhanced wav output" * 6))

    monkeypatch.setattr("seance.media.speech_enhancement.subprocess.Popen", fake_popen)
    result, selected = enhance_for_transcription(source, target, mode="ffmpeg", ffmpeg="ffmpeg")

    assert result == target
    assert selected == "ffmpeg"
    assert target.is_file()
    assert source.read_bytes() == b"original remains unchanged"
    command = commands[0]
    assert "highpass=f=65,lowpass=f=7600,afftdn=nr=8:nf=-45:tn=1" in command
    assert command[command.index("-ar") + 1] == "16000"


def test_off_mode_returns_original_without_creating_target(tmp_path):
    source = tmp_path / "original.wav"
    source.write_bytes(b"original")
    target = tmp_path / "enhanced.wav"

    result, selected = enhance_for_transcription(source, target, mode="off")

    assert result == source.resolve()
    assert selected == "off"
    assert not target.exists()


def test_deepfilter_mode_fails_clearly_when_local_assets_are_missing(tmp_path):
    source = tmp_path / "original.wav"
    source.write_bytes(b"original")

    try:
        enhance_for_transcription(
            source,
            tmp_path / "enhanced.wav",
            mode="deepfilter",
            deep_filter_executable=tmp_path / "missing-deep-filter",
            deep_filter_model=tmp_path / "missing-model.tar.gz",
        )
    except RuntimeError as exc:
        assert "binaire ou le modèle manque" in str(exc)
    else:
        raise AssertionError("Expected a helpful error for missing DeepFilterNet assets")


def test_deepfilter_uses_output_dir_cli_argument_and_converts_audio(tmp_path, monkeypatch):
    source = tmp_path / "original.wav"
    source.write_bytes(b"original audio" * 8)
    target = tmp_path / "enhanced.wav"
    executable = tmp_path / "deep-filter.exe"
    executable.write_bytes(b"fake executable")
    model = tmp_path / "model.tar.gz"
    model.write_bytes(b"fake model")
    commands = []

    def fake_popen(command, *args, **kwargs):
        commands.append(list(command))

        def create_output(cmd):
            if cmd[0] == "ffmpeg":
                Path(cmd[-1]).write_bytes(b"converted wav data" * 8)
                return
            # Model the current DeepFilterNet CLI contract and output file.
            assert "--output-dir" in cmd
            assert "--out-dir" not in cmd
            output_dir = Path(cmd[cmd.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "input_DeepFilterNet3.wav").write_bytes(b"denoised wav data" * 8)

        return FakeProcess(command, on_output=create_output)

    monkeypatch.setattr("seance.media.speech_enhancement.subprocess.Popen", fake_popen)
    result, selected = enhance_for_transcription(
        source,
        target,
        mode="deepfilter",
        ffmpeg="ffmpeg",
        deep_filter_executable=executable,
        deep_filter_model=model,
    )

    assert selected == "deepfilter"
    assert result == target
    assert target.is_file()
    assert target.stat().st_size > 44
    assert source.read_bytes() == b"original audio" * 8
    deepfilter_command = next(cmd for cmd in commands if cmd[0] == str(executable))
    assert deepfilter_command[deepfilter_command.index("--output-dir") + 1]
    assert "--compensate-delay" in deepfilter_command
