import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "desktop"))

from core.calibracion_hmi import Acumulador, agrupar, cmd_probar, cmd_set, diferencias, formatear_valor  # noqa: E402

P_INT = {"clave": "vel_auto_max", "grupo": "Tracción", "tipo": "int", "min": 10, "max": 100, "probar": None}
P_FLT = {"clave": "direccion_max", "grupo": "Dirección", "tipo": "float", "min": 45.0, "max": 135.0, "probar": "direccion"}
P_BOOL = {"clave": "direccion_invertida", "grupo": "Dirección", "tipo": "bool", "min": None, "max": None, "probar": None}


class TestComandos(unittest.TestCase):
    def test_formato_y_acotado(self):
        self.assertEqual(cmd_set(P_INT, 40.4), "CAL_SET,vel_auto_max,40")
        self.assertEqual(cmd_set(P_INT, 500), "CAL_SET,vel_auto_max,100")
        self.assertEqual(cmd_set(P_FLT, 120.5), "CAL_SET,direccion_max,120.5")
        self.assertEqual(cmd_set(P_FLT, 120.0), "CAL_SET,direccion_max,120")
        self.assertEqual(cmd_set(P_FLT, -5), "CAL_SET,direccion_max,45")
        self.assertEqual((formatear_valor(P_BOOL, True), formatear_valor(P_BOOL, False)), ("true", "false"))

    def test_probar_solo_si_el_parametro_tiene_servo(self):
        self.assertEqual(cmd_probar(P_FLT, 127.6), "CAL_PROBAR,direccion,128")
        self.assertEqual(cmd_probar(P_FLT, 999), "CAL_PROBAR,direccion,180")
        self.assertIsNone(cmd_probar(P_INT, 40))

    def test_agrupar_conserva_el_orden(self):
        g = agrupar([P_INT, P_FLT, P_BOOL])
        self.assertEqual([n for n, _ in g], ["Tracción", "Dirección"])
        self.assertEqual(len(g[1][1]), 2)
        self.assertEqual(agrupar(None), [])

    def test_diferencias(self):
        self.assertEqual(diferencias([P_INT, P_FLT], {"vel_auto_max": 30, "direccion_max": 125.0}, {"vel_auto_max": 45, "direccion_max": 125.0}),
                         ["vel_auto_max"])


class TestAcumulador(unittest.TestCase):
    def test_arrastrar_una_barra_manda_un_solo_comando_con_el_ultimo_valor(self):
        a = Acumulador(0.25)
        for i, v in enumerate((50, 55, 60, 65, 70)):
            a.editar(P_INT, v, 10.0 + i * 0.05)
            self.assertEqual(a.listos(10.0 + i * 0.05), [])
        self.assertTrue(a.pendiente("vel_auto_max"))
        self.assertEqual(a.listos(10.5), ["CAL_SET,vel_auto_max,70"])
        self.assertEqual(a.listos(11.0), [])
        self.assertFalse(a.pendiente())

    def test_parametros_distintos_salen_por_separado_y_descartar_limpia(self):
        a = Acumulador(0.25)
        a.editar(P_INT, 40, 0.0)
        a.editar(P_FLT, 100, 0.2)
        self.assertEqual(a.listos(0.3), ["CAL_SET,vel_auto_max,40"])
        a.descartar()
        self.assertEqual(a.listos(9.0), [])


if __name__ == "__main__":
    unittest.main()
