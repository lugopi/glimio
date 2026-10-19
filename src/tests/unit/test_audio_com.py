from __future__ import annotations

import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from seance.audio import audio_com_apartment, record
from web.app import _device_names


class _FakeNativeFunction:
    def __init__(self, result=None):
        self.result = result
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class _FakeOle32:
    def __init__(self, init_result=0):
        self.CoInitializeEx = _FakeNativeFunction(init_result)
        self.CoUninitialize = _FakeNativeFunction(None)


class AudioComApartmentTests(unittest.TestCase):
    def test_non_windows_is_a_noop(self) -> None:
        with patch("seance.audio.os.name", "posix"):
            with audio_com_apartment():
                self.assertTrue(True)

    def test_successful_initialization_is_balanced(self) -> None:
        ole32 = _FakeOle32(0)  # S_OK
        with patch("seance.audio.os.name", "nt"), patch(
            "seance.audio.ctypes.WinDLL", return_value=ole32, create=True
        ):
            with audio_com_apartment():
                pass
        self.assertEqual(len(ole32.CoInitializeEx.calls), 1)
        self.assertEqual(len(ole32.CoUninitialize.calls), 1)
        self.assertEqual(ole32.CoInitializeEx.calls[0], (None, 0))

    def test_s_false_initialization_is_also_balanced(self) -> None:
        ole32 = _FakeOle32(1)  # S_FALSE still increments COM's init count
        with patch("seance.audio.os.name", "nt"), patch(
            "seance.audio.ctypes.WinDLL", return_value=ole32, create=True
        ):
            with audio_com_apartment():
                pass
        self.assertEqual(len(ole32.CoUninitialize.calls), 1)

    def test_changed_apartment_mode_is_not_uninitialized_by_this_scope(self) -> None:
        ole32 = _FakeOle32(0x80010106)  # RPC_E_CHANGED_MODE
        with patch("seance.audio.os.name", "nt"), patch(
            "seance.audio.ctypes.WinDLL", return_value=ole32, create=True
        ):
            with audio_com_apartment():
                pass
        self.assertEqual(len(ole32.CoUninitialize.calls), 0)

    def test_com_initialization_failure_is_reported(self) -> None:
        ole32 = _FakeOle32(0x800401F0)  # CO_E_NOTINITIALIZED / failed HRESULT
        with patch("seance.audio.os.name", "nt"), patch(
            "seance.audio.ctypes.WinDLL", return_value=ole32, create=True
        ):
            with self.assertRaisesRegex(OSError, "0x800401F0"):
                with audio_com_apartment():
                    pass
        self.assertEqual(len(ole32.CoUninitialize.calls), 0)

    def test_device_enumeration_imports_soundcard_before_com_scope(self) -> None:
        order: list[str] = []
        backend = SimpleNamespace(
            all_microphones=lambda include_loopback=False: [SimpleNamespace(name="USB Mic")],
            all_speakers=lambda: [SimpleNamespace(name="Speakers")],
        )

        @contextmanager
        def fake_com_scope():
            order.append("com-enter")
            yield
            order.append("com-exit")

        def fake_soundcard():
            order.append("soundcard-import")
            return backend

        with patch("web.app._soundcard", side_effect=fake_soundcard), patch(
            "web.app.audio_com_apartment", side_effect=fake_com_scope
        ):
            result = _device_names()

        self.assertEqual(order, ["soundcard-import", "com-enter", "com-exit"])
        self.assertEqual(result, {
            "microphones": ["USB Mic"],
            "outputs": ["Speakers"],
            "microphone_devices": [{"id": "", "key": "microphone:0:USB Mic", "name": "USB Mic"}],
            "output_devices": [{"id": "", "key": "output:0:Speakers", "name": "Speakers"}],
        })


    def test_device_enumeration_preserves_endpoint_ids_for_unambiguous_selection(self) -> None:
        backend = SimpleNamespace(
            all_microphones=lambda include_loopback=False: [SimpleNamespace(id="mic-42", name="Bluetooth Headset")],
            all_speakers=lambda: [SimpleNamespace(id="spk-42", name="Bluetooth Headset")],
        )

        with patch("web.app._soundcard", return_value=backend), patch("web.app.audio_com_apartment"):
            result = _device_names()

        self.assertEqual(result["microphone_devices"], [{"id": "mic-42", "key": "mic-42", "name": "Bluetooth Headset"}])
        self.assertEqual(result["output_devices"], [{"id": "spk-42", "key": "spk-42", "name": "Bluetooth Headset"}])

    def test_record_imports_backend_before_scoped_com_initialization(self) -> None:
        order: list[str] = []

        @contextmanager
        def fake_com_scope():
            order.append("com-enter")
            yield
            order.append("com-exit")

        def fake_soundcard():
            order.append("soundcard-import")
            return object()

        def fake_record_impl(*args, **kwargs):
            order.append("record-impl")

        from seance import audio
        args = SimpleNamespace(capture_microphone=True, capture_windows=False)
        with patch.object(audio, "_soundcard", side_effect=fake_soundcard), patch.object(
            audio, "audio_com_apartment", side_effect=fake_com_scope
        ), patch.object(audio, "_record_impl", side_effect=fake_record_impl):
            record(args)

        self.assertEqual(order, ["soundcard-import", "com-enter", "record-impl", "com-exit"])


if __name__ == "__main__":
    unittest.main()
