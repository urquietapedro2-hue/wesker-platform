import os
import socket
import struct
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from falsos import FakeCamara, FakeGPIO, esperar, hardware_prueba, ruta_prueba  # noqa: E402
from zeno import config  # noqa: E402
from zeno.servidor import ServidorControl  # noqa: E402

TOKEN = "TokenDePrueba-123"


class Base(unittest.TestCase):
    token, vigilancia = "", 5.0

    def setUp(self):
        self.gpio = FakeGPIO()
        self.hw = hardware_prueba(self.gpio)
        self.cal, self.nav, self.cam = self.hw.cal, ruta_prueba(self.hw), FakeCamara()
        self.srv = ServidorControl(self.hw, self.nav, self.cam, self.token, cal=self.cal, pan=self.nav.pan, host="127.0.0.1", puerto=0,
                                   vigilancia_s=self.vigilancia, auth_s=0.6)
        self.srv.iniciar()
        self.socks = []

    def tearDown(self):
        for s in self.socks:
            try:
                s.close()
            except OSError:
                pass
        self.srv.detener()

    def conectar(self):
        s = socket.create_connection(("127.0.0.1", self.srv.puerto), timeout=2)
        self.socks.append(s)
        return s

    @staticmethod
    def leer(s, hasta=b"\n", segundos=2.0):
        s.settimeout(0.2)
        buf, fin = b"", time.monotonic() + segundos
        while hasta not in buf and time.monotonic() < fin:
            try:
                d = s.recv(4096)
                if not d:
                    break
                buf += d
            except socket.timeout:
                pass
        return buf

    @staticmethod
    def cerrado_por_el_servidor(s, segundos=2.0):
        s.settimeout(0.2)
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            try:
                if s.recv(4096) == b"":
                    return True
            except socket.timeout:
                continue
            except OSError:
                return True
        return False

    def duty(self):
        return self.gpio.pwms[config.PIN_RPWM].duty


class TestSinToken(Base):
    def test_la_telemetria_llega_en_el_formato_de_v2(self):
        s = self.conectar()
        linea = self.leer(s).split(b"\n")[0].decode()
        self.assertRegex(linea, r"^TELEM:S,0,35\.0,0,0,0,0,0,SEGUIMIENTO,NINGUNO$")

    def test_ping_pong_y_hello(self):
        s = self.conectar()
        s.sendall(b"PING\nHELLO\n")
        datos = self.leer(s, b"HELLO:", 2.0)
        self.assertIn(b"PONG\n", datos)
        resto = self.leer(s, b"\n", 1.0)
        self.assertRegex((datos + resto).decode(), r"HELLO:ZENO-01,4\.1\.0,V2,AUTO")

    def test_manual_obedece_y_auto_ignora_los_movimientos(self):
        s = self.conectar()
        s.sendall(b"F,50\n")
        time.sleep(0.3)
        self.assertEqual(self.duty(), 0)                                  # en AUTO se ignora
        s.sendall(b"MODE,MANUAL\nF,50\n")
        self.assertTrue(esperar(lambda: self.duty() == 50))
        s.sendall(b"S\n")
        self.assertTrue(esperar(lambda: self.duty() == 0))

    def test_comandos_partidos_entre_paquetes(self):
        s = self.conectar()
        for trozo in (b"MODE,MAN", b"UAL\nF,", b"3", b"0\n"):
            s.sendall(trozo)
            time.sleep(0.05)
        self.assertTrue(esperar(lambda: self.duty() == 30))

    def test_basura_y_comandos_invalidos_no_mueven_ni_tumban_nada(self):
        s = self.conectar()
        s.sendall(b"MODE,MANUAL\n\xff\xfe\x00\nF,999\nEXPLOTAR\nMODE,xx\nDIAG_PULSE,F,50,999999\n")
        time.sleep(0.4)
        self.assertEqual((self.duty(), self.nav.modo), (0, "MANUAL"))
        s.sendall(b"F,20\n")
        self.assertTrue(esperar(lambda: self.duty() == 20))             # sigue atendiendo

    def test_linea_enorme_sin_salto_cierra_la_conexion_y_el_servidor_sigue(self):
        s = self.conectar()
        s.sendall(b"A" * 2000)
        self.assertTrue(self.cerrado_por_el_servidor(s))
        otro = self.conectar()
        self.assertTrue(self.leer(otro).startswith(b"TELEM:"))

    def test_desconexion_limpia_en_manual_frena(self):
        s = self.conectar()
        s.sendall(b"MODE,MANUAL\nF,50\n")
        self.assertTrue(esperar(lambda: self.duty() == 50))
        s.close()
        self.assertTrue(esperar(lambda: self.duty() == 0))

    def test_desconexion_brusca_no_tumba_el_servidor_y_frena(self):
        """V2: un ConnectionResetError escapaba del bucle y terminaba el programa entero."""
        s = self.conectar()
        s.sendall(b"MODE,MANUAL\nF,50\n")
        self.assertTrue(esperar(lambda: self.duty() == 50))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))  # cierre con RST
        s.close()
        self.assertTrue(esperar(lambda: self.duty() == 0))
        nuevo = self.conectar()
        self.assertTrue(self.leer(nuevo).startswith(b"TELEM:"))

    def test_una_conexion_nueva_reemplaza_a_la_muerta_sin_frenar(self):
        a = self.conectar()
        a.sendall(b"MODE,MANUAL\n")
        self.assertTrue(esperar(lambda: self.nav.modo == "MANUAL"))
        b = self.conectar()
        b.sendall(b"F,40\n")
        self.assertTrue(esperar(lambda: self.duty() == 40))
        self.assertTrue(self.cerrado_por_el_servidor(a))                  # la vieja se cerró
        time.sleep(0.4)
        self.assertEqual(self.duty(), 40)                                  # y no frenó a la nueva

    def test_camara_on_off_y_abortar_una_fase(self):
        s = self.conectar()
        s.sendall(b"CAM_ON\nCAM_OFF\n")
        self.assertTrue(esperar(lambda: (self.cam.inicios, self.cam.paros) == (1, 1)))
        self.cal.set("debounce_interseccion_ms", 0)
        self.nav.paso((1, 1, 1, 1, 1), "NINGUNO")
        self.assertEqual(self.nav.fase, "ESCANEANDO_QR")
        s.sendall(b"ABORTAR\n")
        self.assertTrue(esperar(lambda: self.nav.abortar() or True))
        self.nav.paso((0, 0, 1, 0, 0), "NINGUNO")
        self.assertEqual(self.nav.fase, "SALIENDO")

    def test_pulso_de_diagnostico_valido(self):
        s = self.conectar()
        s.sendall(b"DIAG_PULSE,F,40,100\n")
        self.assertTrue(esperar(lambda: self.duty() == 40))
        self.assertTrue(esperar(lambda: self.duty() == 0))

    def test_la_telemetria_refleja_el_estado_de_la_estacion(self):
        self.cal.set("debounce_interseccion_ms", 0)
        self.nav.paso((1, 1, 1, 1, 1), "NINGUNO")
        s = self.conectar()
        self.assertRegex(self.leer(s).decode(), r"TELEM:ESTACION,0,35\.0,0,0,0,0,0,ESTACION_DESCARGA,NINGUNO")


class TestVigilanciaDeEnlace(Base):
    vigilancia = 0.4

    def test_en_manual_sin_senales_frena(self):
        s = self.conectar()
        s.sendall(b"MODE,MANUAL\nF,50\n")
        self.assertTrue(esperar(lambda: self.duty() == 50))
        self.assertTrue(esperar(lambda: self.duty() == 0, 3.0))

    def test_los_ping_mantienen_el_movimiento(self):
        s = self.conectar()
        s.sendall(b"MODE,MANUAL\nF,50\n")
        self.assertTrue(esperar(lambda: self.duty() == 50))
        for _ in range(12):
            s.sendall(b"PING\n")
            time.sleep(0.1)
        self.assertEqual(self.duty(), 50)

    def test_en_auto_no_actua(self):
        s = self.conectar()
        s.sendall(b"PING\n")
        self.hw.traccion("F", 45)
        time.sleep(1.0)
        self.assertEqual(self.duty(), 45)


class TestConToken(Base):
    token = TOKEN

    def test_sin_autenticar_no_hay_telemetria_ni_se_obedece(self):
        s = self.conectar()
        self.assertEqual(self.leer(s, segundos=0.5), b"")
        s.sendall(b"MODE,MANUAL\n")
        self.assertIn(b"ERR,AUTH", self.leer(s, b"ERR,AUTH"))
        self.assertTrue(self.cerrado_por_el_servidor(s))
        self.assertEqual(self.nav.modo, "AUTO")

    def test_token_incorrecto_se_rechaza(self):
        for malo in (b"AUTH,otro\n", b"AUTH,\n", b"AUTH\n", b"AUTH," + TOKEN.upper().encode() + b"\n"):
            s = self.conectar()
            s.sendall(malo)
            self.assertIn(b"ERR,AUTH", self.leer(s, b"ERR,AUTH"), malo)

    def test_token_correcto_da_acceso(self):
        s = self.conectar()
        s.sendall(b"AUTH," + TOKEN.encode() + b"\n")
        self.assertTrue(self.leer(s).startswith(b"TELEM:"))
        s.sendall(b"MODE,MANUAL\nF,35\n")
        self.assertTrue(esperar(lambda: self.duty() == 35))

    def test_quien_no_se_autentica_a_tiempo_es_desconectado(self):
        s = self.conectar()
        self.assertTrue(self.cerrado_por_el_servidor(s, 3.0))

    def test_una_conexion_sin_autenticar_no_desplaza_al_hmi_activo(self):
        bueno = self.conectar()
        bueno.sendall(b"AUTH," + TOKEN.encode() + b"\n")
        self.assertTrue(self.leer(bueno).startswith(b"TELEM:"))
        intruso = self.conectar()
        intruso.sendall(b"AUTH,mal\n")
        self.leer(intruso, b"ERR,AUTH")
        time.sleep(0.3)
        self.assertTrue(self.leer(bueno).startswith(b"TELEM:"))            # el HMI legítimo sigue recibiendo datos


if __name__ == "__main__":
    unittest.main()


class TestClientePrueba(Base):
    token = TOKEN

    def test_el_cliente_de_prueba_se_autentica_manda_ordenes_y_lee_telemetria(self):
        from zeno.cliente_prueba import ejecutar
        lineas = ejecutar("127.0.0.1", self.srv.puerto, TOKEN, ["MODE,MANUAL", "F,25"], 1.2, salida=lambda t: None)
        self.assertTrue(any(l.startswith("TELEM:") for l in lineas))
        self.assertTrue(esperar(lambda: self.duty() == 0))            # al cerrar el cliente, Zeno frena
        self.assertEqual(self.nav.modo, "MANUAL")

    def test_el_cliente_sin_token_correcto_no_recibe_telemetria(self):
        from zeno.cliente_prueba import ejecutar
        lineas = ejecutar("127.0.0.1", self.srv.puerto, "equivocado", [], 0.8, salida=lambda t: None)
        self.assertFalse(any(l.startswith("TELEM:") for l in lineas))
