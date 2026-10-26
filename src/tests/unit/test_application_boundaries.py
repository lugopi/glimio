from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_import(code: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    src_path = str(PROJECT_ROOT / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-c", code], cwd=PROJECT_ROOT, env=env,
        capture_output=True, text=True, timeout=20, check=False,
    )


def test_cli_import_does_not_require_fastapi_or_import_web() -> None:
    result = _run_import(
        "import sys; import seance.cli; "
        "assert 'fastapi' not in sys.modules; assert 'web.app' not in sys.modules"
    )
    assert result.returncode == 0, result.stderr


def test_web_import_does_not_import_the_cli_entrypoint() -> None:
    result = _run_import(
        "import sys; import web.app; "
        "assert 'seance.cli' not in sys.modules"
    )
    assert result.returncode == 0, result.stderr
