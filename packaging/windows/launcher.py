from __future__ import annotations

import argparse
import os
import socket
import sys
import traceback
import webbrowser
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, value: str) -> int:
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        return len(value)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def find_app_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in [current, *current.parents]:
        if (candidate / "slipform").is_dir() and (candidate / "static").is_dir():
            return candidate
    return current


APP_ROOT = find_app_root()
LOG_DIR = APP_ROOT / "logs"


def prepare_environment() -> Path:
    os.chdir(APP_ROOT)
    sys.path.insert(0, str(APP_ROOT))
    (APP_ROOT / "data").mkdir(exist_ok=True)
    (APP_ROOT / "data" / "backups").mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"inicio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file = log_path.open("a", encoding="utf-8")
    sys.stdout = Tee(sys.__stdout__, log_file)
    sys.stderr = Tee(sys.__stderr__, log_file)
    return log_path


def find_available_port(start: int, end: int, host: str = "127.0.0.1") -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No hay puertos disponibles entre {start} y {end}.")


def check_installation() -> None:
    required = [
        APP_ROOT / "slipform",
        APP_ROOT / "static",
        APP_ROOT / "static" / "index.html",
        APP_ROOT / "data",
    ]
    missing = [str(path.relative_to(APP_ROOT)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Faltan archivos o carpetas: " + ", ".join(missing))

    from slipform.http.legacy_server import DB_PATH
    from slipform.db import connect, init_db

    with connect(DB_PATH) as conn:
        init_db(conn)


def run_server(open_browser: bool = True) -> None:
    from slipform.http.legacy_server import SlipformHandler

    start_port = int(os.environ.get("SLIPFORM_PORT_START", "8010"))
    end_port = int(os.environ.get("SLIPFORM_PORT_END", "8020"))
    host = os.environ.get("SLIPFORM_HOST", "127.0.0.1")
    port = find_available_port(start_port, end_port, host)
    url = f"http://{host}:{port}"

    server = ThreadingHTTPServer((host, port), SlipformHandler)
    print()
    print("==============================================================")
    print(" Control De Deslizamiento - Seybaplaya")
    print("==============================================================")
    print()
    if port != start_port:
        print(f"El puerto {start_port} estaba ocupado. Se usara: {url}")
    else:
        print(f"Servidor iniciado en: {url}")
    print()
    print("No cierres esta ventana mientras uses el programa.")
    print("Para cerrar, presiona Ctrl+C o cierra esta ventana.")
    print()

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Cerrando programa...")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Arrancador portable del Control De Deslizamiento.")
    parser.add_argument("--check", action="store_true", help="Valida el paquete sin iniciar el servidor.")
    parser.add_argument("--no-browser", action="store_true", help="Inicia sin abrir el navegador.")
    args = parser.parse_args()

    log_path = prepare_environment()
    try:
        print(f"Carpeta del programa: {APP_ROOT}")
        print(f"Log de inicio: {log_path}")
        check_installation()
        if args.check:
            port = find_available_port(
                int(os.environ.get("SLIPFORM_PORT_START", "8010")),
                int(os.environ.get("SLIPFORM_PORT_END", "8020")),
                os.environ.get("SLIPFORM_HOST", "127.0.0.1"),
            )
            print(f"diagnostico-ok puerto-disponible={port}")
            return 0
        no_browser = args.no_browser or os.environ.get("SLIPFORM_NO_BROWSER") == "1"
        run_server(open_browser=not no_browser)
        return 0
    except Exception:
        print()
        print("No se pudo iniciar el programa.")
        print("Revisa el mensaje tecnico siguiente o comparte el archivo de log.")
        print()
        traceback.print_exc()
        print()
        print(f"Log guardado en: {log_path}")
        try:
            input("Presiona Enter para cerrar esta ventana...")
        except EOFError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
