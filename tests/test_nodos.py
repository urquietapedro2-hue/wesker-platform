import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

from core.auth import AuthError  # noqa: E402
from core.nodos import Endpoint, RegistroNodos, validar_endpoint  # noqa: E402
from core.secretos_local import Almacen, CifradorDPAPI, SecretosError, destruir  # noqa: E402


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data

    def json(self):
        if self._data is None:
            raise ValueError("sin json")
        return self._data


class ClienteFalso:
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def _request(self, metodo, ruta, **kw):
        self.llamadas.append((ruta, kw.get("json")))
        return self.respuestas.pop(0)


class TestValidacion(unittest.TestCase):
    def test_endpoint_valido(self):
        self.assertEqual(validar_endpoint("ZENO-01", "  Casa ", " 192.0.2.10 ", "65432"), Endpoint("ZENO-01", "Casa", "192.0.2.10", 65432))

    def test_entradas_invalidas(self):
        malos = [("OTRO", "Casa", "192.0.2.10", 1), ("ZENO-01", "", "192.0.2.10", 1), ("ZENO-01", "x" * 31, "192.0.2.10", 1),
                 ("ZENO-01", "Ca\nsa", "192.0.2.10", 1), ("ZENO-01", "Casa\x00", "192.0.2.10", 1), ("ZENO-01", "Casa", "999.1.1.1", 1), ("ZENO-01", "Casa", "casa.local", 1),
                 ("ZENO-01", "Casa", "", 1), ("ZENO-01", "Casa", "127.0.0.1", 1), ("ZENO-01", "Casa", "0.0.0.0", 1),
                 ("ZENO-01", "Casa", "224.0.0.1", 1), ("ZENO-01", "Casa", "::1", 1), ("ZENO-01", "Casa", "fe80::1", 1),
                 ("ZENO-01", "Casa", "192.0.2.10", 0), ("ZENO-01", "Casa", "192.0.2.10", 70000), ("ZENO-01", "Casa", "192.0.2.10", "abc"),
                 ("ZENO-01", "Casa", None, None)]
        for args in malos:
            with self.assertRaises(AuthError, msg=str(args)):
                validar_endpoint(*args)


class TestRegistro(unittest.TestCase):
    def test_listar_ordena_y_descarta_filas_raras(self):
        c = ClienteFalso(Resp(200, [{"node_id": "ZENO-01", "red": "Universidad", "ip": "192.0.2.20", "puerto": 65432},
                                    {"node_id": "ALBERT-01", "red": "Casa", "ip": "192.0.2.30/32", "puerto": 5000},
                                    {"node_id": "ZENO-01", "red": "Casa", "ip": "192.0.2.10", "puerto": 65432},
                                    {"node_id": "ZENO-01"}, {"node_id": "ZENO-01", "red": "X", "ip": "i", "puerto": "no"}, "basura"]))
        self.assertEqual(RegistroNodos(c).listar(), [Endpoint("ALBERT-01", "Casa", "192.0.2.30", 5000),
                                                     Endpoint("ZENO-01", "Casa", "192.0.2.10", 65432),
                                                     Endpoint("ZENO-01", "Universidad", "192.0.2.20", 65432)])

    def test_guardar_envia_datos_ya_validados_y_borrar(self):
        c = ClienteFalso(Resp(204), Resp(204))
        r = RegistroNodos(c)
        r.guardar("ZENO-01", " Casa ", "192.0.2.10", "65432")
        r.borrar("ZENO-01", "Casa")
        self.assertTrue(c.llamadas[0][0].endswith("/rpc/set_endpoint"))
        self.assertEqual(c.llamadas[0][1], {"p_node": "ZENO-01", "p_red": "Casa", "p_ip": "192.0.2.10", "p_puerto": 65432})
        self.assertTrue(c.llamadas[1][0].endswith("/rpc/delete_endpoint"))

    def test_guardar_no_llega_al_servidor_si_los_datos_son_invalidos(self):
        c = ClienteFalso()
        with self.assertRaises(AuthError):
            RegistroNodos(c).guardar("ZENO-01", "Casa", "no-es-ip", 65432)
        self.assertEqual(c.llamadas, [])

    def test_errores_del_servidor(self):
        with self.assertRaisesRegex(AuthError, "Admin"):
            RegistroNodos(ClienteFalso(Resp(400, {"message": "SIN_PERMISO"}))).listar()
        with self.assertRaisesRegex(AuthError, "set_endpoint"):
            RegistroNodos(ClienteFalso(Resp(404, None))).guardar("ZENO-01", "Casa", "192.0.2.10", 1)


class CifradorFalso:
    def __init__(self, falla=False): self.falla = falla
    def cifrar(self, d): return bytes(b ^ 0x5A for b in d)[::-1]

    def descifrar(self, d):
        if self.falla:
            raise SecretosError("x")
        return bytes(b ^ 0x5A for b in d[::-1])


class TestTokenCifrado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta = Path(self.tmp.name) / "hmi_secretos.dat"
        self.a = Almacen(CifradorFalso(), self.ruta)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ciclo_y_sin_texto_plano(self):
        self.assertFalse(self.a.hay_token())
        self.a.guardar_token_zeno("  Tok-en_de.prueba1234 ")
        self.assertEqual(self.a.token_zeno(), "Tok-en_de.prueba1234")
        self.assertNotIn(b"prueba1234", self.ruta.read_bytes())
        self.assertTrue(self.a.hay_token())
        self.a.borrar_token_zeno()
        self.assertFalse(self.a.hay_token())

    def test_tokens_invalidos_no_se_guardan(self):
        for malo in ("", "corto", "x" * 201, "con espacio dentro1", "con,coma12345", "salto\nlinea1234", None):
            with self.assertRaises(SecretosError, msg=str(malo)):
                self.a.guardar_token_zeno(malo)
        self.assertFalse(self.ruta.exists())

    def test_otra_cuenta_o_archivo_danado(self):
        self.a.guardar_token_zeno("TokenDePrueba-123")
        ajeno = Almacen(CifradorFalso(falla=True), self.ruta)
        with self.assertRaises(SecretosError):
            ajeno.token_zeno()
        self.assertFalse(ajeno.hay_token())                 # la interfaz no se rompe: solo dice «sin token»
        self.ruta.write_bytes(b"basura")
        with self.assertRaises(SecretosError):
            self.a.token_zeno()

    def test_dpapi_solo_en_windows(self):
        if sys.platform == "win32":
            self.skipTest("en Windows sí existe")
        with self.assertRaises(SecretosError):
            CifradorDPAPI()

    def test_destruir_borra_el_archivo_importado(self):
        f = Path(self.tmp.name) / "zeno_token"
        f.write_text("TokenDePrueba-123", encoding="utf-8")
        destruir(f)
        self.assertFalse(f.exists())


if __name__ == "__main__":
    unittest.main()
