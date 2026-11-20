from __future__ import annotations

import functools
import http.server
import socket
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from .cesty import WEB, je_uvnitr


class VerejnyHandler(http.server.SimpleHTTPRequestHandler):
    server_version = "ZnalostniDatabaze/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def list_directory(self, path):
        self._ceska_chyba(404, "Výpis složky není povolen.")
        return None

    def _ceska_chyba(self, kod: int, text: str) -> None:
        telo = ("<!doctype html><html lang=\"cs\"><meta charset=\"utf-8\">"
                f"<title>Chyba {kod}</title><h1>Chyba {kod}</h1><p>{text}</p></html>").encode("utf-8")
        self.send_response(kod, "Not Found" if kod == 404 else "Method Not Allowed")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(telo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(telo)

    def translate_path(self, path: str) -> str:
        prelozena = Path(super().translate_path(path)).resolve(strict=False)
        if not je_uvnitr(prelozena, WEB):
            return str(WEB / "__neexistuje__")
        try:
            if prelozena.exists() and prelozena.is_symlink():
                return str(WEB / "__neexistuje__")
        except OSError:
            return str(WEB / "__neexistuje__")
        return str(prelozena)

    def do_POST(self):
        self._ceska_chyba(405, "Nahrávání na server není povoleno.")

    def end_headers(self):
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

    def log_message(self, format, *args):
        print("Server:", format % args)


def najdi_port() -> int | None:
    for port in range(8765, 8770):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test:
            try:
                test.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


def vytvor_server(port: int | None = None) -> http.server.ThreadingHTTPServer:
    port = najdi_port() if port is None else port
    if port is None:
        raise OSError("Všechny porty 8765 až 8769 jsou obsazené.")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), VerejnyHandler)
    server.daemon_threads = True
    return server


def spust_server() -> None:
    server = vytvor_server()
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Databáze je dostupná na adrese: {url}")
    print("Server zastavíte klávesami Ctrl+C. Potom se vrátíte do menu.")
    try:
        if not webbrowser.open(url):
            print("Prohlížeč se nepodařilo otevřít. Zkopírujte uvedenou adresu ručně.")
    except Exception:
        print("Prohlížeč se nepodařilo otevřít. Zkopírujte uvedenou adresu ručně.")
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("Server byl zastaven.")
    finally:
        server.server_close()
