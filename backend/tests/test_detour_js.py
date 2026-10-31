"""Alternativ yol seçimi (brauzer JS-i) Node ilə yoxlanır; Node yoxdursa keçilir."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node yoxdur")
def test_detour_js():
    f = Path(__file__).parent / "detour.test.js"
    r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert "detour ok" in r.stdout
