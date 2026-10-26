import time

from PyQt5 import QtCore, QtGui, QtWidgets

from core import updater
from core.nodos import RegistroNodos
from core.permissions import puede_controlar
from core.secretos_local import Almacen as AlmacenHMI
from core.shared import EstadoCompartido
from core.version import __version__
from core.vera_cliente import ClienteVera
from ui import audio, branding
from ui.acceso_real import AccesoReal
from ui.albert_page import AlbertPage
from ui.common import UpdateBanner, run_async
from ui.nodos_page import NodosPage
from ui.hmi import HMI_GRANDE, HMI_STYLE, BarraEstado, FondoCentral, PanelEventos
from ui.shared_sync import Sincronizador
from ui.users_page import UsersPage
from ui.zeno_page import ZenoPage

REPETIDO_S = 5.0  # el mismo mensaje no se repite en el registro antes de este tiempo


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, client, cfg, on_logout, shared=None, registro=None, almacen=None):
        super().__init__()
        self.client, self.on_logout = client, on_logout
        self.shared = shared or EstadoCompartido(client)
        self.registro, self.almacen, self.endpoints = registro or RegistroNodos(client), almacen or AlmacenHMI(), []
        self._busy, self._bloqueada = False, False
        self._senal, self._nube_ok, self._vistos = {}, None, {}
        p = client.profile
        self._usuario = p.get("nombre") or p["email"]
        self.vera = ClienteVera()
        self.setWindowTitle(f"WESKER {__version__}")
        self.setWindowIcon(branding.icono())
        self.resize(1280, 820)
        self.setStyleSheet(HMI_STYLE)

        raiz = FondoCentral()
        self.setCentralWidget(raiz)
        lay = QtWidgets.QVBoxLayout(raiz)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(10)

        self.barra = BarraEstado(self._usuario, p["role"])
        self.barra.btn_salir.clicked.connect(self._logout)
        self.barra.btn_pantalla.clicked.connect(self._alternar_pantalla_completa)
        self.barra.btn_sonido.clicked.connect(self._alternar_sonido)
        self.barra.poner_sonido(audio.gestor().activo())
        self.panel_eventos = PanelEventos()
        self.banner = UpdateBanner(cfg["github_repo"])
        self.users = UsersPage()
        self.sync = Sincronizador(self.shared, self)
        self.albert = AlbertPage(p["role"], self.auditar, self.sync, self.evento)
        control = puede_controlar(p["role"])
        self.zeno = ZenoPage(p["role"], self.auditar, self.sync, self.evento,
                             AccesoReal(lambda: self.endpoints, self.almacen) if control else None)
        paginas, nombres = [self.users, self.albert, self.zeno], ["Conectados", "Albert (dosificadora)", "Zeno (AGV)"]
        self.nodos = None
        if control:  # un Visor no ve direcciones de red de los nodos
            self.nodos = NodosPage(p["role"], self.registro, self.almacen, self._ejecutar, self.evento, self._set_endpoints)
            paginas.append(self.nodos)
            nombres.append("Nodos y red")
        self.stack = QtWidgets.QStackedWidget()
        for page in paginas:
            self.stack.addWidget(page)
        self.nav = QtWidgets.QListWidget()
        self.nav.setFixedWidth(200)
        self.nav.addItems(nombres)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.body = QtWidgets.QWidget()
        self.body.setObjectName("cuerpo")
        bl = QtWidgets.QHBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(10)
        bl.addWidget(self.nav)
        bl.addWidget(self.stack, 1)
        self.estado = QtWidgets.QLabel("Conectando con la nube…")
        self.estado.setObjectName("muted")

        for w in (self.barra, self.banner):
            lay.addWidget(w)
        lay.addWidget(self.body, 1)
        lay.addWidget(self.panel_eventos)
        lay.addWidget(self.estado)

        QtWidgets.QShortcut(QtGui.QKeySequence("F11"), self, activated=self._alternar_pantalla_completa)
        QtWidgets.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self._salir_pantalla_completa)
        self.sync.senal.connect(self._on_senal)
        self.sync.error.connect(self._on_error_sync)

        self.evento("info", f"Sesión iniciada: {self._usuario} ({p['role']})", "sesion_iniciada")
        self.banner.comprobar()
        run_async(self, self.client.min_version, self._check_min, None)
        if self.nodos is not None:
            run_async(self, self.registro.listar, self._set_endpoints, self._endpoints_fallo)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(15000)
        self._tick()

    # ---------- punto único de eventos: registro visible, sonido y V.E.R.A. ----------
    def evento(self, nivel, texto, codigo=None, nodo=""):
        """nivel: info | ok | warn | error. Los errores suenan; si hay `codigo`, V.E.R.A. lo anuncia (si está corriendo)."""
        ahora = time.monotonic()
        if ahora - self._vistos.get(texto, -1e9) < REPETIDO_S:
            return
        self._vistos[texto] = ahora
        self.panel_eventos.registrar(nivel, texto)
        if nivel == "error":
            audio.reproducir("error_sistema")
        if codigo:
            self.vera.enviar(codigo, "info" if nivel == "ok" else nivel, nodo, self._usuario)

    def _ejecutar(self, fn, ok, fallo=None, *args):
        """Trabajo de red en segundo plano para las páginas (los hilos cuelgan de esta ventana, que main.py espera al cerrar)."""
        run_async(self, fn, ok, fallo, *args)

    def _set_endpoints(self, lista):
        self.endpoints = list(lista)
        if self.nodos is not None:
            self.nodos.mostrar(self.endpoints)

    def _endpoints_fallo(self, msg):
        if self.nodos is not None:
            self.nodos.estado.setText(f"El registro de direcciones no está disponible: {msg}")

    def auditar(self, accion, detalle=None):
        """Evento de auditoría en la nube, en segundo plano: nunca bloquea la ventana."""
        run_async(self, self.client.log_event, lambda _r: None, None, accion, detalle or {})

    # ---------- señal de los nodos y estado de la nube (consulta de 1 s del sincronizador) ----------
    def _on_senal(self, nodo, publicador):
        self._poner_nube(True)
        hay = bool(publicador)
        self.barra.poner_nodo(nodo, hay, publicador)
        previo, self._senal[nodo] = self._senal.get(nodo), hay
        if previo is None and not hay:
            return  # primera lectura sin señal: no es noticia
        if previo != hay:
            if hay:
                self.evento("ok", f"{nodo} en línea (publica {publicador})", "nodo_en_linea", nodo)
            else:
                self.evento("warn", f"{nodo} sin señal", "nodo_sin_senal", nodo)

    def _on_error_sync(self, msg):
        self._poner_nube(False, msg)

    def _poner_nube(self, ok, detalle=""):
        previo, self._nube_ok = self._nube_ok, ok
        if ok == previo:
            return
        self.barra.poner_nube(ok)
        if ok and previo is False:
            self.evento("ok", "Conexión con la nube restablecida", "nube_restablecida")
        elif not ok:
            self.evento("error", f"Nube no disponible: {detalle}" if detalle else "Nube no disponible", "nube_perdida")

    # ---------- pantalla completa / sonido ----------
    def _alternar_pantalla_completa(self):
        if self.isFullScreen():
            self._salir_pantalla_completa()
        else:
            self.setStyleSheet(HMI_STYLE + HMI_GRANDE)
            self.showFullScreen()

    def _salir_pantalla_completa(self):
        if self.isFullScreen():
            self.showNormal()
            self.setStyleSheet(HMI_STYLE)

    def _alternar_sonido(self):
        g = audio.gestor()
        g.set_activo(not g.activo())
        self.barra.poner_sonido(g.activo())

    # ---------- versión mínima, pulso de conexión y lista de conectados ----------
    def _check_min(self, minima):
        if updater.is_newer(minima, __version__):
            self._bloqueada = True
            self.sync.detener()
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

    # ---------- cierre ----------
    def _soltar_nodos(self):
        """Libera los nodos que esta PC publica para que otra persona pueda tomarlos enseguida."""
        if not getattr(self.client, "token", True):
            return  # ya no hay sesión: el servidor lo suelta solo a los 10 s
        for page in (self.albert, self.zeno):
            if page.publicando:
                try:
                    self.shared.liberar(page.NODO, timeout=2)
                except Exception:
                    pass

    def _logout(self):
        self.sync.detener()
        self.zeno.cerrar()
        self._soltar_nodos()
        self.client.sign_out()
        self.on_logout()
        self.close()

    def closeEvent(self, event):
        self.timer.stop()
        self.sync.detener()
        self.zeno.cerrar()
        self._soltar_nodos()
        self.client.sign_out()
        super().closeEvent(event)
