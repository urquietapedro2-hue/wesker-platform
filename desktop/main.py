import faulthandler
import os
import sys
import time
import traceback

from PyQt5 import QtCore, QtWidgets

from core.auth import SupabaseClient
from core.config import load_config
from core.paths import user_data_dir
from core.version import __version__
from ui.common import STYLE
from ui.login_window import LoginWindow
from ui.main_window import MainWindow

_LOG = None  # %APPDATA%/WESKER/crash.log


def _abrir_log():
    """El .exe no tiene consola: sin esto, cualquier fallo desaparece sin dejar rastro."""
    global _LOG
    try:
        _LOG = open(user_data_dir() / "crash.log", "a", buffering=1, encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = _LOG
        if sys.stdout is None:
            sys.stdout = _LOG
        faulthandler.enable(_LOG)  # también registra caídas nativas (Qt, DLL)
    except OSError:
        pass


def trazar(texto):
    if _LOG:
        _LOG.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} v{__version__} {texto}\n")


def registrar_error(tipo, valor, tb):
    trazar("ERROR NO CONTROLADO\n" + "".join(traceback.format_exception(tipo, valor, tb)))
    if QtWidgets.QApplication.instance():
        QtWidgets.QMessageBox.critical(
            None, "WESKER", f"Error inesperado:\n{valor}\n\nDetalle en %APPDATA%\\WESKER\\crash.log")


class App:
    def __init__(self):
        self.cfg = load_config()
        self.client = SupabaseClient(self.cfg["supabase_url"], self.cfg["supabase_anon_key"])
        self.login = self.main = None

    def show_login(self):
        self.login = LoginWindow(self.client, self.cfg, on_success=self.show_main)
        self.login.show()

    def show_main(self):
        self.main = MainWindow(self.client, self.cfg, on_logout=self.show_login)
        self.main.show()
        self.login.close()

    def esperar_hilos(self):
        """Cerrar con una petición de red en curso aborta Qt; se espera a que terminen."""
        for ventana in (self.login, self.main):
            for obj in (ventana, getattr(ventana, "banner", None)):
                for w in list(getattr(obj, "_workers", None) or []):
                    w.wait(2000)


def _fin_prueba(qt, app):
    """Prueba de humo (solo en la compilación automática): ¿la ventana sigue viva?"""
    try:
        ok = bool(app.login.isVisible())
    except Exception:  # ventana destruida
        ok = False
    trazar(f"prueba de humo: ventana visible={ok}")
    qt.exit(0 if ok else 3)


def main():
    _abrir_log()
    sys.excepthook = registrar_error
    trazar("inicio")
    qt = QtWidgets.QApplication(sys.argv)
    qt.setStyleSheet(STYLE)
    app = App()  # variable viva: si se pierde la referencia, la ventana desaparece sola
    qt.aboutToQuit.connect(app.esperar_hilos)
    app.show_login()
    trazar("login mostrado")
    if os.environ.get("WESKER_SMOKETEST"):
        QtCore.QTimer.singleShot(3000, lambda: _fin_prueba(qt, app))
    code = qt.exec_()
    trazar(f"cierre normal (codigo {code})")
    sys.exit(code)


if __name__ == "__main__":
    main()