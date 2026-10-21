import http.server
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

from core.vera_cliente import ClienteVera  # noqa: E402

# Debe coincidir con vera/vera/eventos.py (CONTRATO.md): si un código nuevo no está allí, V.E.R.A. lo rechaza.
CODIGOS_CONTRATO = {"sesion_iniciada", "login_fallo", "nodo_en_linea", "nodo_sin_senal", "nube_perdida",
                    "nube_restablecida", "error_publicacion", "estado_invalido"}


class ServidorFalso:
    """Imita a V.E.R.A.: acepta solo con el token correcto y guarda lo recibido."""

    def __init__(self, token="tok", codigo=202):
        self.recibidos, token_ok, codigo_resp = [], token, codigo
        recibidos = self.recibidos

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                cuerpo = self.rfile.read(int(self.headers["Content-Length"]))
                recibidos.append((self.path, self.headers.get("X-Vera-Token"), json.loads(cuerpo)))
                self.send_response(codigo_resp if self.headers.get("X-Vera-Token") == token_ok else 401)
                self.send_header("Content-Length", "0")
                self.end_headers()

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.puerto = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestClienteVera(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "vera_local.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_sin_vera_corriendo_no_pasa_nada(self):
        c = ClienteVera(ruta=self.cfg)
        self.assertFalse(c.enviar("nube_perdida"))  # no hay archivo: ni siquiera abre un hilo
        self.assertFalse(c._post({"codigo": "nube_perdida"}))

    def test_archivos_de_configuracion_malos_se_ignoran(self):
        c = ClienteVera(ruta=self.cfg)
        for contenido in ("no json", "[1]", json.dumps({"puerto": "80", "token": "x"}), json.dumps({"puerto": 0, "token": "x"}),
                          json.dumps({"puerto": 99999, "token": "x"}), json.dumps({"puerto": True, "token": "x"}),
                          json.dumps({"puerto": 5000, "token": ""}), json.dumps({"puerto": 5000})):
            self.cfg.write_text(contenido, encoding="utf-8")
            self.assertIsNone(c._config(), contenido)

    def test_entrega_el_evento_con_el_token_y_el_formato_del_contrato(self):
        srv = ServidorFalso("tok-secreto")
        try:
            self.cfg.write_text(json.dumps({"puerto": srv.puerto, "token": "tok-secreto"}), encoding="utf-8")
            self.assertTrue(ClienteVera(ruta=self.cfg)._post({"v": 1, "codigo": "nube_perdida"}))
            ruta, token, cuerpo = srv.recibidos[0]
            self.assertEqual((ruta, token, cuerpo["codigo"]), ("/v1/evento", "tok-secreto", "nube_perdida"))
        finally:
            srv.cerrar()

    def test_enviar_en_segundo_plano_llega(self):
        srv = ServidorFalso("t")
        try:
            self.cfg.write_text(json.dumps({"puerto": srv.puerto, "token": "t"}), encoding="utf-8")
            self.assertTrue(ClienteVera(ruta=self.cfg).enviar("sesion_iniciada", usuario="Ana", datos={"rol": "ADMIN"}))
            for _ in range(100):
                if srv.recibidos:
                    break
                threading.Event().wait(0.02)
            self.assertEqual(srv.recibidos[0][2], {"v": 1, "codigo": "sesion_iniciada", "nivel": "info", "nodo": "",
                                                   "usuario": "Ana", "datos": {"rol": "ADMIN"}})
        finally:
            srv.cerrar()

    def test_token_incorrecto_o_servidor_caido_devuelven_false_sin_excepcion(self):
        srv = ServidorFalso("bueno")
        try:
            self.cfg.write_text(json.dumps({"puerto": srv.puerto, "token": "malo"}), encoding="utf-8")
            self.assertFalse(ClienteVera(ruta=self.cfg)._post({"codigo": "nube_perdida"}))
        finally:
            srv.cerrar()
        self.assertFalse(ClienteVera(ruta=self.cfg, timeout=0.3)._post({"codigo": "nube_perdida"}))  # ya no hay nadie

    def test_los_codigos_que_usa_el_hmi_existen_en_el_contrato(self):
        usados = set()
        for p in (Path(__file__).resolve().parent.parent / "desktop" / "ui").glob("*.py"):
            texto = p.read_text(encoding="utf-8")
            usados |= set(re.findall(r'self\.evento\([^)]*?,\s*"([a-z_]+)"(?:,|\))', texto))
            usados |= set(re.findall(r'vera\.enviar\(\s*"([a-z_]+)"', texto))
        self.assertTrue(usados, "no se encontró ningún código: ¿cambió el formato de las llamadas?")
        self.assertLessEqual(usados, CODIGOS_CONTRATO, usados - CODIGOS_CONTRATO)

    def test_desktop_no_importa_codigo_de_vera(self):
        for p in (Path(__file__).resolve().parent.parent / "desktop").rglob("*.py"):
            if "twins" in p.parts:
                continue
            self.assertIsNone(re.search(r"^\s*(?:from|import)\s+vera\b", p.read_text(encoding="utf-8"), re.M), str(p))


if __name__ == "__main__":
    unittest.main()
