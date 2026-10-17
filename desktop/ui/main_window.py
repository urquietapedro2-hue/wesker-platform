from PyQt5 import QtCore, QtWidgets

from core import updater
from core.version import __version__
from ui.albert_page import AlbertPage
from ui.common import UpdateBanner, run_async
from ui.users_page import UsersPage
from ui.zeno_page import ZenoPage

EXTRA_STYLE = """
QListWidget{background:#131a22;border:1px solid #1e293b;border-radius:6px;padding:4px;outline:0}
QListWidget::item{padding:10px 12px;border-radius:4px}
QListWidget::item:selected{background:#0c4a6e;color:#e0f2fe}
QGroupBox{border:1px solid #26313f;border-radius:6px;margin-top:10px;padding:12px 8px 8px 8px;font-weight:600;color:#94a3b8}
QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px}
QComboBox,QSpinBox{background:#1a222c;border:1px solid #334155;border-radius:6px;padding:6px 8px}
QLabel#valor{font-weight:600;color:#e2e8f0}
QLabel#alerta{color:#fbbf24}
"""


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, client, cfg, on_logout):
        super().__init__()
        self.client, self.on_logout = client, on_logout
        self._busy, self._bloqueada = False, False
        p = client.profile
        self.setWindowTitle(f"WESKER {__version__}")
        self.resize(1180, 760)
        self.setStyleSheet(EXTRA_STYLE)

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
        self.users = UsersPage()
        self.albert = AlbertPage(p["role"], self.auditar)
        self.zeno = ZenoPage(p["role"], self.auditar)
        self.stack = QtWidgets.QStackedWidget()
        for page in (self.users, self.albert, self.zeno):
            self.stack.addWidget(page)
        self.nav = QtWidgets.QListWidget()
        self.nav.setFixedWidth(170)
        self.nav.addItems(["Conectados", "Albert (dosificadora)", "Zeno (AGV)"])
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.body = QtWidgets.QWidget()
        bl = QtWidgets.QHBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.nav)
        bl.addWidget(self.stack, 1)

        self.estado = QtWidgets.QLabel("Conectando con la nube…")
        self.estado.setObjectName("muted")

        lay.addLayout(top)
        lay.addWidget(self.banner)
        lay.addWidget(self.body, 1)
        lay.addWidget(self.estado)

        self.banner.comprobar()
        run_async(self, self.client.min_version, self._check_min, None)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(15000)
        self._tick()

    def auditar(self, accion, detalle=None):
        """Evento de auditoría en segundo plano: nunca bloquea la ventana."""
        run_async(self, self.client.log_event, lambda _r: None, None, accion, detalle or {})

    def _check_min(self, minima):
        if updater.is_newer(minima, __version__):
            self._bloqueada = True
            self.body.setEnabled(False)
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
        self.users.pintar(filas)
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
