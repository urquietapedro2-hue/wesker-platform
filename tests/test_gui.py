"""Prueba de ventanas sin pantalla (Qt 'offscreen'). Se omite sola si PyQt5 no está instalado."""
import os
import sys
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "desktop"))

try:
    from PyQt5 import QtWidgets
    HAY_QT = True
except ImportError:
    HAY_QT = False


class ClienteFalso:
    def __init__(self, role):
        self.profile = {"id": "u1", "email": "t@t.t", "nombre": "Prueba", "role": role, "activo": True}
        self.eventos = []

    def min_version(self):
        return "0.0.0"

    def heartbeat(self, client, version):
        pass

    def online_users(self):
        return [{"nombre": "Prueba", "role": "ADMIN", "client": "desktop", "version": "x",
                 "last_seen": "2026-01-01T00:00:00+00:00"}]

    def log_event(self, accion, detalle=None, timeout=None):
        self.eventos.append(accion)

    def sign_out(self):
        pass


@unittest.skipUnless(HAY_QT, "PyQt5 no está instalado")
class TestVentanas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _abrir(self, role):
        from ui.main_window import MainWindow
        cliente = ClienteFalso(role)
        with patch("core.updater.check_latest", return_value=None):
            win = MainWindow(cliente, {"github_repo": "x/y"}, on_logout=lambda: None)
        win.show()
        return win, cliente

    def _bombear(self, segundos):
        fin = time.monotonic() + segundos
        while time.monotonic() < fin:
            self.qt.processEvents()
            time.sleep(0.01)

    def _cerrar(self, win):
        win.close()
        for pool in (win, win.banner):
            for w in list(getattr(pool, "_workers", [])):
                w.wait(5000)

    def test_operador_simula_albert_y_zeno(self):
        win, cliente = self._abrir("OPERATOR")
        self.assertEqual(win.stack.count(), 3)
        win.nav.setCurrentRow(1)
        win.albert._alternar()
        win.nav.setCurrentRow(2)
        win.zeno._alternar()
        self._bombear(0.5)
        win.zeno._tick()
        self.assertEqual(win.zeno.twin.velocidad_pwm, 60)  # el recorrido arranca en recta
        win.albert.twin.animar_rotacion()
        self.assertEqual(win.albert.twin.angulo_objetivo, 45.0)
        for w in list(win._workers):
            w.wait(5000)
        self.qt.processEvents()
        self.assertIn("SIM_ALBERT_INICIAR", cliente.eventos)
        self.assertIn("SIM_ZENO_INICIAR", cliente.eventos)
        self._cerrar(win)

    def test_visor_solo_observa(self):
        win, _ = self._abrir("VIEWER")
        self.assertFalse(win.albert.btn_inicio.isEnabled())
        self.assertFalse(win.zeno.btn_inicio.isEnabled())
        self.assertIn("solo permite observar", win.albert.lbl_rol.text())
        self._cerrar(win)


if __name__ == "__main__":
    unittest.main()
