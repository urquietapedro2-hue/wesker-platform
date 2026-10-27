"""El cliente del HMI contra el servidor REAL de Zeno (zeno/servidor.py con hardware falso)."""
import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "desktop"))
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "zeno" / "tests"))

try:
    from falsos import FakeCamara, FakeGPIO, hardware_prueba, ruta_prueba  # noqa: E402
    from zeno import config as cfg_zeno  # noqa: E402
    from zeno.logica import formatear_telemetria  # noqa: E402
    from zeno.servidor import ServidorControl  # noqa: E402
    HAY_ZENO = True
except ImportError:
    HAY_ZENO = False

from core.zeno_enlace import Candidato, EnlaceZeno, parsear_telem, probar  # noqa: E402

TOKEN = "TokenDePrueba-123"


def esperar(cond, seg=4.0):
    fin = time.monotonic() + seg
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipUnless(HAY_ZENO, "no está la carpeta zeno/")
class Base(unittest.TestCase):
    token = TOKEN

    def levantar(self, puerto=0, vigilancia=2.0):
        gpio = FakeGPIO()
        hw = hardware_prueba(gpio)
        nav = ruta_prueba(hw)
        srv = ServidorControl(hw, nav, FakeCamara(), self.token, cal=hw.cal, pan=nav.pan, host="127.0.0.1", puerto=puerto,
                              vigilancia_s=vigilancia)
        srv.iniciar()
        self.recursos.append(srv)
        return srv, hw, gpio

    def setUp(self):
        self.recursos = []

    def tearDown(self):
        for r in reversed(self.recursos):
            (r.detener if hasattr(r, "detener") else r.close)()

    def enlace(self, candidatos, token=TOKEN, **kw):
        e = EnlaceZeno(candidatos, token, esperas=kw.pop("esperas", (0.05,)), **kw)
        self.recursos.append(e)
        e.iniciar()
        return e


class TestTelemetria(unittest.TestCase):
    def test_lo_que_manda_zeno_lo_entiende_el_hmi(self):
        linea = formatear_telemetria("ESTACION", 0.0, 35.0, (1, 0, 1, 0, 1), "ESTACION_DESCARGA", "ESTACION_2") if HAY_ZENO else \
            "TELEM:ESTACION,0,35.0,1,0,1,0,1,ESTACION_DESCARGA,ESTACION_2\n"
        t = parsear_telem(linea.strip())
        self.assertEqual(t, {"dir": "ESTACION", "pwm": 0, "dist": 35.0, "sens": [1, 0, 1, 0, 1], "sub": "ESTACION_DESCARGA", "qr": "ESTACION_2"})

    def test_lineas_invalidas_se_descartan_sin_excepciones(self):
        for malo in ("", "PONG", "HELLO:ZENO-01,3.0.0,V2", "TELEM:", "TELEM:F,50", "TELEM:F,50,35.0,0,0,0,0,0,SEGUIMIENTO",
                     "TELEM:X,50,35.0,0,0,0,0,0,SEGUIMIENTO,NINGUNO", "TELEM:F,500,35.0,0,0,0,0,0,SEGUIMIENTO,NINGUNO",
                     "TELEM:F,50,abc,0,0,0,0,0,SEGUIMIENTO,NINGUNO", "TELEM:F,50,35.0,0,0,2,0,0,SEGUIMIENTO,NINGUNO",
                     "TELEM:F,50,-1,0,0,0,0,0,SEGUIMIENTO,NINGUNO", "TELEM:F,50,35.0,0,0,0,0,0,SEGUIMIENTO,NINGUNO,EXTRA"):
            self.assertIsNone(parsear_telem(malo), malo)

    def test_textos_largos_se_recortan(self):
        t = parsear_telem("TELEM:F,50,35.0,0,0,0,0,0," + "A" * 200 + "," + "B" * 200)
        self.assertEqual((len(t["sub"]), len(t["qr"])), (30, 24))


class TestEnlace(Base):
    def test_conecta_se_autentica_y_recibe_telemetria(self):
        srv, hw, gpio = self.levantar()
        e = self.enlace([Candidato("Casa", "127.0.0.1", srv.puerto)])
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado"))
        s = e.snapshot()
        self.assertTrue(esperar(lambda: e.snapshot()["modo"] == "AUTO"))      # Zeno informa su modo al conectar
        self.assertEqual((s["red"], s["version"]), ("Casa", "4.1.0"))
        self.assertEqual(s["telemetria"]["dir"], "S")
        self.assertLess(s["edad"], 1.0)

    def test_token_incorrecto_se_rechaza_y_no_se_reintenta(self):
        srv, hw, gpio = self.levantar()
        e = self.enlace([Candidato("Casa", "127.0.0.1", srv.puerto)], token="equivocado")
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "rechazado"))
        time.sleep(0.4)
        self.assertEqual(e.snapshot()["estado"], "rechazado")
        self.assertFalse(e._hilo.is_alive())          # reintentar con el mismo token equivocado no tiene sentido

    def test_sin_token_contra_un_zeno_con_token_tambien_se_rechaza(self):
        srv, hw, gpio = self.levantar()
        e = self.enlace([Candidato("Casa", "127.0.0.1", srv.puerto)], token="")
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] in ("rechazado", "reintentando")))
        self.assertIsNone(e.snapshot()["telemetria"])

    def test_enviar_comandos_mueve_a_zeno_y_solo_si_hay_enlace(self):
        srv, hw, gpio = self.levantar()
        e = self.enlace([Candidato("Casa", "127.0.0.1", srv.puerto)])
        self.assertFalse(e.enviar("MODE,MANUAL"))      # todavía no está conectado
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado"))
        self.assertTrue(e.enviar("MODE,MANUAL"))
        self.assertTrue(e.enviar("F,40"))
        self.assertTrue(esperar(lambda: gpio.pwms[cfg_zeno.PIN_RPWM].duty == 40))
        self.assertTrue(esperar(lambda: e.snapshot()["telemetria"]["dir"] == "F"))

    def test_el_latido_mantiene_a_zeno_en_marcha_mas_alla_de_su_vigilancia(self):
        srv, hw, gpio = self.levantar(vigilancia=1.5)
        e = self.enlace([Candidato("Casa", "127.0.0.1", srv.puerto)])
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado"))
        e.enviar("MODE,MANUAL")
        e.enviar("F,40")
        self.assertTrue(esperar(lambda: gpio.pwms[cfg_zeno.PIN_RPWM].duty == 40))
        time.sleep(3.6)                                # más del doble de la vigilancia: solo el PING lo sostiene
        self.assertEqual(gpio.pwms[cfg_zeno.PIN_RPWM].duty, 40)

    def test_si_el_hmi_desaparece_zeno_frena(self):
        srv, hw, gpio = self.levantar()
        e = self.enlace([Candidato("Casa", "127.0.0.1", srv.puerto)])
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado"))
        e.enviar("MODE,MANUAL")
        e.enviar("F,40")
        self.assertTrue(esperar(lambda: gpio.pwms[cfg_zeno.PIN_RPWM].duty == 40))
        e.detener()
        self.assertTrue(esperar(lambda: gpio.pwms[cfg_zeno.PIN_RPWM].duty == 0))

    def test_prueba_las_redes_registradas_hasta_encontrar_a_zeno(self):
        srv, hw, gpio = self.levantar()
        e = self.enlace([Candidato("Universidad", "127.0.0.1", puerto_libre()), Candidato("Casa", "127.0.0.1", srv.puerto)])
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado"))
        self.assertEqual(e.snapshot()["red"], "Casa")

    def test_sin_ninguna_ip_registrada_lo_dice(self):
        e = self.enlace([])
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "sin_destino"))

    def test_se_reconecta_solo_cuando_zeno_vuelve(self):
        puerto = puerto_libre()
        srv, hw, gpio = self.levantar(puerto)
        e = self.enlace([Candidato("Casa", "127.0.0.1", puerto)])
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado"))
        srv.detener()
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] in ("reintentando", "conectando")))
        self.assertIsNone(e.snapshot()["telemetria"])  # nunca se muestran datos viejos como si fueran actuales
        self.levantar(puerto)                          # «Zeno reinicia»
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado", 8.0))

    def test_un_zeno_que_acepta_pero_no_habla_se_considera_muerto(self):
        mudo = socket.socket()
        mudo.bind(("127.0.0.1", 0))
        mudo.listen(5)
        self.recursos.append(mudo)
        e = self.enlace([Candidato("Casa", "127.0.0.1", mudo.getsockname()[1])], sin_datos_s=0.5)
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "reintentando"))
        self.assertNotEqual(e.snapshot()["estado"], "conectado")


class TestProbar(Base):
    def test_resultados_claros_para_cada_situacion(self):
        srv, hw, gpio = self.levantar()
        ok, msg = probar("127.0.0.1", srv.puerto, TOKEN)
        self.assertTrue(ok)
        self.assertIn("ZENO-01", msg)
        ok, msg = probar("127.0.0.1", srv.puerto, "mal")
        self.assertFalse(ok)
        self.assertIn("token", msg.lower())
        ok, msg = probar("127.0.0.1", puerto_libre(), TOKEN, timeout=1.0)
        self.assertFalse(ok)
        self.assertIn("No se pudo conectar", msg)

    def test_un_servidor_mudo_no_cuelga_la_prueba(self):
        mudo = socket.socket()
        mudo.bind(("127.0.0.1", 0))
        mudo.listen(5)
        self.recursos.append(mudo)
        t0 = time.monotonic()
        ok, msg = probar("127.0.0.1", mudo.getsockname()[1], TOKEN, timeout=1.0)
        self.assertFalse(ok)
        self.assertLess(time.monotonic() - t0, 3.0)


if __name__ == "__main__":
    unittest.main()
