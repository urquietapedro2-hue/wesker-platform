"""Lado HMI de Zeno 4.1 (sin Qt): líneas RUTA/CAL, disparador de estación, video MJPEG, saneado y todo contra el servidor real."""
import json
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
    from falsos import FakeCamara, FakeGPIO, hardware_prueba, ruta_prueba
    from zeno.calibracion import ESQUEMA
    from zeno.camara_stream import crear_servidor_video
    from zeno.logica import formatear_ruta
    from zeno.servidor import ServidorControl
    HAY_ZENO = True
except ImportError:
    HAY_ZENO = False

from core.estado import sanear_logistica, sanear_zeno  # noqa: E402
from core.permissions import puede_calibrar, puede_controlar  # noqa: E402
from core.video_zeno import ExtractorMJPEG, LectorVideo  # noqa: E402
from core.zeno_enlace import (Candidato, EnlaceZeno, detectar_estacion, parsear_cal, parsear_cal_esquema,  # noqa: E402
                              parsear_ruta)

TOKEN = "Token/De+Prueba=1"
BUENA = "RUTA:DESCARGANDO,ESTACION_2,1,0,NINGUNA,12,GPIO,0,90,95,130,-,7"


def esperar(cond, seg=4.0):
    fin = time.monotonic() + seg
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


class TestRuta(unittest.TestCase):
    def test_linea_valida(self):
        r = parsear_ruta(BUENA)
        self.assertEqual((r["fase"], r["estacion"], r["carga_r1"], r["carga_r2"], r["restante_s"], r["i2c"], r["backend"], r["cal_version"]),
                         ("DESCARGANDO", "ESTACION_2", True, False, 12.0, False, "GPIO", 7))
        self.assertEqual(r["servos"], {"direccion": 90.0, "camara": 95.0, "rampa1": 130.0, "rampa2": None})

    def test_lineas_invalidas_no_lanzan(self):
        malas = ["", "TELEM:F", "RUTA:", BUENA + ",1", BUENA.replace("DESCARGANDO", "VOLANDO"), BUENA.replace("NINGUNA", "FUEGO"),
                 BUENA.replace(",GPIO,", ",WIFI,"), BUENA.replace(",1,0,NINGUNA", ",2,0,NINGUNA"), BUENA.replace(",130,", ",999,"),
                 BUENA.replace(",130,", ",abc,"), BUENA.replace("ESTACION_2", "<script>"), BUENA.replace("ESTACION_2", "ESTACION_4"),
                 BUENA.replace(",12,", ",-1,"), BUENA.replace(",7", ",x")]
        for m in malas:
            self.assertIsNone(parsear_ruta(m), m)

    def test_disparador_de_estacion(self):
        self.assertEqual(detectar_estacion("NINGUNO", "ESTACION_2"), "ESTACION_2")
        self.assertEqual(detectar_estacion("ESTACION_1", "ESTACION_3"), "ESTACION_3")
        for previa, actual in (("ESTACION_2", "ESTACION_2"), ("ESTACION_2", "NINGUNO"), ("NINGUNO", "BASURA"), ("NINGUNO", "ESTACION_4")):
            self.assertIsNone(detectar_estacion(previa, actual), (previa, actual))

    def test_sanear_ruta_de_otra_persona(self):
        d = {"fase": "DESCARGANDO", "estacion": "ESTACION_2", "carga_r1": True, "alarma": "RARA", "servos": {"rampa1": 9999, "camara": "x"}}
        s = sanear_logistica(d)
        self.assertEqual((s["alarma"], s["carga_r1"], s["carga_r2"], s["servos"]["camara"], s["servos"]["rampa1"]), ("NINGUNA", True, False, None, 180.0))
        for malo in (None, [], "x", {"fase": "XX"}):
            self.assertIsNone(sanear_logistica(malo))
        self.assertIsNone(sanear_zeno({"dir": "F"})["logistica"])
        self.assertEqual(sanear_zeno({"logi": d})["logistica"]["fase"], "DESCARGANDO")

    def test_roles_de_calibracion(self):
        self.assertTrue(puede_calibrar("ADMIN") and puede_calibrar("MAINTENANCE"))
        self.assertFalse(puede_calibrar("OPERATOR") or puede_calibrar("VIEWER"))
        self.assertTrue(puede_controlar("OPERATOR"))


class TestCalibracionLineas(unittest.TestCase):
    ESQ = [{"clave": "vel_auto_max", "grupo": "Tracción", "etiqueta": "Límite", "tipo": "int", "min": 10, "max": 100, "defecto": 45,
            "unidad": "%", "probar": None, "ayuda": ""},
           {"clave": "direccion_invertida", "grupo": "Dirección", "etiqueta": "Invertir", "tipo": "bool", "min": None, "max": None,
            "defecto": False, "unidad": "", "probar": None, "ayuda": ""}]

    def test_cal_valida_e_invalida(self):
        ok = parsear_cal('CAL:{"version":3,"sin_guardar":true,"valores":{"a":1,"b":2.5,"c":true}}')
        self.assertEqual((ok["version"], ok["sin_guardar"], ok["valores"]), (3, True, {"a": 1, "b": 2.5, "c": True}))
        for mala in ("", "CAL:", "CAL:{", "CAL:[]", 'CAL:{"version":"x","valores":{}}', 'CAL:{"version":1,"valores":{"a":"texto"}}',
                     'CAL:{"version":1,"valores":{"a":NaN}}', 'CAL:{"version":true,"valores":{}}', 'CAL:{"version":1,"valores":5}',
                     'CAL:{"version":1,"valores":{"' + "k" * 50 + '":1}}'):
            self.assertIsNone(parsear_cal(mala), mala)

    def test_esquema_valido_e_invalido(self):
        e = parsear_cal_esquema("CAL_ESQ:" + json.dumps(self.ESQ))
        self.assertEqual([p["clave"] for p in e], ["vel_auto_max", "direccion_invertida"])
        casos = ["", "CAL_ESQ:", "CAL_ESQ:{}", "CAL_ESQ:[]", "CAL_ESQ:" + json.dumps([{"clave": "x"}]),
                 "CAL_ESQ:" + json.dumps([dict(self.ESQ[0], tipo="texto")]), "CAL_ESQ:" + json.dumps([dict(self.ESQ[0], min=50, max=10)]),
                 "CAL_ESQ:" + json.dumps([dict(self.ESQ[0], probar="motor")]), "CAL_ESQ:" + json.dumps([dict(self.ESQ[0], etiqueta="x" * 500)]),
                 "CAL_ESQ:" + json.dumps(self.ESQ * 50), "CAL_ESQ:" + json.dumps([dict(self.ESQ[0], defecto="a")])]
        for c in casos:
            self.assertIsNone(parsear_cal_esquema(c), c[:60])


class TestExtractor(unittest.TestCase):
    def flujo(self, *cuadros):
        return b"".join(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(c) + c + b"\r\n" for c in cuadros)

    def test_corte_en_cualquier_byte(self):
        datos = self.flujo(b"\xff\xd8AAAA\xff\xd9", b"\xff\xd8" + b"B" * 5000 + b"\xff\xd9")
        for corte in (1, 7, 40, 100, 3000):
            e, salida = ExtractorMJPEG(), []
            for i in range(0, len(datos), corte):
                salida += e.alimentar(datos[i:i + corte])
            self.assertEqual(len(salida), 2, corte)
            self.assertEqual(salida[0], b"\xff\xd8AAAA\xff\xd9")

    def test_cuadro_gigante_o_cabecera_rota_se_descarta(self):
        e = ExtractorMJPEG()
        self.assertEqual(e.alimentar(b"Content-Length: 99999999\r\n\r\nxxxx"), [])
        self.assertEqual(e.alimentar(b"Content-Length: abc\r\n\r\n"), [])
        self.assertEqual(e.alimentar(self.flujo(b"OK")), [b"OK"])


@unittest.skipUnless(HAY_ZENO, "no está la carpeta zeno/")
class TestContraZenoReal(unittest.TestCase):
    def setUp(self):
        self.gpio = FakeGPIO()
        self.hw = hardware_prueba(self.gpio)
        self.cam = FakeCamara()
        self.cam._frame = b"\xff\xd8CUADRO\xff\xd9"
        self.nav = ruta_prueba(self.hw, fase_inicial="ST1_CARGA_R1")
        self.srv = ServidorControl(self.hw, self.nav, self.cam, TOKEN, cal=self.hw.cal, pan=self.nav.pan, host="127.0.0.1", puerto=0)
        self.srv.iniciar()
        self.video = crear_servidor_video(self.cam, "127.0.0.1", 0, TOKEN)
        threading.Thread(target=self.video.serve_forever, daemon=True).start()
        self.cierres = []

    def tearDown(self):
        for c in self.cierres:
            c()
        self.video.shutdown()
        self.srv.detener()

    def enlace(self):
        e = EnlaceZeno([Candidato("Casa", "127.0.0.1", self.srv.puerto)], TOKEN, esperas=(0.05,))
        e.iniciar()
        self.cierres.append(e.detener)
        return e

    def test_enlace_recibe_ruta_esquema_y_valores_al_conectar(self):
        e = self.enlace()
        self.assertTrue(esperar(lambda: e.snapshot()["ruta"] is not None and e.snapshot()["cal"] and e.snapshot()["cal_esquema"]))
        s = e.snapshot()
        self.assertEqual((s["ruta"]["fase"], s["ruta"]["carga_r1"]), ("ST1_CARGA_R1", False))
        self.assertEqual(len(s["cal_esquema"]), len(ESQUEMA))
        self.assertEqual(s["cal"]["valores"]["t_espera_descarga_s"], self.hw.cal["t_espera_descarga_s"])

    def test_cambiar_un_parametro_desde_el_hmi_lo_aplica_zeno_y_lo_confirma(self):
        e = self.enlace()
        self.assertTrue(esperar(lambda: e.snapshot()["cal"]))
        self.assertTrue(e.enviar("CAL_SET,vel_auto_max,33"))
        self.assertTrue(esperar(lambda: self.hw.cal["vel_auto_max"] == 33))
        self.assertTrue(esperar(lambda: e.snapshot()["cal"]["valores"]["vel_auto_max"] == 33 and e.snapshot()["cal"]["sin_guardar"]))
        e.enviar("CAL_SET,vel_auto_max,999")
        self.assertTrue(esperar(lambda: e.snapshot()["cal_error"][0] == 1))
        self.assertIn("fuera de rango", e.snapshot()["cal_error"][1])
        self.assertEqual(self.hw.cal["vel_auto_max"], 33)

    def test_un_cambio_hecho_por_otro_se_relee_solo(self):
        e = self.enlace()
        self.assertTrue(esperar(lambda: e.snapshot()["cal"]))
        self.hw.cal.set("t_indexacion_ms", 777)                      # otro cliente (o el propio Zeno) cambia la calibración
        self.assertTrue(esperar(lambda: e.snapshot()["cal"]["valores"]["t_indexacion_ms"] == 777))

    def test_botones_de_carga_llegan_a_la_ruta(self):
        e = self.enlace()
        self.assertTrue(esperar(lambda: e.snapshot()["ruta"]))
        e.enviar("CARGA_RAMPA,1")
        self.assertTrue(esperar(lambda: self.nav.carga[1] is False and self.nav._ok_carga[1]))
        self.nav.paso((0, 0, 1, 0, 0), "NINGUNO")
        self.assertTrue(esperar(lambda: e.snapshot()["ruta"]["carga_r1"] and e.snapshot()["ruta"]["fase"] == "ST1_INDEXANDO"))
        e.detener()
        self.assertIsNone(e.snapshot()["ruta"])                      # al perder el enlace no quedan datos viejos
        self.assertIsNone(e.snapshot()["cal_esquema"])
        self.assertEqual(e.url_video(), "")

    def test_url_de_video_lleva_el_token_codificado_y_el_lector_recibe_cuadros(self):
        e = self.enlace()
        self.assertTrue(esperar(lambda: e.snapshot()["estado"] == "conectado"))
        url = e.url_video(puerto=self.video.server_address[1])
        self.assertIn("t=Token%2FDe%2BPrueba%3D1", url)
        cuadros, estados = [], []
        lector = LectorVideo(lambda: url, cuadros.append, estados.append)
        lector.iniciar()
        self.cierres.append(lector.detener)
        self.assertTrue(esperar(lambda: len(cuadros) >= 2))
        self.assertEqual(cuadros[0], b"\xff\xd8CUADRO\xff\xd9")
        self.assertIn("En vivo", estados)

    def test_lector_con_token_malo_se_detiene_y_no_lo_muestra(self):
        estados = []
        url = "http://127.0.0.1:%d/stream.mjpg?t=malo" % self.video.server_address[1]
        lector = LectorVideo(lambda: url, lambda c: None, estados.append)
        lector.iniciar()
        self.cierres.append(lector.detener)
        self.assertTrue(esperar(lambda: any("rechazó" in x for x in estados)))
        self.assertNotIn("malo", " ".join(estados))

    def test_lector_reintenta_si_el_servidor_no_esta(self):
        estados = []
        lector = LectorVideo(lambda: "http://127.0.0.1:1/stream.mjpg", lambda c: None, estados.append)
        lector.iniciar()
        self.cierres.append(lector.detener)
        self.assertTrue(esperar(lambda: any("Sin video" in x for x in estados)))


if __name__ == "__main__":
    unittest.main()
