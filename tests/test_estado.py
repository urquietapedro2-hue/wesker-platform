import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

from core.estado import sanear_albert, sanear_zeno  # noqa: E402

ALBERT_VALIDO = {
    "modo": "AUTO", "receta": "PINTO", "dinamica": False, "resumen": "Pinto x4", "motor": "REPOSO",
    "ang_obj": 675.0, "silo": 2, "slots": ["PINTO", None, "VACIO", None, None, None, "NEGRO", "PERUANO"],
    "tapas": [True, False, False, False, False, False, False, False], "terminados": 9, "est1": "STANDBY",
    "tolva": 55.5, "tipo_tolva": "PINTO", "servo_tolva": False, "servos": [False, True, False], "fase": "VERTIDO",
    "silo_desc": 1, "comp_obj": [0.0, 85.0, 0.0], "silos_sel": [1], "tapa_obj": 30.0, "tapa_anim": False,
    "piston_obj": 0.0, "sellando": False, "corriendo": True, "restante": 5,
}
BASURA = [None, 5, "texto", [], [1, 2, 3], {"x": {"y": 1}}, float("nan"), True, 10 ** 30, -10 ** 30, {"a": [None]}]


class TestAlbert(unittest.TestCase):
    def test_un_estado_valido_pasa_intacto(self):
        self.assertEqual(sanear_albert(json.loads(json.dumps(ALBERT_VALIDO))), ALBERT_VALIDO)

    def test_basura_en_cualquier_campo_nunca_lanza_excepciones(self):
        for clave in ALBERT_VALIDO:
            for malo in BASURA:
                estado = dict(ALBERT_VALIDO, **{clave: malo})
                limpio = sanear_albert(estado)
                self.assertIsInstance(limpio, dict)
        for malo in BASURA:
            self.assertIsInstance(sanear_albert(malo), dict)

    def test_los_valores_invalidos_se_descartan(self):
        limpio = sanear_albert({"silo": "abc", "ang_obj": "x", "tolva": None, "terminados": [1], "fase": "HACKEADO",
                                "slots": [1, 2], "modo": {"a": 1}})
        self.assertEqual(limpio, {})

    def test_los_rangos_se_limitan(self):
        limpio = sanear_albert({"tolva": 9999, "silo": -50, "ang_obj": 10 ** 30, "piston_obj": 7})
        self.assertEqual((limpio["tolva"], limpio["silo"], limpio["ang_obj"], limpio["piston_obj"]), (100.0, 0, 1e7, 1.0))

    def test_un_tipo_de_vaso_desconocido_se_convierte_en_vacio_y_none_se_conserva(self):
        limpio = sanear_albert({"slots": ["PINTO", "MALWARE", None, 5, "NEGRO", "VACIO", "x", None]})
        self.assertEqual(limpio["slots"], ["PINTO", "VACIO", None, "VACIO", "NEGRO", "VACIO", "VACIO", None])

    def test_tolva_sin_grano_es_valida(self):
        self.assertIn("tipo_tolva", sanear_albert({"tipo_tolva": None}))
        self.assertNotIn("tipo_tolva", sanear_albert({"tipo_tolva": "ARSENICO"}))
        self.assertNotIn("tipo_tolva", sanear_albert({}))

    def test_los_textos_largos_se_recortan(self):
        self.assertEqual(len(sanear_albert({"resumen": "x" * 5000})["resumen"]), 200)


class TestZeno(unittest.TestCase):
    def test_telemetria_valida(self):
        e = {"modo": "MANUAL", "dir": "FL", "pwm": 45, "dist": 20.5, "sens": [1, 1, 0, 0, 0], "sub": "ESTACION_DESCARGA",
             "qr": "ESTACION_2", "seg": "curva", "corriendo": True}
        self.assertEqual(sanear_zeno(e), {"modo": "MANUAL", "direccion": "FL", "velocidad": 45, "distancia": 20.5,
                                          "sensores": [1, 1, 0, 0, 0], "subestado": "ESTACION_DESCARGA",
                                          "qr": "ESTACION_2", "tramo": "curva", "corriendo": True})

    def test_basura_da_siempre_una_telemetria_segura(self):
        seguro = sanear_zeno({})
        for malo in BASURA:
            self.assertEqual(sanear_zeno(malo), seguro)
            for clave in ("modo", "dir", "pwm", "dist", "sens", "sub", "qr", "seg", "corriendo"):
                limpio = sanear_zeno({clave: malo})
                self.assertIn(limpio["direccion"], {"F", "B", "L", "R", "FL", "FR", "BL", "BR", "S", "ESTACION"})
                self.assertTrue(0 <= limpio["velocidad"] <= 100)
                self.assertTrue(0.0 <= limpio["distancia"] <= 500.0)
                self.assertEqual(len(limpio["sensores"]), 5)
                self.assertIsInstance(limpio["qr"], str)

    def test_valores_por_defecto(self):
        s = sanear_zeno(None)
        self.assertEqual((s["direccion"], s["velocidad"], s["distancia"], s["subestado"], s["qr"]),
                         ("S", 0, 85.0, "SEGUIMIENTO", "NINGUNO"))


if __name__ == "__main__":
    unittest.main()
