"""Máquina de estados de la ruta (3 estaciones, 2 rampas) con reloj manual y rampas/pan falsos."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from falsos import calibracion_prueba  # noqa: E402
from zeno.ruta import FASES, Ruta  # noqa: E402

RECTO, VACIO, TODOS, IZQ = (0, 0, 1, 0, 0), (0, 0, 0, 0, 0), (1, 1, 1, 1, 1), (1, 1, 0, 0, 0)


class RampasFalsas:
    def __init__(self): self.llamadas, self.est = [], {1: None, 2: None}
    def abrir(self, n): self.llamadas.append(("abrir", n)); self.est[n] = "ABIERTA"
    def cerrar(self, n): self.llamadas.append(("cerrar", n)); self.est[n] = "CERRADA"
    def cerrar_todas(self): self.llamadas.append(("cerrar_todas",)); self.est = {1: "CERRADA", 2: "CERRADA"}
    def olvidar(self): self.llamadas.append(("olvidar",))


class PanFalso:
    def __init__(self): self.llamadas = []
    def centrar(self): self.llamadas.append("centrar")
    def barrido(self): self.llamadas.append("barrido")


class Base(unittest.TestCase):
    def setUp(self):
        self.t = 1000.0
        self.cal = calibracion_prueba(debounce_interseccion_ms=150)
        self.rampas, self.pan = RampasFalsas(), PanFalso()
        self.ruta = Ruta(self.cal, self.rampas, self.pan, reloj=lambda: self.t)
        self.ruta.cambiar_modo("AUTO")

    def paso(self, sensores=RECTO, qr="NINGUNO", avanzar=0.0):
        self.t += avanzar
        return self.ruta.paso(sensores, qr, self.t)

    def fase(self):
        return self.ruta.fase

    def avanzar_hasta(self, fase, sensores=RECTO, qr="NINGUNO", maximo=60.0, paso=0.05):
        fin = self.t + maximo
        while self.fase() != fase and self.t < fin:
            self.paso(sensores, qr, paso)
        self.assertEqual(self.fase(), fase)

    def ir_a_seguimiento(self):
        self.ruta.carga_rampa(1)
        self.paso()
        self.avanzar_hasta("ST1_CARGA_R2")
        self.ruta.carga_rampa(2)
        self.paso()
        self.avanzar_hasta("SEGUIMIENTO")

    def ir_a_escaneo(self):
        self.ir_a_seguimiento()
        self.paso(TODOS)
        self.avanzar_hasta("ESCANEANDO_QR", TODOS)


class TestEstacion1(Base):
    def test_arranca_en_la_estacion_1_con_las_rampas_bloqueadas_y_sin_moverse(self):
        self.assertEqual(self.fase(), "ST1_CARGA_R1")
        self.assertEqual(self.rampas.llamadas[0], ("cerrar_todas",))
        self.assertIn("centrar", self.pan.llamadas)
        o = self.paso(RECTO, avanzar=5.0)
        self.assertEqual((o.cmd, o.vel), ("S", 0))              # espera, aunque la línea esté a la vista

    def test_la_carga_se_acepta_solo_en_su_turno(self):
        self.assertFalse(self.ruta.carga_rampa(2))                # primero la 1
        self.assertTrue(self.ruta.carga_rampa(1))
        self.paso()
        self.assertFalse(self.ruta.carga_rampa(1))                # la 1 ya pasó
        self.assertEqual(self.fase(), "ST1_INDEXANDO")

    def test_indexacion_avanza_el_tiempo_y_el_pwm_calibrados_y_luego_para(self):
        self.cal.set_many({"t_indexacion_ms": 400, "vel_indexacion": 33})
        self.ruta.carga_rampa(1)
        o = self.paso()
        self.assertEqual((o.cmd, o.vel, self.fase()), ("F", 33, "ST1_INDEXANDO"))
        self.assertEqual(self.paso(avanzar=0.39).cmd, "F")
        o = self.paso(avanzar=0.02)
        self.assertEqual((o.cmd, o.vel, self.fase()), ("S", 0, "ST1_CARGA_R2"))

    def test_el_tiempo_de_indexacion_se_puede_cambiar_en_vivo(self):
        self.ruta.carga_rampa(1)
        self.paso()
        self.cal.set("t_indexacion_ms", 1000)
        self.assertEqual(self.paso(avanzar=0.5).cmd, "F")
        self.assertEqual(self.paso(avanzar=0.6).cmd, "S")

    def test_con_la_rampa_2_cargada_sale_a_ciegas_y_empieza_a_seguir_la_linea(self):
        self.cal.set_many({"vel_auto_max": 38, "t_salida_s": 1.0})
        self.ruta.carga_rampa(1)
        self.paso()
        self.avanzar_hasta("ST1_CARGA_R2")
        self.ruta.carga_rampa(2)
        o = self.paso()
        self.assertEqual((o.cmd, o.vel, self.fase()), ("F", 38, "SALIENDO"))
        self.assertEqual(self.paso(TODOS, avanzar=0.5).cmd, "F")  # ignora la marca de la estación mientras sale
        self.assertEqual(self.fase(), "SALIENDO")
        self.paso(RECTO, avanzar=0.6)
        self.assertEqual(self.fase(), "SEGUIMIENTO")
        self.assertEqual(self.ruta.estado()["carga_r1"], True)
        self.assertEqual(self.ruta.estado()["carga_r2"], True)

    def test_sin_carga_nunca_sale_solo_solo_avisa(self):
        self.cal.set("t_carga_max_s", 10.0)
        self.paso(avanzar=9.0)
        self.assertEqual(self.ruta.estado()["alarma"], "NINGUNA")
        self.paso(avanzar=2.0)
        self.assertEqual(self.ruta.estado()["alarma"], "TIMEOUT_CARGA")
        for _ in range(50):
            self.assertEqual(self.paso(RECTO, avanzar=10.0).cmd, "S")
        self.assertEqual(self.fase(), "ST1_CARGA_R1")
        self.assertTrue(self.ruta.carga_rampa(1))                # y se resuelve cuando por fin llega la carga
        self.paso()
        self.assertEqual((self.fase(), self.ruta.estado()["alarma"]), ("ST1_INDEXANDO", "NINGUNA"))


class TestNavegacion(Base):
    def test_seguimiento_con_tope_de_pwm_calibrable(self):
        self.ir_a_seguimiento()
        self.cal.set("vel_auto_max", 30)
        for sensores, esperado in ((RECTO, ("F", 30)), (IZQ, ("L", 30)), ((0, 0, 0, 1, 0), ("R", 30))):
            o = self.paso(sensores)
            self.assertEqual((o.cmd, o.vel), esperado)
        self.cal.set("vel_auto_max", 100)
        self.assertEqual(self.paso(RECTO).vel, 45)                # sin tope vuelve a las velocidades de V2
        self.cal.set("vel_auto_max", 43)
        self.assertEqual(self.paso(IZQ).vel, 42)                  # solo recorta lo que lo supera

    def test_sin_regla_mantiene_y_linea_perdida_detiene(self):
        self.ir_a_seguimiento()
        self.assertIsNone(self.paso((1, 0, 0, 0, 1)).cmd)         # combinación sin regla en V2
        self.assertEqual(self.paso(VACIO).cmd, "S")

    def test_debounce_exige_los_5_sensores_durante_el_tiempo_calibrado(self):
        self.ir_a_seguimiento()
        self.assertIsNone(self.paso(TODOS).cmd)                   # empieza el conteo: mantiene lo que hacía
        self.paso(TODOS, avanzar=0.10)
        self.assertEqual(self.fase(), "SEGUIMIENTO")
        o = self.paso(TODOS, avanzar=0.06)
        self.assertEqual((o.cmd, o.vel, o.camara, self.fase()), ("S", 0, True, "ESCANEANDO_QR"))
        self.assertIn("barrido", self.pan.llamadas)

    def test_un_destello_corto_no_detiene_y_reinicia_el_conteo(self):
        self.ir_a_seguimiento()
        self.paso(TODOS)
        self.paso(TODOS, avanzar=0.10)                            # 100 ms: aún no
        self.paso(RECTO, avanzar=0.01)                            # el brillo se fue
        self.paso(TODOS, avanzar=0.01)
        self.paso(TODOS, avanzar=0.10)
        self.assertEqual(self.fase(), "SEGUIMIENTO")              # el conteo empezó de cero
        self.paso(TODOS, avanzar=0.06)
        self.assertEqual(self.fase(), "ESCANEANDO_QR")

    def test_debounce_se_cambia_en_vivo(self):
        self.ir_a_seguimiento()
        self.cal.set("debounce_interseccion_ms", 0)
        self.paso(TODOS)
        self.assertEqual(self.fase(), "ESCANEANDO_QR")
        self.setUp()
        self.ir_a_seguimiento()
        self.cal.set("debounce_interseccion_ms", 500)
        self.paso(TODOS)
        self.paso(TODOS, avanzar=0.4)
        self.assertEqual(self.fase(), "SEGUIMIENTO")
        self.paso(TODOS, avanzar=0.2)
        self.assertEqual(self.fase(), "ESCANEANDO_QR")


class TestEstaciones2y3(Base):
    def test_qr_estacion_2_abre_la_rampa_1_espera_20_s_la_cierra_y_sigue(self):
        self.ir_a_escaneo()
        o = self.paso(TODOS, "ESTACION_2", 0.1)
        self.assertEqual((o.cmd, o.camara, self.fase()), ("S", False, "DESCARGANDO"))
        self.assertEqual(self.rampas.llamadas[-1], ("abrir", 1))
        self.assertEqual(self.ruta.estado()["estacion"], "ESTACION_2")
        self.assertEqual(self.paso(TODOS, "ESTACION_2", 19.8).cmd, "S")
        self.assertAlmostEqual(self.ruta.estado()["restante_s"], 0.2, places=2)
        self.assertEqual(self.rampas.est[1], "ABIERTA")
        o = self.paso(TODOS, "ESTACION_2", 0.3)
        self.assertEqual((o.cmd, self.fase(), self.rampas.est[1]), ("F", "SALIENDO", "CERRADA"))
        self.assertFalse(self.ruta.estado()["carga_r1"])
        self.assertTrue(self.ruta.estado()["carga_r2"])           # la rampa 2 sigue cargada

    def test_qr_estacion_3_usa_la_rampa_2_y_la_espera_es_programable(self):
        self.cal.set("t_espera_descarga_s", 5.0)
        self.ir_a_escaneo()
        self.paso(TODOS, "ESTACION_3", 0.1)
        self.assertEqual(self.rampas.llamadas[-1], ("abrir", 2))
        self.paso(TODOS, "ESTACION_3", 4.8)
        self.assertEqual(self.fase(), "DESCARGANDO")
        self.paso(TODOS, "ESTACION_3", 0.3)
        self.assertEqual((self.fase(), self.rampas.est[2], self.ruta.estado()["carga_r2"]), ("SALIENDO", "CERRADA", False))

    def test_el_tiempo_de_espera_puede_cambiar_con_la_rampa_abierta(self):
        self.ir_a_escaneo()
        self.paso(TODOS, "ESTACION_2", 0.1)
        self.cal.set("t_espera_descarga_s", 2.0)
        self.paso(TODOS, "ESTACION_2", 2.1)
        self.assertEqual(self.fase(), "SALIENDO")

    def test_despues_de_descargar_sale_a_ciegas_y_no_vuelve_a_detectar_la_misma_interseccion(self):
        self.cal.set_many({"t_espera_descarga_s": 1.0, "t_salida_s": 1.0})
        self.ir_a_escaneo()
        self.paso(TODOS, "ESTACION_2", 0.1)
        self.paso(TODOS, "ESTACION_2", 1.1)
        self.assertEqual(self.fase(), "SALIENDO")
        for _ in range(8):                                        # sigue sobre la marca (5 sensores) mientras avanza
            self.assertEqual(self.paso(TODOS, "ESTACION_2", 0.1).cmd, "F")
        self.assertEqual(self.fase(), "SALIENDO")
        self.paso(RECTO, "NINGUNO", 0.5)
        self.assertEqual(self.fase(), "SEGUIMIENTO")

    def test_qr_no_valido_se_ignora_y_sin_qr_avisa_pero_no_avanza(self):
        self.cal.set("t_escaneo_qr_s", 8.0)
        self.ir_a_escaneo()
        for qr in ("BASURA", "ESTACION_9", "NINGUNO", "estacion_2", ""):
            self.assertEqual(self.paso(TODOS, qr, 0.5).cmd, "S")
        self.assertEqual((self.fase(), self.ruta.estado()["alarma"]), ("ESCANEANDO_QR", "NINGUNA"))
        self.paso(TODOS, "NINGUNO", 6.0)                           # ya van 8.5 s desde que empezó a buscar
        self.assertEqual(self.ruta.estado()["alarma"], "QR_NO_LEIDO")
        self.assertEqual(self.paso(TODOS, "NINGUNO", 30.0).cmd, "S")
        self.assertEqual(self.fase(), "ESCANEANDO_QR")             # parado: no cruza una intersección sin saber cuál es
        self.paso(TODOS, "ESTACION_3", 0.1)                        # si por fin lo lee, continúa y la alarma desaparece
        self.assertEqual((self.fase(), self.ruta.estado()["alarma"]), ("DESCARGANDO", "NINGUNA"))

    def test_qr_estacion_1_vuelve_a_empezar_el_ciclo_de_carga(self):
        self.ir_a_escaneo()
        self.rampas.llamadas.clear()
        o = self.paso(TODOS, "ESTACION_1", 0.1)
        self.assertEqual((o.cmd, self.fase()), ("S", "ST1_CARGA_R1"))
        self.assertEqual(self.rampas.llamadas, [("cerrar_todas",)])

    def test_ciclo_completo_1_2_3_1(self):
        self.cal.set_many({"t_espera_descarga_s": 2.0, "t_salida_s": 0.5, "t_indexacion_ms": 100})
        self.ir_a_seguimiento()
        for qr, rampa in (("ESTACION_2", 1), ("ESTACION_3", 2)):
            self.paso(TODOS)
            self.avanzar_hasta("ESCANEANDO_QR", TODOS)
            self.paso(TODOS, qr, 0.1)
            self.avanzar_hasta("DESCARGANDO", TODOS, qr)
            self.avanzar_hasta("SALIENDO", TODOS, qr)
            self.avanzar_hasta("SEGUIMIENTO", RECTO)
            self.assertIn(("abrir", rampa), self.rampas.llamadas)
            self.assertIn(("cerrar", rampa), self.rampas.llamadas)
        self.paso(TODOS)
        self.avanzar_hasta("ESCANEANDO_QR", TODOS)
        self.paso(TODOS, "ESTACION_1", 0.1)
        self.assertEqual(self.fase(), "ST1_CARGA_R1")
        self.assertEqual((self.ruta.estado()["carga_r1"], self.ruta.estado()["carga_r2"]), (False, False))


class TestOperador(Base):
    def test_abortar_en_la_estacion_1_salta_la_carga_y_sigue_la_linea(self):
        self.assertTrue(self.ruta.abortar())
        o = self.paso()
        self.assertEqual((o.cmd, self.fase()), ("F", "SALIENDO"))

    def test_abortar_con_la_rampa_abierta_la_cierra(self):
        self.ir_a_escaneo()
        self.paso(TODOS, "ESTACION_2", 0.1)
        self.assertTrue(self.ruta.abortar())
        self.paso(TODOS, "ESTACION_2", 0.1)
        self.assertEqual((self.fase(), self.rampas.est[1]), ("SALIENDO", "CERRADA"))

    def test_abortar_en_escaneo_cruza_la_interseccion(self):
        self.ir_a_escaneo()
        self.assertTrue(self.ruta.abortar())
        self.paso(TODOS, "NINGUNO", 0.1)
        self.assertEqual(self.fase(), "SALIENDO")

    def test_abortar_no_hace_nada_siguiendo_la_linea_ni_en_manual(self):
        self.ir_a_seguimiento()
        self.assertFalse(self.ruta.abortar())
        self.ruta.cambiar_modo("MANUAL")
        self.assertFalse(self.ruta.abortar())

    def test_manual_no_decide_suelta_el_seguimiento_de_rampas_y_auto_reinicia_en_la_estacion_1(self):
        self.ir_a_seguimiento()
        self.ruta.cambiar_modo("MANUAL")
        self.assertEqual((self.fase(), self.ruta.sub, self.paso(TODOS).cmd), ("MANUAL", "SEGUIMIENTO", None))
        self.assertIn(("olvidar",), self.rampas.llamadas)
        self.assertFalse(self.ruta.carga_rampa(1))
        self.ruta.cambiar_modo("AUTO")
        self.assertEqual(self.fase(), "ST1_CARGA_R1")

    def test_cambiar_a_manual_en_plena_descarga_descarta_lo_pendiente(self):
        self.ruta.carga_rampa(1)
        self.ruta.cambiar_modo("MANUAL")
        self.ruta.cambiar_modo("AUTO")
        self.paso()
        self.assertEqual(self.fase(), "ST1_CARGA_R1")             # la señal vieja no se arrastra

    def test_subestado_compatible_con_el_formato_telem_de_siempre(self):
        esperado = {"ST1_CARGA_R1": "ESTACION_DESCARGA", "ST1_INDEXANDO": "ESTACION_DESCARGA", "ST1_CARGA_R2": "ESTACION_DESCARGA",
                    "SEGUIMIENTO": "SEGUIMIENTO", "ESCANEANDO_QR": "ESTACION_DESCARGA", "DESCARGANDO": "ESTACION_DESCARGA",
                    "SALIENDO": "SEGUIMIENTO", "MANUAL": "SEGUIMIENTO"}
        self.assertEqual(set(esperado), set(FASES))
        for f, sub in esperado.items():
            self.ruta.fase = f
            self.assertEqual(self.ruta.sub, sub, f)

    def test_parametros_invalidos(self):
        with self.assertRaises(ValueError):
            Ruta(self.cal, self.rampas, self.pan, "INVENTADA")
        with self.assertRaises(ValueError):
            Ruta(self.cal, self.rampas, self.pan, fase_inicial="VOLANDO")

    def test_logica_nueva_tambien_funciona(self):
        r = Ruta(self.cal, self.rampas, self.pan, "NUEVA", reloj=lambda: self.t, fase_inicial="SEGUIMIENTO")
        o = r.paso((1, 0, 0, 0, 1), "NINGUNO", self.t)
        self.assertEqual((o.cmd, o.vel), ("L", 42))


if __name__ == "__main__":
    unittest.main()
