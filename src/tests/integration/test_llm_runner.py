from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from seance.llm import LLMCancelled, run_completion_resilient
from seance.runtime import AI_ENGINE_LOCK


class SharedCompletionTests(unittest.TestCase):
    def _make_fake_llama(self, root: Path, *, sleep: bool = False) -> tuple[Path, Path]:
        binary = root / ("fake_llama.py" if os.name != "nt" else "fake_llama.cmd")
        model = root / "model.gguf"
        model.write_bytes(b"test-model")
        if os.name == "nt":
            # This branch is not used in CI here, but keeps the helper understandable on Windows.
            binary.write_text(
                "@echo off\r\n"
                "if \"%1\"==\"--help\" (echo -cnv --conversation\necho -st --single-turn\necho -p --prompt\necho -sys --system-prompt\necho --jinja\necho --no-display-prompt\nexit /b 0)\r\n"
                "echo ## Synthese generale\r\necho La source confirme ce point [1].\r\n",
                encoding="utf-8",
            )
            return binary, model

        import sys

        binary.write_text(
            "#!" + sys.executable + "\n"
            "import sys, time\n"
            "if '--help' in sys.argv:\n"
            " print('-cnv, --conversation\\n-st, --single-turn\\n-p, --prompt\\n-sys, --system-prompt\\n--jinja\\n--no-display-prompt\\n--reasoning')\n"
            " raise SystemExit(0)\n"
            + ("time.sleep(5)\n" if sleep else "")
            + "print('## Synthèse générale\\nLa source confirme ce point [1].')\n",
            encoding="utf-8",
        )
        binary.chmod(0o755)
        return binary, model

    @unittest.skipIf(os.name == "nt", "The subprocess fixture uses a POSIX shebang.")
    def test_generates_with_shared_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary, model = self._make_fake_llama(root)
            answer, hit_limit = run_completion_resilient(
                binary, model, root, "Tu synthétises fidèlement.", "Réponds aux sources [1].",
                context=4096, max_tokens=256, retries=0, timeout_seconds=5,
            )
            self.assertFalse(hit_limit)
            self.assertIn("Synthèse générale", answer)
            self.assertIn("[1]", answer)

    @unittest.skipIf(os.name == "nt", "The subprocess fixture uses a POSIX shebang.")
    def test_llama_waits_for_the_shared_slot_used_by_whisper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary, model = self._make_fake_llama(root)
            completed = threading.Event()
            errors: list[BaseException] = []

            def run() -> None:
                try:
                    run_completion_resilient(
                        binary, model, root, "system", "user", context=4096,
                        max_tokens=256, retries=0, timeout_seconds=5,
                    )
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    completed.set()

            # Simulate a Whisper process holding the shared engine slot.
            AI_ENGINE_LOCK.acquire()
            thread = threading.Thread(target=run)
            try:
                thread.start()
                self.assertFalse(completed.wait(0.35), "llama.cpp must wait while Whisper owns the engine slot")
            finally:
                AI_ENGINE_LOCK.release()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "llama.cpp did not resume after the engine slot was released")
            self.assertFalse(errors, errors)

    @unittest.skipIf(os.name == "nt", "The subprocess fixture uses a POSIX shebang.")
    def test_concurrent_callers_never_run_two_llama_processes_at_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            model = root / "model.gguf"
            model.write_bytes(b"test-model")
            event_log = root / "events.log"
            binary = root / "fake_llama_serial.py"
            import sys
            binary.write_text(
                "#!" + sys.executable + "\n"
                "import sys, time\n"
                "if '--help' in sys.argv:\n"
                " print('--conversation\\n--single-turn\\n--system-prompt\\n--prompt\\n--jinja\\n--no-display-prompt')\n"
                " raise SystemExit(0)\n"
                f"log = {str(event_log)!r}\n"
                "with open(log, 'a', encoding='utf-8') as stream: stream.write('start\\n'); stream.flush()\n"
                "time.sleep(0.35)\n"
                "with open(log, 'a', encoding='utf-8') as stream: stream.write('end\\n'); stream.flush()\n"
                "print('Réponse stable')\n",
                encoding="utf-8",
            )
            binary.chmod(0o755)
            start_gate = threading.Barrier(3)
            errors: list[BaseException] = []

            def run() -> None:
                try:
                    start_gate.wait(timeout=2)
                    run_completion_resilient(
                        binary, model, root, "system", "user", context=4096,
                        max_tokens=256, retries=0, timeout_seconds=5,
                    )
                except BaseException as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=run) for _ in range(2)]
            for thread in threads:
                thread.start()
            start_gate.wait(timeout=2)
            for thread in threads:
                thread.join(timeout=5)
            self.assertFalse(any(thread.is_alive() for thread in threads), "LLM workers did not finish")
            self.assertFalse(errors, errors)
            events = event_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(events, ["start", "end", "start", "end"])

    @unittest.skipIf(os.name == "nt", "The subprocess fixture uses a POSIX shebang.")
    def test_cancellation_terminates_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            binary, model = self._make_fake_llama(root, sleep=True)
            cancel_event = threading.Event()
            errors: list[BaseException] = []

            def run() -> None:
                try:
                    run_completion_resilient(
                        binary, model, root, "system", "user",
                        context=4096, max_tokens=256, retries=0,
                        cancel_event=cancel_event, timeout_seconds=10,
                    )
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=run)
            thread.start()
            time.sleep(0.5)
            cancel_event.set()
            thread.join(timeout=4)
            self.assertFalse(thread.is_alive(), "generation did not stop after cancellation")
            self.assertTrue(errors)
            self.assertIsInstance(errors[0], LLMCancelled)
