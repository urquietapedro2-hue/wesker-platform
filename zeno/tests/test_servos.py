import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from falsos import FakeGPIO, FakePCA, calibracion_prueba  # noqa: E402
from zeno import config  # noqa: E402
from zeno.servos import GestorServos, PanCamara, Rampas, angulo_a_us  # noqa: E402


def con_pca(pca=None, cal=None, **kw):
    pca = pca or FakePCA()
    cal = cal or calibracion_prueba()
    return GestorServos(gpio=FakeGPIO(), fabrica_pca=lambda: pca, cal=cal, dormir=lambda s: None, **kw), pca, cal


def sin_pca(cal=None, **kw):
    def falla():
        raise ImportError("No module named 'board'")
    g, cal = FakeGPIO(), cal or calibracion_prueba()
    return GestorServos(gpio=g, fabrica_pca=falla, cal=cal, dormir=lambda s: None, **kw), g, cal


class TestBackends(unittest.TestCase):
    def test_usa_el_pca9685_si_responde(self):
        g, pca, _ = con_pca()
        self.assertEqual((g.backend, g.i2c_ok), ("PCA9685", True))
        g.mover("camara", 90)
        self.assertEqual(pca.pulsos[-1], (config.CANAL_PCA["camara"], 1500.0))

    def test_sin_pca_o_sin_libreria_pasa_a_gpio_sin_configurar_nada(self):
        g, gpio, _ = sin_pca()
        self.assertEqual((g.backend, g.i2c_ok), ("GPIO", False))
        self.assertIn("ImportError", g.motivo_fallback)
        g.mover("camara", 90)
        self.assertAlmostEqual(gpio.pwms[config.PIN_SERVO_CAMARA].duty, 7.5)

    def test_mismo_pulso_en_ambos_backends(self):
        g1, pca, _ = con_pca()
        g2, gpio, _ = sin_pca()
        for g in (g1, g2):
            g.mover("rampa2", 130)
        self.assertAlmostEqual(pca.pulsos[-1][1] / 200.0, gpio.pwms[config.PIN_SERVO_RAMPA[2]].duty)
        self.assertAlmostEqual(angulo_a_us(90) / 200.0, 2.5 + 90 / 18.0)

    def test_sin_i2c_ni_rpi_gpio_no_revienta(self):
        def falla():
            raise OSError("sin i2c")
        g = GestorServos(gpio=None, fabrica_pca=falla, cal=calibracion_prueba())   # en la PC no existe RPi.GPIO
        self.assertEqual(g.backend, "NINGUNO")
        self.assertFalse(g.mover("camara", 90))
        g.cerrar()

    def test_degrada_a_gpio_tras_fallos_seguidos_y_reaplica_posiciones(self):
        g, pca, _ = con_pca(umbral_fallos=3)
        g._gpio = FakeGPIO()
        g.mover("camara", 100)
        pca.roto = True
        for _ in range(2):
            g.mover("camara", 110)
        self.assertEqual(g.backend, "PCA9685")
        g.mover("camara", 120)
        self.assertEqual((g.backend, g.i2c_ok, pca.cerrado), ("GPIO", False, True))
        self.assertAlmostEqual(g._gpio.pwms[config.PIN_SERVO_CAMARA].duty, angulo_a_us(120) / 200.0)

    def test_un_fallo_aislado_no_degrada(self):
        g, pca, _ = con_pca(umbral_fallos=3)
        pca.roto = True
        g.mover("camara", 100)
        pca.roto = False
        g.mover("camara", 100)
        g.mover("camara", 100)
        self.assertEqual(g.backend, "PCA9685")

    def test_pin_roto_no_tumba_a_los_demas(self):
        class G(FakeGPIO):
            def PWM(self, pin, f):
                if pin == config.PIN_SERVO_CAMARA:
                    raise RuntimeError("pin ocupado")
                return super().PWM(pin, f)
        g = GestorServos(gpio=G(), intentar_pca=False, cal=calibracion_prueba())
        self.assertFalse(g.disponible("camara"))
        self.assertTrue(g.mover("rampa1", 90))


class TestMovimiento(unittest.TestCase):
    def test_limites_fisicos_y_trim_calibrado_solo_en_direccion(self):
        g, pca, cal = con_pca()
        g.mover("direccion", 90)
        self.assertAlmostEqual(pca.pulsos[-1][1], angulo_a_us(90 + cal["direccion_trim"]))
        cal.set("direccion_trim", 5.0)                               # el trim se lee de la calibración en cada movimiento
        g.mover("direccion", 90)
        self.assertAlmostEqual(pca.pulsos[-1][1], angulo_a_us(95))
        g.mover("direccion", 500)
        self.assertEqual(g.angulo("direccion"), config.LIMITES_FISICOS["direccion"][1])
        g.mover("camara", 0)
        self.assertEqual(g.angulo("camara"), config.LIMITES_FISICOS["camara"][0])
        g.mover("camara", 90)
        self.assertEqual(pca.pulsos[-1][1], 1500.0)
        with self.assertRaises(KeyError):
            g.mover("fantasma", 10)

    def test_direccion_se_suelta_tras_esperar_y_camara_y_rampas_se_mantienen(self):
        g, pca, _ = con_pca()
        g.mover("direccion", 90, esperar_s=0.18)
        self.assertIn(config.CANAL_PCA["direccion"], pca.apagados)
        for n in ("camara", "rampa1", "rampa2"):
            g.mover(n, 90, esperar_s=0.0)
        self.assertEqual([c for c in pca.apagados if c != config.CANAL_PCA["direccion"]], [])

    def test_estado_y_cierre(self):
        g, pca, _ = con_pca()
        g.mover("camara", 90)
        e = g.estado()
        self.assertEqual((e["backend"], e["i2c"], e["servos"]["camara"]["angulo"], e["servos"]["rampa1"]["angulo"]),
                         ("PCA9685", True, 90.0, None))
        self.assertEqual(sorted(e["servos"]), ["camara", "direccion", "rampa1", "rampa2"])
        g.cerrar()
        self.assertTrue(pca.cerrado)


class TestRampas(unittest.TestCase):
    def setUp(self):
        self.g, self.pca, self.cal = con_pca()
        self.r = Rampas(self.g, self.cal)

    def test_cerrar_y_abrir_usan_los_angulos_calibrados(self):
        self.r.cerrar_todas()
        self.assertEqual((self.g.angulo("rampa1"), self.g.angulo("rampa2")), (90.0, 90.0))
        self.r.abrir(1)
        self.r.abrir(2)
        self.assertEqual((self.g.angulo("rampa1"), self.g.angulo("rampa2")), (130.0, 50.0))
        self.assertEqual((self.r.estado(1), self.r.estado(2)), ("ABIERTA", "ABIERTA"))
        with self.assertRaises(ValueError):
            self.r.abrir(3)

    def test_un_cambio_de_calibracion_reposiciona_la_rampa_en_vivo(self):
        self.r.abrir(1)
        self.cal.set("rampa1_abierto", 150.0)
        self.assertEqual(self.g.angulo("rampa1"), 150.0)
        self.assertIsNone(self.g.angulo("rampa2"))                   # la que nunca se movió, no se toca

    def test_en_manual_no_se_reposicionan_solas(self):
        self.r.cerrar(1)
        self.r.olvidar()
        self.g.mover("rampa1", 20)                                   # prueba de calibración
        self.cal.set("rampa2_abierto", 40.0)
        self.assertEqual(self.g.angulo("rampa1"), 20.0)


class TestPan(unittest.TestCase):
    def setUp(self):
        self.g, _, self.cal = con_pca()
        self.pan = PanCamara(self.g, self.cal)

    def test_barre_de_izquierda_a_derecha_dentro_del_rango_calibrado_y_rebota(self):
        self.pan.barrido()
        self.assertEqual(self.pan.angulo, 30.0)                      # empieza en camara_min
        t, anterior = 0.0, self.pan.angulo
        for _ in range(10):
            t += 0.1
            self.pan.tick(None, t)
        self.assertGreater(self.pan.angulo, anterior)
        self.assertEqual(self.pan.modo, "BARRIDO")
        for _ in range(200):
            t += 0.1
            self.pan.tick(None, t)
            self.assertTrue(30.0 <= self.pan.angulo <= 150.0)

    def test_la_velocidad_y_los_limites_salen_de_la_calibracion(self):
        self.cal.set_many({"camara_min": 60.0, "camara_max": 100.0, "camara_velocidad_dps": 10.0})
        self.pan.barrido()
        self.assertEqual(self.pan.angulo, 60.0)
        self.pan.tick(None, 0.0)
        self.pan.tick(None, 0.2)
        self.assertAlmostEqual(self.pan.angulo, 62.0, places=3)      # 10 °/s durante 0.2 s
        for i in range(300):
            self.pan.tick(None, 1.0 + i * 0.1)
            self.assertTrue(60.0 <= self.pan.angulo <= 100.0)

    def test_se_detiene_y_centra_el_qr(self):
        self.pan.barrido()
        self.pan.tick(None, 0.0)
        for i in range(1, 40):
            self.pan.tick(0.5 if self.pan.angulo < 100 else 0.0, i * 0.05)
        self.assertEqual(self.pan.modo, "SEGUIMIENTO")
        self.assertTrue(self.pan.alineado)
        quieto = self.pan.angulo
        self.pan.tick(0.0, 3.0)
        self.assertEqual(self.pan.angulo, quieto)

    def test_invertida_arranca_por_el_otro_extremo_y_gira_al_reves(self):
        self.cal.set("camara_invertida", True)
        self.pan.barrido()
        self.assertEqual(self.pan.angulo, 150.0)
        self.pan.tick(None, 0.0)
        self.pan.tick(None, 0.1)
        self.assertLess(self.pan.angulo, 150.0)

    def test_vuelve_a_barrer_si_pierde_el_qr(self):
        self.pan.barrido()
        self.pan.tick(0.5, 0.0)
        self.pan.tick(None, 0.5)
        self.assertEqual(self.pan.modo, "SEGUIMIENTO")
        self.pan.tick(None, 3.0)
        self.pan.tick(None, 3.1)
        self.assertEqual(self.pan.modo, "BARRIDO")

    def test_fijo_no_sigue_al_qr_y_centrar_usa_el_centro_calibrado(self):
        self.cal.set("camara_centro", 100.0)
        self.pan.centrar()
        self.pan.tick(0.9, 0.0)
        self.pan.tick(0.9, 0.5)
        self.assertEqual((self.pan.angulo, self.g.angulo("camara")), (100.0, 100.0))

    def test_fijar_desde_el_hmi_solo_se_acota_a_la_mecanica(self):
        self.pan.fijar(10)                                           # fuera del rango calibrado, dentro de lo físico (20..160)
        self.assertEqual(self.pan.angulo, 20.0)
        self.pan.fijar(120)
        self.assertEqual(self.pan.angulo, 120.0)


if __name__ == "__main__":
    unittest.main()
