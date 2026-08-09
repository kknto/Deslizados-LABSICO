from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CACHE = DIST / "cache"
PACKAGE_NAME = "SeybaPlaya-Deslizamiento-Portable"
PYTHON_VERSION = "3.12.10"
PYTHON_ZIP = f"python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/{PYTHON_ZIP}"

RUNTIME_DIRS = [
    "slipform",
    "static",
    "data",
    "Bitacora_escrita",
]

RUNTIME_FILES = [
    "README_LITE.md",
    "ARCHITECTURE.md",
    "DISTRIBUCION.md",
    "API_CONTRACTS.md",
    "UX_UI_QUALITY.md",
    "Curvas HRP.xlsx",
    "Prediccion_Arrhenius_Campo.xlsx",
]

EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "test-results",
    "playwright",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Construye un paquete portable Windows para compartir la app.")
    parser.add_argument("--no-zip", action="store_true", help="Solo crea la carpeta portable, sin comprimir.")
    parser.add_argument("--include-dev", action="store_true", help="Incluye pruebas y archivos de desarrollo.")
    args = parser.parse_args()

    DIST.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    package_dir = DIST / PACKAGE_NAME
    ensure_safe_dist_path(package_dir)
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir()

    copy_runtime(package_dir, include_dev=args.include_dev)
    install_python_runtime(package_dir)
    copy_tesseract_runtime(package_dir)
    copy_windows_helpers(package_dir)
    write_version_file(package_dir)

    if args.no_zip:
        print(package_dir)
        return 0

    zip_path = DIST / f"{PACKAGE_NAME}-{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    if zip_path.exists():
        zip_path.unlink()
    make_zip(package_dir, zip_path)
    print(zip_path)
    return 0


def ensure_safe_dist_path(path: Path) -> None:
    resolved = path.resolve()
    dist_resolved = DIST.resolve()
    if resolved == dist_resolved or dist_resolved not in resolved.parents:
        raise RuntimeError(f"Ruta de salida insegura: {resolved}")


def copy_runtime(package_dir: Path, include_dev: bool = False) -> None:
    for name in RUNTIME_DIRS:
        source = ROOT / name
        target = package_dir / name
        if not source.exists():
            continue
        shutil.copytree(source, target, ignore=ignore_dev_files if not include_dev else None)

    for name in RUNTIME_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, package_dir / name)

    if include_dev:
        for name in ["tests", "tests-ui", "package.json", "package-lock.json", "playwright.config.js"]:
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, package_dir / name, ignore=ignore_dev_files)
            elif source.exists():
                shutil.copy2(source, package_dir / name)


def ignore_dev_files(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(directory) / name
        if name in EXCLUDED_DIR_NAMES:
            ignored.add(name)
        elif path.suffix.lower() in EXCLUDED_SUFFIXES:
            ignored.add(name)
    return ignored


def install_python_runtime(package_dir: Path) -> None:
    archive = CACHE / PYTHON_ZIP
    if not archive.exists():
        print(f"Descargando Python portable {PYTHON_VERSION}...")
        download_file(PYTHON_URL, archive)

    runtime_python = package_dir / "runtime" / "python"
    runtime_python.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(runtime_python)

    configure_embedded_python_path(runtime_python)

    test_python = runtime_python / "python.exe"
    if not test_python.exists():
        raise RuntimeError("No se pudo preparar runtime\\python\\python.exe")


def copy_tesseract_runtime(package_dir: Path) -> None:
    source = find_tesseract_runtime()
    if not source:
        print("Tesseract OCR no encontrado; el paquete usara OCR solo si el equipo destino lo tiene instalado.")
        return
    target = package_dir / "runtime" / "tesseract"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=ignore_dev_files)


def find_tesseract_runtime() -> Path | None:
    candidates = [
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate).parent
    return None


def download_file(url: str, target: Path) -> None:
    try:
        urllib.request.urlretrieve(url, target)
        return
    except Exception as exc:
        print(f"Descarga con urllib fallo: {exc}")
        print("Intentando descarga con PowerShell...")

    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"Invoke-WebRequest -Uri {url!r} -OutFile {str(target)!r} -UseBasicParsing",
    ]
    subprocess.run(command, check=True)


def configure_embedded_python_path(runtime_python: Path) -> None:
    pth_files = list(runtime_python.glob("python*._pth"))
    if not pth_files:
        return
    pth = pth_files[0]
    lines = pth.read_text(encoding="utf-8").splitlines()
    if "..\\.." not in lines:
        insert_at = 0
        for index, line in enumerate(lines):
            if line.strip() == ".":
                insert_at = index + 1
                break
        lines.insert(insert_at, "..\\..")
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_windows_helpers(package_dir: Path) -> None:
    helper_dir = ROOT / "packaging" / "windows"
    for path in helper_dir.glob("*"):
        if path.is_file():
            shutil.copy2(path, package_dir / path.name)


def write_version_file(package_dir: Path) -> None:
    content = "\n".join(
        [
            "Control De Deslizamiento - Seybaplaya",
            f"Paquete generado: {datetime.now().isoformat(timespec='seconds')}",
            f"Python portable: {PYTHON_VERSION}",
            "Entrada: INICIAR_PROGRAMA.bat",
            "Base de datos: data\\slipform.sqlite",
            "",
        ]
    )
    (package_dir / "VERSION.txt").write_text(content, encoding="utf-8")


def make_zip(package_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in package_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(package_dir.parent))


if __name__ == "__main__":
    raise SystemExit(main())
