import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

from core.auth import AuthError  # noqa: E402
from core.shared import EstadoCompartido, Ocupado  # noqa: E402


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data

    def json(self):
        return self._data


class ClienteFalso:
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    def _request(self, metodo, ruta, with_token=True, timeout=None, **kw):
        self.llamadas.append((ruta, kw.get("json"), timeout))
        return self.respuestas.pop(0)


class TestEstadoCompartido(unittest.TestCase):
    def test_publicar(self):
        c = ClienteFalso(Resp(200, 7))
        self.assertEqual(EstadoCompartido(c).publicar("ALBERT-01", {"a": 1}), 7)
        ruta, cuerpo, _ = c.llamadas[0]
        self.assertTrue(ruta.endswith("/rpc/publish_state"))
        self.assertEqual(cuerpo, {"p_node": "ALBERT-01", "p_state": {"a": 1}, "p_force": False})

    def test_ocupado_lleva_el_nombre(self):
        c = ClienteFalso(Resp(400, {"message": "OCUPADO:Pedro"}))
        with self.assertRaises(Ocupado) as cm:
            EstadoCompartido(c).publicar("ZENO-01", {})
        self.assertEqual(str(cm.exception), "OCUPADO:Pedro")
        self.assertIsInstance(cm.exception, AuthError)

    def test_sin_permiso(self):
        c = ClienteFalso(Resp(400, {"message": "SIN_PERMISO"}))
        with self.assertRaisesRegex(AuthError, "rol"):
            EstadoCompartido(c).publicar("ZENO-01", {})

    def test_error_generico_menciona_la_funcion(self):
        c = ClienteFalso(Resp(500, "no es json"))
        with self.assertRaisesRegex(AuthError, "publish_state"):
            EstadoCompartido(c).publicar("ZENO-01", {})

    def test_leer_solo_reenvia_lo_que_cambio(self):
        fila = lambda n, v, quien, cambio, est: {"node_id": n, "version": v, "publisher_name": quien,  # noqa: E731
                                                 "changed": cambio, "state": est}
        c = ClienteFalso(
            Resp(200, [fila("ALBERT-01", 3, "Pedro", True, {"x": 1}), fila("ZENO-01", 0, None, True, {})]),
            Resp(200, [fila("ALBERT-01", 3, "Pedro", False, None), fila("ZENO-01", 0, None, False, None)]),
        )
        e = EstadoCompartido(c)
        r1 = e.leer()
        self.assertEqual((r1["ALBERT-01"]["cambio"], r1["ALBERT-01"]["estado"]), (True, {"x": 1}))
        self.assertEqual(r1["ZENO-01"]["publicador"], "")
        self.assertFalse(r1["ZENO-01"]["cambio"])          # estado vacío = aún no hay datos
        self.assertEqual(e.conocidas, {"ALBERT-01": 3})    # solo recuerda lo que trajo datos
        r2 = e.leer()
        self.assertEqual(c.llamadas[1][1], {"p_known": {"ALBERT-01": 3}})
        self.assertFalse(r2["ALBERT-01"]["cambio"])
        self.assertEqual(r2["ALBERT-01"]["publicador"], "Pedro")

    def test_liberar_usa_timeout_corto(self):
        c = ClienteFalso(Resp(204, None))
        EstadoCompartido(c).liberar("ALBERT-01", timeout=2)
        self.assertEqual(c.llamadas[0][2], 2)


if __name__ == "__main__":
    unittest.main()
