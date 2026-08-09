"""Development validation entrypoint.

Run with:
    python -m slipform.devcheck
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _python_files() -> list[str]:
    ignored = {"__pycache__", ".venv", "venv", ".git"}
    files: list[str] = []
    for path in ROOT.rglob("*.py"):
        if any(part in ignored for part in path.parts):
            continue
        files.append(str(path.relative_to(ROOT)))
    return files


def _javascript_files() -> list[str]:
    files = [ROOT / "static" / "app.js"]
    files.extend((ROOT / "static" / "js").rglob("*.js"))
    return [str(path.relative_to(ROOT)) for path in files if path.exists()]


def _check_service_worker_assets() -> None:
    sw_path = ROOT / "static" / "sw.js"
    if not sw_path.exists():
        raise SystemExit("static/sw.js no existe")
    text = sw_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith('"/'):
            continue
        asset = stripped.split('"', 2)[1]
        if asset == "/":
            continue
        path = ROOT / "static" / asset.lstrip("/")
        if not path.exists():
            raise SystemExit(f"Asset cacheado inexistente: {asset}")


def _quoted_static_paths(text: str) -> set[str]:
    return set(re.findall(r'["\'](/(?:css|js)/[^"\']+)["\']', text))


def _check_frontend_assets() -> None:
    sw_path = ROOT / "static" / "sw.js"
    cached = _quoted_static_paths(sw_path.read_text(encoding="utf-8"))

    for css_file in (ROOT / "static" / "css").rglob("*.css"):
        text = css_file.read_text(encoding="utf-8")
        for asset in _quoted_static_paths(text):
            path = ROOT / "static" / asset.lstrip("/")
            if not path.exists():
                raise SystemExit(f"Import CSS inexistente en {css_file.relative_to(ROOT)}: {asset}")
            if asset not in cached:
                raise SystemExit(f"Import CSS fuera del cache offline: {asset}")

    for loader_name in ("app.js", "js/main.js"):
        loader_path = ROOT / "static" / loader_name
        if not loader_path.exists():
            continue
        for asset in _quoted_static_paths(loader_path.read_text(encoding="utf-8")):
            path = ROOT / "static" / asset.lstrip("/")
            if not path.exists():
                raise SystemExit(f"Script inexistente en {loader_name}: {asset}")
            if asset not in cached:
                raise SystemExit(f"Script fuera del cache offline: {asset}")


def main() -> None:
    py_files = _python_files()
    if py_files:
        _run([sys.executable, "-m", "py_compile", *py_files])

    _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])

    node = shutil.which("node")
    if node:
        for js_file in _javascript_files():
            _run([node, "--check", js_file])
    else:
        print("node no encontrado; se omite validacion JS")

    _check_service_worker_assets()
    _check_frontend_assets()

    print("devcheck OK")


if __name__ == "__main__":
    main()
