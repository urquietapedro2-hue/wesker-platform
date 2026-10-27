"""Zeno 4.1 completo en una PC: sockets reales, hardware falso. Ruta + rampas + calibración + protocolo + video."""
import http.client
import json
import os
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from falsos import FakeCamara, FakeGPIO, FakePCA, esperar  # noqa: E402
from falsos import calibracion_prueba  # noqa: E402
from zeno import config  # noqa: E402
from zeno.camara_stream import crear_servidor_video  # noqa: E402
from zeno.hardware import Hardware  # noqa: E402
from zeno.principal import Aplicacion  # noqa: E402
from zeno.ruta import Ruta  # noqa: E402
from zeno.servidor import ServidorControl  # noqa: E402
from zeno.servos import GestorServos, PanCamara, Rampas, angulo_a_us  # noqa: E402

CENTRO_NEGRO = {5: 1, 6: 1, 19: 0, 20: 1, 26: 1}     # solo el sensor central en negro (con lógica invertida)
TODOS_NEGROS = {p: 0 for p in config.PINS_LINEA}


class Armado(unittest.TestCase):
    def setUp(self):
        self.cal = calibracion_prueba(t_indexacion_ms=60, t_espera_descarga_s=0.5, t_salida_s=0.3, debounce_interseccion_ms=50,
                                      t_escaneo_qr_s=5.0)
        self.gpio, self.pca = FakeGPIO(), FakePCA()
        self.servos = GestorServos(gpio=self.gpio, fabrica_pca=lambda: self.pca, cal=self.cal, dormir=lambda s: None)
        self.hw = Hardware(self.cal, self.gpio, servos=self.servos)
        self.cam = FakeCamara()
        self.rampas, self.pan = Rampas(self.servos, self.cal), PanCamara(self.servos, self.cal)
        self.ruta = Ruta(self.cal, self.rampas, self.pan)
        self.srv = ServidorControl(self.hw, self.ruta, self.cam, "", cal=self.cal, pan=self.pan, host="127.0.0.1", puerto=0,
                                   vigilancia_s=30)
        self.app = Aplicacion(self.hw, self.cam, self.ruta, self.srv, self.pan, paso_s=0.005)
        self.ruta.cambiar_modo("AUTO")
        self.gpio.entradas = dict(CENTRO_NEGRO)
        self.socks = []

    def tearDown(self):
        self.app.detener()
        for s in self.socks:
            s.close()

    def cliente(self):
        s = socket.create_connection(("127.0.0.1", self.srv.puerto), timeout=2)
        s.settimeout(0.2)
        self.socks.append(s)
        return s

    @staticmethod
    def leer_hasta(s, texto, seg=3.0):
        buf, fin = b"", time.monotonic() + seg
        while texto.encode() not in buf and time.monotonic() < fin:
            try:
                buf += s.recv(65536)
            except socket.timeout:
                pass
        return buf.decode(errors="replace")

    def pulso_us(self, canal):
        return [u for c, u in self.pca.pulsos if c == canal]

    def duty(self):
        return self.gpio.pwms[config.PIN_RPWM].duty


class TestCicloCompleto(Armado):
    def test_estacion_1_espera_la_carga_y_solo_entonces_se_mueve(self):
        self.app.iniciar()
        time.sleep(0.4)
        self.assertEqual((self.ruta.fase, self.duty()), ("ST1_CARGA_R1", 0))        # línea a la vista pero no sale
        self.assertEqual(self.servos.angulo("rampa1"), 90.0)                        # rampas bloqueadas
        c = self.cliente()
        c.sendall(b"CARGA_RAMPA,2\n")                                               # fuera de turno: se ignora
        time.sleep(0.3)
        self.assertEqual(self.ruta.fase, "ST1_CARGA_R1")
        c.sendall(b"CARGA_RAMPA,1\n")
        self.assertTrue(esperar(lambda: self.ruta.fase == "ST1_CARGA_R2"))
        c.sendall(b"CARGA_RAMPA,2\n")
        self.assertTrue(esperar(lambda: self.ruta.fase == "SEGUIMIENTO", 3.0))
        self.assertTrue(esperar(lambda: self.duty() == 45))                          # y ya sigue la línea

    def test_ruta_completa_con_qr_en_intersecciones(self):
        self.cal.set("vel_auto_max", 100)
        self.app.iniciar()
        c = self.cliente()
        c.sendall(b"CARGA_RAMPA,1\n")
        self.assertTrue(esperar(lambda: self.ruta.fase == "ST1_CARGA_R2"))
        c.sendall(b"CARGA_RAMPA,2\n")
        self.assertTrue(esperar(lambda: self.ruta.fase == "SEGUIMIENTO", 3.0))
        for qr, rampa, abierto in (("ESTACION_2", 1, 130.0), ("ESTACION_3", 2, 50.0)):
            self.gpio.entradas, self.cam.qr = dict(TODOS_NEGROS), "NINGUNO"          # intersección
            self.assertTrue(esperar(lambda: self.ruta.fase == "ESCANEANDO_QR"))
            self.assertEqual((self.duty(), self.cam.inicios >= 1), (0, True))
            self.cam.qr = qr
            self.assertTrue(esperar(lambda: self.ruta.fase == "DESCARGANDO"))
            self.assertEqual(self.servos.angulo("rampa%d" % rampa), abierto)         # liberación calibrada
            self.assertTrue(esperar(lambda: self.servos.angulo("rampa%d" % rampa) == 90.0, 3.0))   # y vuelve a bloqueo
            self.gpio.entradas = dict(CENTRO_NEGRO)
            self.cam.qr = "NINGUNO"
            self.assertTrue(esperar(lambda: self.ruta.fase == "SEGUIMIENTO", 3.0))
        self.assertEqual((self.ruta.estado()["carga_r1"], self.ruta.estado()["carga_r2"]), (False, False))

    def test_debounce_ignora_un_destello_de_5_sensores(self):
        self.cal.set_many({"debounce_interseccion_ms": 400, "vel_auto_max": 100})
        self.ruta.cambiar_modo("MANUAL")
        self.ruta.cambiar_modo("AUTO")
        self.app.iniciar()
        c = self.cliente()
        c.sendall(b"CARGA_RAMPA,1\n")
        self.assertTrue(esperar(lambda: self.ruta.fase == "ST1_CARGA_R2"))
        c.sendall(b"CARGA_RAMPA,2\n")
        self.assertTrue(esperar(lambda: self.ruta.fase == "SEGUIMIENTO", 3.0))
        self.gpio.entradas = dict(TODOS_NEGROS)
        time.sleep(0.15)                                                              # destello de 150 ms < 400 ms
        self.gpio.entradas = dict(CENTRO_NEGRO)
        time.sleep(0.5)
        self.assertEqual(self.ruta.fase, "SEGUIMIENTO")
        self.gpio.entradas = dict(TODOS_NEGROS)
        self.assertTrue(esperar(lambda: self.ruta.fase == "ESCANEANDO_QR", 2.0))


class TestCalibracionPorRed(Armado):
    def pedir(self, c, linea, espera):
        c.sendall(linea.encode() + b"\n")
        return self.leer_hasta(c, espera)

    def test_esquema_y_valores_llegan_en_json(self):
        self.app.iniciar()
        c = self.cliente()
        txt = self.pedir(c, "CAL_ESQUEMA", "CAL_ESQ:")
        esq = json.loads(txt.split("CAL_ESQ:", 1)[1].split("\n", 1)[0])
        self.assertIn("vel_auto_max", [e["clave"] for e in esq])
        txt = self.pedir(c, "CAL_GET", "CAL:{")
        snap = json.loads(txt.split("CAL:", 1)[1].split("\n", 1)[0])
        self.assertEqual(snap["valores"]["t_espera_descarga_s"], 0.5)

    def test_cambio_en_vivo_valida_y_responde_error_sin_cambiar_nada(self):
        self.app.iniciar()
        c = self.cliente()
        txt = self.pedir(c, "CAL_SET,vel_auto_max,33", "CAL:{")
        self.assertEqual(json.loads(txt.split("CAL:", 1)[1].split("\n", 1)[0])["valores"]["vel_auto_max"], 33)
        self.assertEqual(self.cal["vel_auto_max"], 33)
        for malo in ("CAL_SET,vel_auto_max,500", "CAL_SET,nada,1", "CAL_SET,direccion_min,120", "CAL_SET,vel_auto_max,abc"):
            self.assertIn("CAL_ERR:", self.pedir(c, malo, "CAL_ERR:"), malo)
        self.assertEqual(self.cal["vel_auto_max"], 33)

    def test_el_tope_de_pwm_cambia_la_marcha_sin_reiniciar(self):
        self.ruta.fase = "SEGUIMIENTO"
        self.cal.set("vel_auto_max", 100)
        self.app.iniciar()
        self.assertTrue(esperar(lambda: self.duty() == 45))
        c = self.cliente()
        c.sendall(b"CAL_SET,vel_auto_max,30\n")
        self.assertTrue(esperar(lambda: self.hw.velocidad_actual == 30 or self.duty() == 30))

    def test_guardar_escribe_el_json_y_restaurar_lo_recupera(self):
        self.app.iniciar()
        c = self.cliente()
        self.pedir(c, "CAL_SET,t_indexacion_ms,700", "CAL:{")
        self.assertIn('"sin_guardar":true', self.pedir(c, "CAL_GET", "sin_guardar"))
        self.assertIn('"sin_guardar":false', self.pedir(c, "CAL_GUARDAR", "sin_guardar"))
        with open(self.cal.ruta) as f:
            self.assertEqual(json.load(f)["valores"]["t_indexacion_ms"], 700)
        self.pedir(c, "CAL_SET,t_indexacion_ms,100", "CAL:{")
        self.pedir(c, "CAL_RESTAURAR", "CAL:{")
        self.assertEqual(self.cal["t_indexacion_ms"], 700)
        self.pedir(c, "CAL_DEFECTO", "CAL:{")
        self.assertEqual(self.cal["t_indexacion_ms"], 400)

    def test_probar_servo_solo_en_manual_y_con_limites_fisicos(self):
        self.app.iniciar()
        c = self.cliente()
        self.assertIn("MANUAL", self.pedir(c, "CAL_PROBAR,rampa1,120", "CAL_ERR:"))   # en AUTO se rechaza
        c.sendall(b"MODE,MANUAL\n")
        self.assertTrue(esperar(lambda: self.ruta.modo == "MANUAL"))
        self.pedir(c, "CAL_PROBAR,rampa1,120", "CAL:{")
        self.assertEqual(self.servos.angulo("rampa1"), 120.0)
        self.pedir(c, "CAL_PROBAR,direccion,170", "CAL:{")
        self.assertEqual(self.servos.angulo("direccion"), config.LIMITES_FISICOS["direccion"][1])   # nunca fuera de la mecánica

    def test_los_angulos_de_direccion_calibrados_llegan_al_servo(self):
        self.cal.set_many({"direccion_centro": 95.0, "direccion_max": 120.0, "direccion_min": 75.0, "direccion_trim": 0.0})
        self.ruta.cambiar_modo("MANUAL")
        self.app.iniciar()
        c = self.cliente()
        c.sendall(b"F,40\nL,40\n")
        self.assertTrue(esperar(lambda: self.hw.estado_movimiento == "L"))
        self.assertAlmostEqual(self.pulso_us(config.CANAL_PCA["direccion"])[-1], angulo_a_us(120.0))
        c.sendall(b"R,40\n")
        self.assertTrue(esperar(lambda: self.hw.estado_movimiento == "R"))
        self.assertAlmostEqual(self.pulso_us(config.CANAL_PCA["direccion"])[-1], angulo_a_us(75.0))
        self.cal.set("direccion_invertida", True)                                      # izquierda y derecha se intercambian
        c.sendall(b"L,40\n")
        self.assertTrue(esperar(lambda: self.hw.estado_movimiento == "L"))
        self.assertAlmostEqual(self.pulso_us(config.CANAL_PCA["direccion"])[-1], angulo_a_us(75.0))

    def test_linea_ruta_y_telemetria_clasica_conviven(self):
        self.app.iniciar()
        c = self.cliente()
        txt = self.leer_hasta(c, "RUTA:")
        self.assertRegex(txt, r"TELEM:[A-Z]+,\d+,35\.0,\d,\d,\d,\d,\d,[A-Z_]+,[A-Z_0-9]+\n")
        self.assertRegex(txt + self.leer_hasta(c, "\n", 0.5), r"RUTA:ST1_CARGA_R1,NINGUNA,0,0,NINGUNA,0,PCA9685,1,[0-9-]+,[0-9-]+,90,90,\d+")


class TestStream(unittest.TestCase):
    def test_token_y_cuadros_nuevos(self):
        cam = FakeCamara()
        cam._frame = b"\xff\xd8JPEG\xff\xd9"
        srv = crear_servidor_video(cam, "127.0.0.1", 0, "tok")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            puerto = srv.server_address[1]
            for ruta, codigo in (("/stream.mjpg", 401), ("/stream.mjpg?t=mal", 401), ("/otra", 404)):
                c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=2)
                c.request("GET", ruta)
                self.assertEqual(c.getresponse().status, codigo, ruta)
            c = http.client.HTTPConnection("127.0.0.1", puerto, timeout=2)
            c.request("GET", "/stream.mjpg?t=tok")
            r = c.getresponse()
            self.assertEqual(r.status, 200)
            self.assertIn("multipart/x-mixed-replace", r.getheader("Content-Type"))
            self.assertIn(b"--frame", r.fp.read1(200) if hasattr(r.fp, "read1") else r.read(60))
            self.assertTrue(esperar(lambda: cam.espectadores == 1 and cam.inicios >= 1))
            r.close()
            c.close()
            self.assertTrue(esperar(lambda: cam.espectadores == 0, 4.0))
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
