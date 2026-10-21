"""Servidor HTTP local de V.E.R.A.: solo 127.0.0.1, con token, cuerpo limitado y validación estricta."""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from vera.eventos import EventoInvalido, validar_evento

MAX_CUERPO = 4096


def crear_servidor(vera, token: str, puerto: int = 0) -> ThreadingHTTPServer:
    token_b = token.encode("utf-8")

    class Manejador(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):  # sin registro de accesos: podría contener datos de la planta
            pass

        def _responder(self, codigo, cuerpo):
            datos = json.dumps(cuerpo).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(datos)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(datos)

        def _autorizado(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):  # frena ataques de «DNS rebinding» desde un navegador
                return False
            return hmac.compare_digest((self.headers.get("X-Vera-Token") or "").encode("utf-8", "ignore"), token_b)

        def do_GET(self):
            if not self._autorizado():
                return self._responder(401, {"ok": False, "error": "no autorizado"})
            if self.path != "/v1/estado":
                return self._responder(404, {"ok": False, "error": "no existe"})
            self._responder(200, {"ok": True, **vera.estado()})

        def do_POST(self):
            if not self._autorizado():
                return self._responder(401, {"ok": False, "error": "no autorizado"})
            if self.path != "/v1/evento":
                return self._responder(404, {"ok": False, "error": "no existe"})
            try:
                largo = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self._responder(411, {"ok": False, "error": "falta Content-Length"})
            if not 0 < largo <= MAX_CUERPO:
                return self._responder(413, {"ok": False, "error": "cuerpo demasiado grande"})
            try:
                evento = validar_evento(json.loads(self.rfile.read(largo).decode("utf-8")))
            except (ValueError, UnicodeDecodeError, EventoInvalido) as ex:
                return self._responder(400, {"ok": False, "error": str(ex)[:80]})
            self._responder(202, {"ok": True, "resultado": vera.encolar(evento)})

    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    servidor.daemon_threads = True
    return servidor
