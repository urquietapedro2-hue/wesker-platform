from PyQt5 import QtCore, QtGui, QtWidgets

from core.auth import AuthError  # noqa: F401  (los mensajes de error llegan por la señal del Worker)
from core.config import is_configured
from core.version import __version__
from ui import branding
from ui.common import UpdateBanner, run_async

NOMBRE_COMPLETO = "Wireless Environment for Synchronized Kernel Execution & Routing"
TARJETA = ("QFrame#tarjeta{background-color:rgba(10,14,20,218);border:1px solid #26313f;border-radius:12px}"
           "QFrame#tarjeta QLabel{background:transparent}")


class LoginWindow(QtWidgets.QWidget):
    def __init__(self, client, cfg, on_success):
        super().__init__()
        self.client, self.on_success = client, on_success
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setWindowTitle("WESKER")
        self.setWindowIcon(branding.icono())
        self.setFixedSize(520, 620)
        self._fondo = branding.fondo_cubriendo("fondos/background.jpg", self.size())

        raiz = QtWidgets.QVBoxLayout(self)
        raiz.setContentsMargins(44, 30, 44, 30)
        tarjeta = QtWidgets.QFrame()
        tarjeta.setObjectName("tarjeta")
        tarjeta.setStyleSheet(TARJETA)
        lay = QtWidgets.QVBoxLayout(tarjeta)
        lay.setContentsMargins(32, 26, 32, 18)
        lay.setSpacing(10)

        logo = QtWidgets.QLabel()
        logo.setAlignment(QtCore.Qt.AlignCenter)
        pm = branding.pixmap("wesker_logo.png", 120)
        if pm is not None:
            logo.setPixmap(pm)
        logo.setToolTip(NOMBRE_COMPLETO)
        title = QtWidgets.QLabel("WESKER")
        title.setStyleSheet("font-size:30px;font-weight:700;letter-spacing:5px")
        title.setAlignment(QtCore.Qt.AlignCenter)
        sub = QtWidgets.QLabel("Planta virtual compartida")
        sub.setObjectName("muted")
        sub.setAlignment(QtCore.Qt.AlignCenter)
        sub.setToolTip(NOMBRE_COMPLETO)
        self.email = QtWidgets.QLineEdit(placeholderText="Correo")
        self.pwd = QtWidgets.QLineEdit(placeholderText="Contraseña")
        self.pwd.setEchoMode(QtWidgets.QLineEdit.Password)
        self.btn = QtWidgets.QPushButton("Entrar")
        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        self.status.setAlignment(QtCore.Qt.AlignCenter)
        self.banner = UpdateBanner(cfg["github_repo"])
        ver = QtWidgets.QLabel(f"Versión {__version__}")
        ver.setObjectName("muted")
        ver.setAlignment(QtCore.Qt.AlignCenter)

        for w in (logo, title, sub, self.email, self.pwd, self.btn, self.status, self.banner):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(ver)
        raiz.addStretch(1)
        raiz.addWidget(tarjeta)
        raiz.addStretch(1)

        self.btn.clicked.connect(self._entrar)
        self.email.returnPressed.connect(self.pwd.setFocus)
        self.pwd.returnPressed.connect(self._entrar)

        if is_configured(cfg):
            self.banner.comprobar()
        else:
            self._msg("Falta configurar app_config.json (supabase_url y supabase_anon_key).", "#f59e0b")
            self.btn.setEnabled(False)

    def paintEvent(self, _event):
        """Dibuja el fondo propio; si no está el archivo queda el color liso de la hoja de estilos."""
        if self._fondo is not None:
            pintor = QtGui.QPainter(self)
            pintor.drawPixmap(0, 0, self._fondo)
            pintor.end()

    def _msg(self, text, color="#94a3b8"):
        self.status.setText(text)
        self.status.setStyleSheet(f"color:{color}")

    def _entrar(self):
        email, pwd = self.email.text().strip(), self.pwd.text()
        if not email or not pwd:
            return self._msg("Escribe tu correo y tu contraseña.", "#f59e0b")
        self.btn.setEnabled(False)
        self._msg("Conectando…")
        run_async(self, self.client.sign_in, self._ok, self._fail, email, pwd)

    def _ok(self, _profile):
        self.on_success()

    def _fail(self, msg):
        self.pwd.clear()
        self.btn.setEnabled(True)
        self._msg(msg, "#ef4444")
