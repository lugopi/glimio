"""Portable audio-device discovery shared by the CLI and Web adapters."""
from __future__ import annotations
from collections.abc import Callable
from typing import Any


def list_audio_devices(
    *, soundcard_loader: Callable[[], Any] | None = None,
    com_scope: Callable[[], Any] | None = None,
) -> dict[str, list[Any]]:
    """Return display-name lists and stable keys for input/output devices.

    Optional callables are dependency-injection points for adapter tests; defaults
    are imported lazily so other CLI commands never import the audio backend.
    """
    if soundcard_loader is None or com_scope is None:
        from seance.media.audio import _soundcard, audio_com_apartment
        soundcard_loader = soundcard_loader or _soundcard
        com_scope = com_scope or audio_com_apartment
    sc = soundcard_loader()
    with com_scope():
        microphones = list(sc.all_microphones(include_loopback=False))
        outputs = list(sc.all_speakers())
    def record(device: Any, index: int, kind: str) -> dict[str, str]:
        device_id = str(getattr(device, "id", "") or "")
        name = str(device.name)
        return {"id": device_id, "key": device_id or f"{kind}:{index}:{name}", "name": name}
    return {
        "microphones": [str(item.name) for item in microphones],
        "outputs": [str(item.name) for item in outputs],
        "microphone_devices": [record(item, index, "microphone") for index, item in enumerate(microphones)],
        "output_devices": [record(item, index, "output") for index, item in enumerate(outputs)],
    }
