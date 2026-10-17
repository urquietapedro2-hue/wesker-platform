"""Estilo compartido, hilo de trabajo (la GUI nunca espera a la red) y aviso de actualización."""
from PyQt5 import QtCore, QtWidgets

from core import updater
from core.version import __version__

STYLE = """
QWidget{background:#0f1419;color:#e2e8f0;font-family:'Segoe UI',Arial;font-size:13px}
QLineEdit{background:#1a222c;border:1px solid #334155;border-radius:6px;padding:9px 12px}
QLineEdit:focus{border-color:#38bdf8}
QPushButton{background:#0284c7;border:1px solid #38bdf8;border-radius:6px;padding:9px 16px;font-weight:600;color:#fff}
QPushButton:hover{background:#0369a1}
QPushButton:disabled{background:#1e293b;border-color:#334155;color:#64748b}
QPushButton#ghost{background:transparent;border-color:#334155;color:#cbd5e1}
QTableWidget{background:#131a22;gridline-color:#1e293b;border:1px solid #1e293b}
QHeaderView::section{background:#1a222c;border:0;padding:6px;color:#94a3b8}
QFrame#banner{background:#422006;border:1px solid #b45309;border-radius:6px}
QLabel#muted{color:#94a3b8}
"""


class Worker(QtCore.QThread):
    """Ejecuta fn(*args) fuera del hilo de la interfaz."""
    ok = QtCore.pyqtSignal(object)
    fail = QtCore.pyqtSignal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.ok.emit(self.fn(*self.args))
        except Exception as ex:  # el mensaje llega a la UI; nada se pierde en silencio
            self.fail.emit(str(ex))


def run_async(owner, fn, on_ok, on_fail=None, *args):
    """Lanza un Worker y lo mantiene vivo hasta que termina."""
    pool = owner.__dict__.setdefault("_workers", [])
    w = Worker(fn, *args, parent=owner)
    w.ok.connect(on_ok)
    w.fail.connect(on_fail or (lambda _m: None))
    w.finished.connect(lambda: pool.remove(w))
    pool.append(w)
    w.start()


class UpdateBanner(QtWidgets.QFrame):
    """Aviso de versión nueva; descarga, verifica e instala al pulsar el botón."""

    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo, self.info = repo, None
        self.setObjectName("banner")
        self.hide()
        lay = QtWidgets.QHBoxLayout(self)
        self.lbl = QtWidgets.QLabel()
        self.btn = QtWidgets.QPushButton("Actualizar ahora")
        lay.addWidget(self.lbl, 1)
        lay.addWidget(self.btn)
        self.btn.clicked.connect(self._descargar)

    def comprobar(self):
        run_async(self, updater.check_latest, self._on_check, None, self.repo)

    def _on_check(self, info):
        if info and updater.is_newer(info["version"], __version__):
            self.info = info
            self.lbl.setText(f"Hay una versión nueva: {info['version']} (tienes {__version__}).")
            self.show()

    def _descargar(self):
        if not self.info:
            return
        self.btn.setEnabled(False)
        self.lbl.setText("Descargando la actualización…")
        run_async(self, updater.download_and_verify, self._instalar, self._error, self.info)

    def _instalar(self, path):
        updater.launch_installer(path)
        QtWidgets.QApplication.quit()

    def _error(self, msg):
        self.lbl.setText(f"No se pudo actualizar: {msg}")
        self.btn.setEnabled(True)
