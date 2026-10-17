from PyQt5 import QtCore, QtWidgets

from core.auth import AuthError
from core.config import is_configured
from core.version import __version__
from ui.common import UpdateBanner, run_async


class LoginWindow(QtWidgets.QWidget):
    def __init__(self, client, cfg, on_success):
        super().__init__()
        self.client, self.on_success = client, on_success
        self.setWindowTitle("WESKER")
        self.setFixedSize(420, 430)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(36, 28, 36, 20)
        lay.setSpacing(10)
        title = QtWidgets.QLabel("WESKER")
        title.setStyleSheet("font-size:30px;font-weight:700;letter-spacing:5px")
        title.setAlignment(QtCore.Qt.AlignCenter)
        sub = QtWidgets.QLabel("Planta virtual compartida")
        sub.setObjectName("muted")
        sub.setAlignment(QtCore.Qt.AlignCenter)
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

        for w in (title, sub, self.email, self.pwd, self.btn, self.status, self.banner):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(ver)

        self.btn.clicked.connect(self._entrar)
        self.email.returnPressed.connect(self.pwd.setFocus)
        self.pwd.returnPressed.connect(self._entrar)

        if is_configured(cfg):
            self.banner.comprobar()
        else:
            self._msg("Falta configurar app_config.json (supabase_url y supabase_anon_key).", "#f59e0b")
            self.btn.setEnabled(False)

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
