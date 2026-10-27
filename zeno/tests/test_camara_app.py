import http.client
import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from falsos import FakeCamara, FakeCv2, FakeGPIO, esperar, hardware_prueba, ruta_prueba  # noqa: E402
from zeno import config  # noqa: E402
from zeno.camara import QR_PERSISTENCIA_S, Camara, crear_servidor_video  # noqa: E402
from zeno.principal import Aplicacion  # noqa: E402


class Reloj:
    def __init__(self): self.t = 50.0
    def __call__(self): return self.t


class TestCamaraQR(unittest.TestCase):
    def camara(self, respuestas):
        self.reloj = Reloj()
        return Camara(cv2=FakeCv2(respuestas), reloj=self.reloj)

    def test_el_qr_se_mantiene_un_instante_y_luego_se_olvida(self):
        c = self.camara(["ESTACION_2", "", ""])
        self.assertEqual(c.qr, "NINGUNO")
        c._leer_qr(b"x")
        self.assertEqual(c.qr, "ESTACION_2")
        c._leer_qr(b"x")                              # cuadro sin lectura: no se pierde de golpe (V2 sí lo perdía)
        self.reloj.t += QR_PERSISTENCIA_S - 0.1
        self.assertEqual(c.qr, "ESTACION_2")
        self.reloj.t += 0.2
        self.assertEqual(c.qr, "NINGUNO")

    def test_un_qr_que_no_es_de_una_estacion_se_ignora(self):
        c = self.camara(["HOLA", "https://sitio.example/x"])
        c._leer_qr(b"x")
        c._leer_qr(b"x")
        self.assertEqual(c.qr, "NINGUNO")

    def test_un_cuadro_defectuoso_no_mata_la_lectura(self):
        c = self.camara([RuntimeError("cuadro roto"), "ESTACION_1"])
        self.assertEqual(c._leer_qr(b"x")[0], "")
        c._leer_qr(b"x")
        self.assertEqual(c.qr, "ESTACION_1")

    def test_el_jpeg_solo_se_codifica_si_alguien_mira(self):
        cv = FakeCv2(["ESTACION_1"] * 3)
        c = Camara(cv2=cv)
        c.start()
        time.sleep(0.4)
        self.assertEqual(cv.codificados, 0)           # nadie mira: cero trabajo de video
        self.assertEqual(c.qr, "ESTACION_1")          # pero el QR se sigue leyendo
        c.espectadores = 1
        self.assertTrue(esperar(lambda: c.frame() == b"JPEG"))
        c.stop()
        self.assertTrue(esperar(lambda: cv.captura.liberada))

    def test_sin_camara_no_se_cae(self):
        cv = FakeCv2()
        cv.captura.isOpened = lambda: False
        c = Camara(cv2=cv)
        c.start()
        self.assertTrue(esperar(lambda: not c.running))


class TestVideoConToken(unittest.TestCase):
    def pedir(self, srv, ruta):
        con = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=3)
        con.request("GET", ruta)
        r = con.getresponse()
        estado = r.status
        con.close()
        return estado

    def test_el_video_exige_el_token_cuando_hay_uno(self):
        cam = Camara(cv2=FakeCv2())
        srv = crear_servidor_video(cam, "127.0.0.1", 0, token="secreto-123")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            self.assertEqual(self.pedir(srv, "/stream.mjpg"), 401)
            self.assertEqual(self.pedir(srv, "/stream.mjpg?t=otro"), 401)
            self.assertEqual(self.pedir(srv, "/otra.cosa?t=secreto-123"), 404)
            self.assertEqual(self.pedir(srv, "/stream.mjpg?t=secreto-123"), 200)
            self.assertTrue(esperar(lambda: cam.running))      # pedir el video enciende la cámara
        finally:
            cam.stop()
            srv.shutdown()
            srv.server_close()

    def test_sin_token_configurado_el_video_es_abierto_como_en_v2(self):
        cam = Camara(cv2=FakeCv2())
        srv = crear_servidor_video(cam, "127.0.0.1", 0, token="")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            self.assertEqual(self.pedir(srv, "/stream.mjpg"), 200)
        finally:
            cam.stop()
            srv.shutdown()
            srv.server_close()


class ServidorFalso:
    def iniciar(self): pass
    def detener(self): pass


class TestAplicacion(unittest.TestCase):
    def armar(self, nav=None, hw=None, paso=0.005):
        self.gpio = FakeGPIO()
        self.hw = hw or hardware_prueba(self.gpio)
        self.cam = FakeCamara()
        ruta = nav or ruta_prueba(self.hw)
        return Aplicacion(self.hw, self.cam, ruta, ServidorFalso(), ruta.pan, paso_s=paso)

    def test_la_navegacion_mueve_el_motor_con_las_lecturas(self):
        app = self.armar()
        self.gpio.entradas = {5: 1, 6: 1, 19: 0, 20: 1, 26: 1}   # solo el sensor central en negro
        app.iniciar()
        try:
            self.assertTrue(esperar(lambda: self.gpio.pwms[config.PIN_RPWM].duty == 45))
            self.assertEqual(self.hw.estado_movimiento, "F")
        finally:
            app.detener()

    def test_un_error_en_la_navegacion_frena_y_el_bucle_sigue_vivo(self):
        """V2: cualquier excepción mataba el hilo y Zeno seguía con el último movimiento para siempre."""
        app = self.armar()
        self.gpio.entradas = {5: 1, 6: 1, 19: 0, 20: 1, 26: 1}
        app.iniciar()
        try:
            self.assertTrue(esperar(lambda: self.hw.estado_movimiento == "F"))
            original = self.hw.leer_sensores
            self.hw.leer_sensores = lambda: (_ for _ in ()).throw(OSError("fallo de GPIO"))
            self.assertTrue(esperar(lambda: self.hw.estado_movimiento == "S" and app.errores_navegacion >= 1))
            self.hw.leer_sensores = original                       # el problema se resuelve...
            self.assertTrue(esperar(lambda: self.hw.estado_movimiento == "F", 3.0))   # ...y Zeno retoma solo
        finally:
            app.detener()

    def test_si_el_bucle_de_navegacion_se_cuelga_el_supervisor_frena(self):
        with patch.object(config, "LATIDO_NAVEGACION_MAX_S", 0.3):
            app = self.armar()
            app.nav.paso = lambda *a, **k: time.sleep(5)
            self.gpio.pwms[config.PIN_RPWM].duty = 60               # el motor quedó encendido
            app.iniciar()
            try:
                self.assertTrue(esperar(lambda: self.gpio.pwms[config.PIN_RPWM].duty == 0, 3.0))
            finally:
                app.detener()

    def test_al_entrar_a_una_estacion_enciende_la_camara_y_se_detiene(self):
        app = self.armar()
        self.gpio.entradas = {p: 0 for p in config.PINS_LINEA}      # todo negro (con lógica invertida)
        app.iniciar()
        try:
            self.assertTrue(esperar(lambda: app.nav.sub == "ESTACION_DESCARGA"))
            self.assertGreaterEqual(self.cam.inicios, 1)
            self.assertEqual(self.hw.estado_movimiento, "S")
        finally:
            app.detener()


class TestCentroQR(unittest.TestCase):
    class Caja:
        def __init__(self, xs): self.xs = xs
        def reshape(self, *a): return [(x, 100) for x in self.xs]

    def camara(self, dato, caja):
        r = Reloj()
        c = Camara(cv2=FakeCv2(), reloj=r)
        c.detector = type("D", (), {"detectAndDecode": lambda s, f: (dato, caja, None)})()
        return c, r

    def test_centro_normalizado_y_caducidad(self):
        c, r = self.camara("ESTACION_4", self.Caja([480, 560, 560, 480]))      # QR a la derecha del centro (320)
        self.assertIsNone(c.qr_centro)
        c._leer_qr(b"x")
        self.assertAlmostEqual(c.qr_centro, (520 - 320) / 320.0)
        r.t += 1.5
        self.assertIsNone(c.qr_centro)

    def test_cuenta_aunque_no_se_pueda_decodificar(self):
        c, _ = self.camara("", self.Caja([80, 160]))
        c._leer_qr(b"x")
        self.assertLess(c.qr_centro, 0)
        self.assertEqual(c.qr, "NINGUNO")


if __name__ == "__main__":
    unittest.main()
