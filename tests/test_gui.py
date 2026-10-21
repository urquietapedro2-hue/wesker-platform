"""Prueba de ventanas sin pantalla (Qt 'offscreen'). Se omite sola si PyQt5 no está instalado."""
import os
import sys
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["WESKER_SIN_AUDIO"] = "1"  # las pruebas nunca deben sonar
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


class CompartidoFalso:
    """Hace de nube: devuelve un estado de Zeno publicado por 'Pedro' y registra lo que se publica."""

    def __init__(self, hostil=False):
        self.publicados, self.liberados, self._entregado, self.hostil = [], [], False, hostil

    def leer(self):
        if self.hostil:
            basura = {"modo": {"x": 1}, "dir": ["F"], "pwm": "abc", "dist": float("nan"), "sens": "no", "sub": 5, "qr": None,
                      "silo": "abc", "ang_obj": "x", "tolva": None, "slots": [1, 2], "fase": "HACKEADO"}
            primero, self._entregado = not self._entregado, True
            return {n: {"version": 1, "publicador": "Intruso", "cambio": primero, "estado": basura if primero else None}
                    for n in ("ZENO-01", "ALBERT-01")}
        estado = {"modo": "AUTO", "dir": "L", "pwm": 45, "dist": 85.0, "sens": [1, 1, 0, 0, 0],
                  "sub": "SEGUIMIENTO", "qr": "NINGUNO", "seg": "curva izquierda", "corriendo": True}
        primero, self._entregado = not self._entregado, True
        return {"ZENO-01": {"version": 1, "publicador": "Pedro", "cambio": primero, "estado": estado if primero else None},
                "ALBERT-01": {"version": 0, "publicador": "", "cambio": False, "estado": None}}

    def publicar(self, nodo, estado, forzar=False):
        self.publicados.append((nodo, estado))
        return len(self.publicados)

    def liberar(self, nodo, timeout=None):
        self.liberados.append(nodo)


@unittest.skipUnless(HAY_QT, "PyQt5 no está instalado")
class TestVentanas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _abrir(self, role, hostil=False):
        from ui.main_window import MainWindow
        cliente, nube = ClienteFalso(role), CompartidoFalso(hostil)
        with patch("core.updater.check_latest", return_value=None):
            win = MainWindow(cliente, {"github_repo": "x/y"}, on_logout=lambda: None, shared=nube)
        win.show()
        win.nube = nube
        return win, cliente

    def _fuente(self, pagina, clave):
        pagina.fuente.setCurrentIndex(pagina.fuente.findData(clave))

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
        self._fuente(win.albert, "LOCAL")
        self._fuente(win.zeno, "LOCAL")
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

    def test_visor_ve_el_gemelo_publicado_por_otro(self):
        win, _ = self._abrir("VIEWER")
        self.assertEqual(win.zeno.fuente.count(), 1)  # un visor solo puede ver la planta
        self._bombear(1.8)                            # el sincronizador consulta cada segundo
        self.assertEqual((win.zeno.twin.direccion, win.zeno.twin.velocidad_pwm), ("L", 45))
        self.assertIn("Pedro", win.zeno.lbl_fuente.text())
        self.assertIn("Sin señal", win.albert.lbl_fuente.text())
        self._cerrar(win)

    def test_operador_publica_y_suelta_al_cerrar(self):
        win, cliente = self._abrir("OPERATOR")
        self._fuente(win.zeno, "PUBLICAR")
        self.assertTrue(win.zeno.publicando)
        win.zeno._alternar()
        self._bombear(1.2)
        for w in list(win._workers):
            w.wait(5000)
        self.qt.processEvents()
        self.assertTrue(win.nube.publicados)
        self.assertEqual(win.nube.publicados[0][0], "ZENO-01")
        self.assertIn("PUBLICAR_INICIAR", cliente.eventos)
        self._cerrar(win)
        self.assertIn("ZENO-01", win.nube.liberados)

    def test_hmi_muestra_nodos_en_linea_y_registra_eventos(self):
        win, _ = self._abrir("VIEWER")
        self.assertIn("Sesión iniciada", win.panel_eventos.toPlainText())
        self._bombear(1.8)
        self.assertEqual(win.barra.insignias["ZENO-01"].estado.text(), "EN LÍNEA")     # Pedro publica Zeno
        self.assertEqual(win.barra.insignias["ALBERT-01"].estado.text(), "SIN SEÑAL")
        self.assertEqual(win.barra.lbl_planta.text(), "PLANTA PARCIAL")
        self.assertIn("ZENO-01 en línea", win.panel_eventos.toPlainText())
        self.assertEqual(win.barra.lbl_nube.text(), "Nube: conectada")
        self._cerrar(win)

    def test_pantalla_completa_y_sonido(self):
        win, _ = self._abrir("OPERATOR")
        win._alternar_pantalla_completa()
        self.assertTrue(win.isFullScreen())
        win._alternar_pantalla_completa()
        self.assertFalse(win.isFullScreen())
        antes = win.barra.btn_sonido.text()
        win._alternar_sonido()
        self.assertNotEqual(win.barra.btn_sonido.text(), antes)
        win._alternar_sonido()
        self._cerrar(win)

    def test_mensajes_repetidos_no_inundan_el_registro(self):
        win, _ = self._abrir("VIEWER")
        for _ in range(5):
            win.evento("warn", "mensaje de prueba repetido")
        self.assertEqual(win.panel_eventos.toPlainText().count("mensaje de prueba repetido"), 1)
        self._cerrar(win)

    def test_estado_hostil_no_rompe_la_pantalla(self):
        win, _ = self._abrir("VIEWER", hostil=True)
        self._bombear(1.8)
        self.assertEqual(win.zeno.twin.velocidad_pwm, 0)       # telemetría segura por defecto
        self.assertEqual(win.zeno.twin.direccion, "S")
        self.assertIn("no válido", win.albert.lbl_fuente.text())
        self._cerrar(win)

    def test_login_se_abre_con_logo_y_fondo(self):
        from core.config import load_config
        from ui.login_window import LoginWindow
        ventana = LoginWindow(ClienteFalso("VIEWER"), {"github_repo": "x/y", "supabase_url": "https://ejemplo.invalid"},
                              on_success=lambda: None)
        ventana.show()
        self._bombear(0.3)
        self.assertTrue(ventana.isVisible())
        self.assertIsNotNone(ventana._fondo)  # el fondo propio se cargó desde assets/
        self.assertFalse(ventana.windowIcon().isNull())
        ventana.close()
        for w in list(getattr(ventana, "_workers", [])) + list(getattr(ventana.banner, "_workers", [])):
            w.wait(5000)

    def test_visor_solo_observa(self):
        win, _ = self._abrir("VIEWER")
        self.assertFalse(win.albert.btn_inicio.isEnabled())
        self.assertFalse(win.zeno.btn_inicio.isEnabled())
        self.assertIn("solo permite observar", win.albert.lbl_rol.text())
        self._cerrar(win)


if __name__ == "__main__":
    unittest.main()
