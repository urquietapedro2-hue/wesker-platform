from datetime import datetime, timezone

from PyQt5 import QtCore, QtWidgets

from core import updater
from core.version import __version__
from ui.common import UpdateBanner, run_async

COLUMNAS = ["Nombre", "Rol", "Cliente", "Versión", "Visto"]


def hace(ts: str) -> str:
    try:
        seg = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        return "—"
    return "ahora" if seg < 20 else f"hace {int(seg)} s"


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, client, cfg, on_logout):
        super().__init__()
        self.client, self.on_logout = client, on_logout
        self._busy, self._bloqueada = False, False
        p = client.profile
        self.setWindowTitle(f"WESKER {__version__}")
        self.resize(760, 520)

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        lay = QtWidgets.QVBoxLayout(root)
        top = QtWidgets.QHBoxLayout()
        quien = QtWidgets.QLabel(f"{p.get('nombre') or p['email']}")
        quien.setStyleSheet("font-size:18px;font-weight:600")
        rol = QtWidgets.QLabel(f"Rol: {p['role']}")
        rol.setObjectName("muted")
        salir = QtWidgets.QPushButton("Cerrar sesión")
        salir.setObjectName("ghost")
        salir.clicked.connect(self._logout)
        top.addWidget(quien)
        top.addWidget(rol)
        top.addStretch(1)
        top.addWidget(salir)

        self.banner = UpdateBanner(cfg["github_repo"])
        self.tabla = QtWidgets.QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.tabla.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.estado = QtWidgets.QLabel("Conectando con la nube…")
        self.estado.setObjectName("muted")

        lay.addLayout(top)
        lay.addWidget(self.banner)
        lay.addWidget(QtWidgets.QLabel("Conectados ahora"))
        lay.addWidget(self.tabla, 1)
        lay.addWidget(self.estado)

        self.banner.comprobar()
        run_async(self, self.client.min_version, self._check_min, None)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(15000)
        self._tick()

    def _check_min(self, minima):
        if updater.is_newer(minima, __version__):
            self._bloqueada = True
            self.tabla.setEnabled(False)
            self.estado.setText(f"Esta versión ya no es compatible (mínima: {minima}). Actualiza para continuar.")
            self.estado.setStyleSheet("color:#ef4444")

    def _sync(self):
        self.client.heartbeat("desktop", __version__)
        return self.client.online_users()

    def _tick(self):
        if self._busy or self._bloqueada:
            return
        self._busy = True
        run_async(self, self._sync, self._pintar, self._sin_nube)

    def _pintar(self, filas):
        self._busy = False
        self.tabla.setRowCount(len(filas))
        for i, u in enumerate(filas):
            for j, v in enumerate((u["nombre"], u["role"], u["client"], u["version"], hace(u["last_seen"]))):
                self.tabla.setItem(i, j, QtWidgets.QTableWidgetItem(v or ""))
        if not self._bloqueada:
            self.estado.setText(f"Conectado a la nube. {len(filas)} sesión(es) activa(s).")
            self.estado.setStyleSheet("color:#4ade80")

    def _sin_nube(self, msg):
        self._busy = False
        self.estado.setText(f"{msg} Reintentando…")
        self.estado.setStyleSheet("color:#f59e0b")

    def _logout(self):
        self.client.sign_out()
        self.on_logout()
        self.close()

    def closeEvent(self, event):
        self.timer.stop()
        self.client.sign_out()
        super().closeEvent(event)
