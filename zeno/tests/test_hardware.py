import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.dirname(__file__))

from falsos import FakeGPIO, esperar, hardware_prueba  # noqa: E402
from zeno import config  # noqa: E402


class TestHardware(unittest.TestCase):
    def setUp(self):
        self.gpio = FakeGPIO()
        self.hw = hardware_prueba(self.gpio)
        self.fwd, self.rev, self.servo = (self.gpio.pwms[config.PIN_RPWM], self.gpio.pwms[config.PIN_LPWM],
                                          self.gpio.pwms[config.PIN_SERVO])

    def duty(self, angulo):
        return 2.5 + max(45.0, min(135.0, angulo + self.hw.cal['direccion_trim'])) / 18.0

    def test_arranque_centra_la_direccion_con_el_trim_y_suelta_el_servo(self):
        self.assertEqual((self.fwd.duty, self.rev.duty), (0, 0))
        self.assertAlmostEqual(self.servo.historial[1], self.duty(90.0))   # 90° con trim -8.6
        self.assertEqual(self.servo.duty, 0)                               # el servo queda sin señal, como en V2
        self.assertEqual((self.fwd.freq, self.servo.freq), (1000, 50))

    def test_cada_comando_mueve_lo_mismo_que_en_v2(self):
        self.hw.traccion("F", 45)
        self.assertEqual((self.fwd.duty, self.rev.duty, self.hw.estado_movimiento, self.hw.velocidad_actual), (45, 0, "F", 45))
        self.hw.traccion("L", 42)
        self.assertEqual((self.fwd.duty, self.hw.estado_movimiento), (42, "L"))
        self.assertAlmostEqual(self.servo.historial[-2], self.duty(125))
        self.hw.traccion("R", 40)
        self.assertAlmostEqual(self.servo.historial[-2], self.duty(70))
        self.hw.traccion("B", 30)
        self.assertEqual((self.fwd.duty, self.rev.duty, self.hw.estado_movimiento), (0, 30, "B"))
        self.hw.traccion("S", 0)
        self.assertEqual((self.fwd.duty, self.rev.duty, self.hw.estado_movimiento, self.hw.velocidad_actual), (0, 0, "S", 0))
        self.assertAlmostEqual(self.servo.historial[-2], self.duty(90))

    def test_repetir_el_mismo_comando_no_vuelve_a_mover_la_direccion(self):
        self.hw.traccion("L", 42)
        n = len(self.servo.historial)
        self.hw.traccion("L", 40)
        self.assertEqual(len(self.servo.historial), n)
        self.assertEqual(self.fwd.duty, 40)

    def test_detener_estando_detenido_no_hace_nada(self):
        n = len(self.servo.historial)
        self.hw.traccion("S", 0)
        self.assertEqual(len(self.servo.historial), n)

    def test_velocidad_acotada_y_comando_desconocido_ignorado(self):
        self.hw.traccion("F", 500)
        self.assertEqual(self.fwd.duty, 100)
        self.hw.traccion("F", -9)
        self.assertEqual(self.fwd.duty, 0)
        self.hw.traccion("X", 50)
        self.assertEqual(self.hw.estado_movimiento, "F")

    def test_parar_duro_corta_aunque_el_estado_diga_detenido(self):
        self.fwd.duty = 70                      # el estado guardado miente
        self.hw.estado_movimiento = "S"
        self.hw.parar_duro()
        self.assertEqual((self.fwd.duty, self.rev.duty), (0, 0))

    def test_sensores_con_logica_invertida(self):
        self.gpio.entradas = {5: 0, 6: 1, 19: 0, 20: 1, 26: 1}
        self.assertEqual(self.hw.leer_sensores(), [1, 0, 1, 0, 0])
        self.assertEqual(self.hw.sensores, [1, 0, 1, 0, 0])
        with patch.object(config, "INVERTIR_LOGICA", False):
            self.assertEqual(self.hw.leer_sensores(), [0, 1, 0, 1, 1])

    def test_pulso_de_diagnostico_gira_y_regresa_o_avanza_y_frena(self):
        self.hw.pulso("L", 40, 50)
        self.assertTrue(esperar(lambda: self.servo.historial.count(self.duty(125)) == 1 and self.servo.historial.count(self.duty(90)) >= 2))
        self.hw.pulso("F", 40, 50)
        self.assertTrue(esperar(lambda: self.fwd.duty == 40))
        self.assertTrue(esperar(lambda: self.fwd.duty == 0 and self.hw.estado_movimiento == "S"))

    def test_cerrar_apaga_todo(self):
        self.hw.traccion("F", 50)
        self.hw.cerrar()
        self.assertEqual((self.fwd.duty, self.rev.duty), (0, 0))
        self.assertTrue(all(p.detenido for p in self.gpio.pwms.values()) and self.gpio.limpio)


if __name__ == "__main__":
    unittest.main()
