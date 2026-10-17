import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

from core.permissions import nota_rol, puede_controlar  # noqa: E402
from core.sim import AlbertSimulator, ZenoSimulator  # noqa: E402


class TestZeno(unittest.TestCase):
    def test_arranca_en_recta(self):
        d = ZenoSimulator().tick(0.1)
        self.assertEqual((d["direccion"], d["velocidad"], d["subestado"]), ("F", 60, "SEGUIMIENTO"))
        self.assertEqual(d["sensores"], [0, 0, 1, 0, 0])

    def test_formato_compatible_con_el_gemelo(self):
        d = ZenoSimulator().tick(0.1)
        self.assertEqual(set(d), {"direccion", "velocidad", "distancia", "sensores", "subestado", "qr"})
        self.assertEqual(len(d["sensores"]), 5)

    def test_recorrido_completo(self):
        s = ZenoSimulator()
        s.tick(4.5)
        self.assertEqual(s.segmento, "curva izquierda")
        d = s.tick(10.0)  # t = 14.5 -> estación
        self.assertEqual((d["subestado"], d["velocidad"], d["qr"]), ("ESTACION_DESCARGA", 0, "ESTACION_2"))
        d = s.tick(5.0)   # t = 19.5 -> nueva vuelta
        self.assertEqual((d["direccion"], s.vueltas), ("F", 1))

    def test_obstaculo_congela_el_recorrido(self):
        s = ZenoSimulator()
        s.provocar_obstaculo(2.0)
        d = s.tick(1.0)
        self.assertEqual((d["velocidad"], d["distancia"]), (0, ZenoSimulator.DISTANCIA_OBSTACULO))
        s.tick(1.5)
        self.assertEqual(s.t, 0.0)
        d = s.tick(0.1)
        self.assertEqual((d["velocidad"], s.t), (60, 0.1))

    def test_escala_y_dt_negativo(self):
        s = ZenoSimulator()
        s.tick(1.0, escala=2.0)
        self.assertEqual(s.t, 2.0)
        s.tick(-5.0)
        self.assertEqual(s.t, 2.0)


class TestAlbert(unittest.TestCase):
    def test_inactivo_no_da_pasos(self):
        self.assertEqual(AlbertSimulator().tick(100.0), 0)

    def test_primer_paso_pronto_y_luego_cada_periodo(self):
        s = AlbertSimulator()
        s.iniciar()
        self.assertEqual(s.tick(2.9), 0)
        self.assertEqual(s.tick(0.2), 1)
        self.assertEqual(s.tick(7.9), 0)
        self.assertEqual(s.tick(0.2), 1)

    def test_nunca_acumula_pasos_atrasados(self):
        s = AlbertSimulator()
        s.iniciar()
        self.assertEqual(s.tick(100.0), 1)
        self.assertEqual(s.tick(0.1), 0)

    def test_periodo_minimo_protege_el_sellado(self):
        s = AlbertSimulator()
        s.set_periodo(3)
        self.assertEqual(s.periodo, AlbertSimulator.PERIODO_MIN)
        s.set_periodo(12)
        self.assertEqual(s.periodo, 12.0)

    def test_detener(self):
        s = AlbertSimulator()
        s.iniciar()
        s.detener()
        self.assertEqual(s.tick(100.0), 0)


class TestPermisos(unittest.TestCase):
    def test_roles(self):
        for r in ("ADMIN", "OPERATOR", "MAINTENANCE"):
            self.assertTrue(puede_controlar(r))
            self.assertEqual(nota_rol(r), "")
        self.assertFalse(puede_controlar("VIEWER"))
        self.assertIn("VIEWER", nota_rol("VIEWER"))
        self.assertFalse(puede_controlar("INVENTADO"))


if __name__ == "__main__":
    unittest.main()
