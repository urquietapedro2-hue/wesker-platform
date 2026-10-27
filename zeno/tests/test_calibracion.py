import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from zeno.calibracion import DEFECTOS, ESQUEMA, Calibracion, ErrorCalibracion  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ruta = os.path.join(self.dir, "sub", "cal.json")
        self.cal = Calibracion(self.ruta)


class TestValores(Base):
    def test_sin_archivo_usa_los_valores_de_fabrica(self):
        self.assertEqual(self.cal.valores(), DEFECTOS)
        self.assertFalse(self.cal.sin_guardar)
        self.assertEqual((self.cal["vel_auto_max"], self.cal["t_espera_descarga_s"], self.cal["debounce_interseccion_ms"]), (45, 20.0, 150))

    def test_el_esquema_cubre_todo_lo_pedido(self):
        pedidos = {"direccion_centro", "direccion_min", "direccion_max", "camara_centro", "camara_min", "camara_max",
                   "rampa1_cerrado", "rampa1_abierto", "rampa2_cerrado", "rampa2_abierto", "vel_auto_max",
                   "t_espera_descarga_s", "t_indexacion_ms", "debounce_interseccion_ms"}
        self.assertTrue(pedidos <= set(ESQUEMA))
        for k, e in ESQUEMA.items():
            self.assertEqual(self.cal[k], e["defecto"])
            if e["tipo"] != "bool":
                self.assertTrue(e["min"] <= e["defecto"] <= e["max"], k)

    def test_set_valida_tipo_rango_y_clave(self):
        self.assertEqual(self.cal.set("vel_auto_max", "40"), 2)           # llega como texto por la red (versión 1 = carga inicial)
        self.assertEqual(self.cal["vel_auto_max"], 40)
        for clave, malo in (("vel_auto_max", 101), ("vel_auto_max", 5), ("vel_auto_max", 40.5), ("vel_auto_max", "abc"),
                            ("vel_auto_max", float("nan")), ("vel_auto_max", True), ("direccion_max", 200), ("t_espera_descarga_s", -1),
                            ("direccion_invertida", "quizas"), ("direccion_invertida", 1), ("inventado", 1)):
            with self.assertRaises(ErrorCalibracion, msg=(clave, malo)):
                self.cal.set(clave, malo)
        self.assertEqual(self.cal["vel_auto_max"], 40)                      # lo rechazado no cambia nada

    def test_bool_acepta_true_false_en_texto(self):
        self.cal.set("direccion_invertida", "true")
        self.assertIs(self.cal["direccion_invertida"], True)

    def test_coherencia_minimo_centro_maximo_y_rampas(self):
        with self.assertRaises(ErrorCalibracion):
            self.cal.set("direccion_min", 100.0)                             # > centro (90)
        with self.assertRaises(ErrorCalibracion):
            self.cal.set("camara_max", 80.0)
        with self.assertRaises(ErrorCalibracion):
            self.cal.set("rampa1_abierto", 92.0)                             # casi igual al bloqueo
        self.cal.set_many({"direccion_centro": 100.0, "direccion_min": 95.0})   # en conjunto sí es coherente

    def test_set_many_es_todo_o_nada(self):
        antes = self.cal.valores()
        with self.assertRaises(ErrorCalibracion):
            self.cal.set_many({"vel_auto_max": 30, "t_indexacion_ms": 99999})
        self.assertEqual(self.cal.valores(), antes)
        with self.assertRaises(ErrorCalibracion):
            self.cal.set_many({})

    def test_version_y_suscriptores(self):
        avisos = []
        self.cal.suscribir(lambda: avisos.append(self.cal["vel_auto_max"]))
        self.cal.set("vel_auto_max", 30)
        self.cal.set("vel_auto_max", 30)                                     # sin cambio real: no avisa ni sube versión
        self.assertEqual((avisos, self.cal.version), ([30], 2))              # 1 de la carga inicial + 1 del cambio
        self.cal.suscribir(lambda: 1 / 0)                                    # un suscriptor roto no rompe a nadie
        self.cal.set("vel_auto_max", 35)
        self.assertEqual(self.cal["vel_auto_max"], 35)


class TestArchivo(Base):
    def test_guardar_y_recargar(self):
        self.cal.set_many({"vel_auto_max": 33, "direccion_max": 120.0, "direccion_invertida": True})
        self.assertTrue(self.cal.sin_guardar)
        self.cal.guardar()
        self.assertFalse(self.cal.sin_guardar)
        otra = Calibracion(self.ruta)
        self.assertEqual((otra["vel_auto_max"], otra["direccion_max"], otra["direccion_invertida"]), (33, 120.0, True))
        self.assertEqual([f for f in os.listdir(os.path.dirname(self.ruta)) if "tmp" in f], [])   # sin temporales sobrantes
        with open(self.ruta) as f:
            self.assertEqual(json.load(f)["formato"], 1)

    def test_lo_no_guardado_se_pierde_al_restaurar(self):
        self.cal.set("vel_auto_max", 33)
        self.cal.guardar()
        self.cal.set("vel_auto_max", 20)
        self.cal.restaurar()
        self.assertEqual(self.cal["vel_auto_max"], 33)

    def test_defecto_no_toca_el_archivo_hasta_guardar(self):
        self.cal.set("vel_auto_max", 33)
        self.cal.guardar()
        self.cal.defecto()
        self.assertEqual(self.cal["vel_auto_max"], 45)
        self.assertEqual(Calibracion(self.ruta)["vel_auto_max"], 33)

    def test_archivo_corrupto_no_impide_arrancar_y_se_aparta(self):
        os.makedirs(os.path.dirname(self.ruta))
        with open(self.ruta, "w") as f:
            f.write("{esto no es json")
        cal = Calibracion(self.ruta)
        self.assertEqual(cal.valores(), DEFECTOS)
        self.assertTrue(cal.avisos)
        self.assertTrue(any(".corrupto." in f for f in os.listdir(os.path.dirname(self.ruta))))

    def test_valores_invalidos_en_el_archivo_se_sustituyen_uno_a_uno(self):
        os.makedirs(os.path.dirname(self.ruta))
        with open(self.ruta, "w") as f:
            json.dump({"formato": 1, "valores": {"vel_auto_max": 999, "t_indexacion_ms": 500, "clave_vieja": 1, "direccion_max": "x"}}, f)
        cal = Calibracion(self.ruta)
        self.assertEqual((cal["vel_auto_max"], cal["t_indexacion_ms"], cal["direccion_max"]), (45, 500, 125.0))
        self.assertEqual(len(cal.avisos), 3)

    def test_archivo_incoherente_vuelve_a_fabrica(self):
        os.makedirs(os.path.dirname(self.ruta))
        with open(self.ruta, "w") as f:
            json.dump({"valores": {"direccion_min": 120.0, "direccion_centro": 90.0}}, f)
        cal = Calibracion(self.ruta)
        self.assertEqual(cal.valores(), DEFECTOS)

    def test_estructura_rara_en_el_archivo(self):
        os.makedirs(os.path.dirname(self.ruta))
        for contenido in ("[]", "null", '{"valores": 5}', ""):
            with open(self.ruta, "w") as f:
                f.write(contenido)
            self.assertEqual(Calibracion(self.ruta).valores(), DEFECTOS, contenido)

    def test_instantanea_y_esquema_publico_son_json(self):
        json.dumps(self.cal.instantanea())
        esq = self.cal.esquema_publico()
        json.dumps(esq)
        self.assertEqual(len(esq), len(ESQUEMA))
        self.assertTrue(all({"clave", "grupo", "etiqueta", "tipo", "defecto"} <= set(e) for e in esq))


if __name__ == "__main__":
    unittest.main()
