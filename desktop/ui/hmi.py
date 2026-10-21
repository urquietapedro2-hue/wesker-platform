"""Piezas visuales del HMI: barra de estado superior, registro de eventos, fondo y hoja de estilos."""
import html
import time

from PyQt5 import QtCore, QtWidgets

from ui import branding

NOMBRE_COMPLETO = "Wireless Environment for Synchronized Kernel Execution & Routing"
VERDE, AMBAR, ROJO, GRIS = "#4ade80", "#fbbf24", "#f87171", "#64748b"

HMI_STYLE = """
QPushButton{min-height:38px}
QListWidget{background-color:rgba(10,14,20,225);border:1px solid #26313f;border-radius:8px;padding:6px;outline:0;font-size:15px}
QListWidget::item{padding:16px 14px;border-radius:6px;margin-bottom:4px}
QListWidget::item:selected{background:#0c4a6e;color:#e0f2fe;border-left:4px solid #38bdf8}
QGroupBox{background-color:rgba(10,14,20,205);border:1px solid #26313f;border-radius:8px;margin-top:10px;padding:12px 8px 8px 8px;font-weight:600;color:#94a3b8}
QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px}
QComboBox,QSpinBox{background:#1a222c;border:1px solid #334155;border-radius:6px;padding:6px 8px;min-height:26px}
QStackedWidget{background:transparent}
QWidget#cuerpo{background:transparent}
QWidget#pagina{background:transparent}
QLabel{background:transparent}
QLabel#valor{font-weight:600;color:#e2e8f0}
QLabel#alerta{color:#fbbf24}
QFrame#barra{background-color:rgba(8,12,18,235);border:1px solid #26313f;border-radius:10px}
QPlainTextEdit#eventos{background-color:rgba(8,12,18,225);border:1px solid #26313f;border-radius:8px;font-family:Consolas,'Courier New',monospace;font-size:12px}
"""
# Pantalla completa (modo pie de máquina / táctil): letra y botones más grandes
HMI_GRANDE = "QWidget{font-size:15px} QPushButton{min-height:50px;font-size:15px} QListWidget{font-size:18px}"


class Led(QtWidgets.QLabel):
    def __init__(self, color=GRIS):
        super().__init__()
        self.setFixedSize(14, 14)
        self.poner(color)

    def poner(self, color):
        self.setStyleSheet(f"background-color:{color};border-radius:7px;border:1px solid rgba(255,255,255,45)")


class Insignia(QtWidgets.QFrame):
    """Estado de un nodo: «hay señal» significa que alguien lo está publicando (simulación hoy, hardware mañana)."""

    def __init__(self, nodo):
        super().__init__()
        self.setObjectName("insignia")
        self.setStyleSheet("QFrame#insignia{border:1px solid #26313f;border-radius:8px;background-color:rgba(255,255,255,10)}")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(8)
        self.led = Led()
        titulo = QtWidgets.QLabel(nodo)
        titulo.setStyleSheet("font-weight:600")
        self.estado = QtWidgets.QLabel("SIN SEÑAL")
        self.estado.setObjectName("muted")
        for w in (self.led, titulo, self.estado):
            lay.addWidget(w)
        self.poner(False)

    def poner(self, hay_senal, publicador=""):
        self.led.poner(VERDE if hay_senal else GRIS)
        self.estado.setText("EN LÍNEA" if hay_senal else "SIN SEÑAL")
        self.setToolTip(f"Publica: {publicador}" if hay_senal and publicador else "Nadie publica este nodo")


class BarraEstado(QtWidgets.QFrame):
    """Cabecera fija del HMI: marca, estado de la planta, nodos, nube, reloj, usuario y accesos rápidos."""

    def __init__(self, nombre, rol):
        super().__init__()
        self.setObjectName("barra")
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(14)
        pm = branding.pixmap("wesker_logo.png", 40)
        if pm is not None:
            logo = QtWidgets.QLabel()
            logo.setPixmap(pm)
            logo.setToolTip(NOMBRE_COMPLETO)
            lay.addWidget(logo)
        marca = QtWidgets.QVBoxLayout()
        marca.setSpacing(0)
        titulo = QtWidgets.QLabel("WESKER")
        titulo.setStyleSheet("font-size:20px;font-weight:700;letter-spacing:4px")
        subtitulo = QtWidgets.QLabel("HMI - Planta virtual")
        subtitulo.setObjectName("muted")
        marca.addWidget(titulo)
        marca.addWidget(subtitulo)
        lay.addLayout(marca)

        self.lbl_planta = QtWidgets.QLabel("SIN SEÑAL DE NODOS")
        self.lbl_planta.setStyleSheet(f"font-size:14px;font-weight:700;letter-spacing:1px;color:{GRIS}")
        lay.addWidget(self.lbl_planta)
        lay.addStretch(1)
        self.insignias = {"ALBERT-01": Insignia("ALBERT-01"), "ZENO-01": Insignia("ZENO-01")}
        for i in self.insignias.values():
            lay.addWidget(i)
        self.led_nube = Led()
        self.lbl_nube = QtWidgets.QLabel("Nube")
        self.lbl_nube.setObjectName("muted")
        for w in (self.led_nube, self.lbl_nube):
            lay.addWidget(w)
        self.reloj = QtWidgets.QLabel()
        self.reloj.setAlignment(QtCore.Qt.AlignCenter)
        self.reloj.setStyleSheet("font-family:Consolas,'Courier New',monospace;font-size:17px;font-weight:600")
        lay.addWidget(self.reloj)
        usuario = QtWidgets.QLabel(f"{nombre}\nRol: {rol}")
        usuario.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        lay.addWidget(usuario)
        self.btn_sonido = QtWidgets.QPushButton("Sonido: sí")
        self.btn_pantalla = QtWidgets.QPushButton("Pantalla completa (F11)")
        self.btn_salir = QtWidgets.QPushButton("Cerrar sesión")
        for b in (self.btn_sonido, self.btn_pantalla, self.btn_salir):
            b.setObjectName("ghost")
            lay.addWidget(b)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tic)
        self._timer.start(1000)
        self._tic()

    def _tic(self):
        self.reloj.setText(time.strftime("%H:%M:%S\n%d/%m/%Y"))

    def poner_nodo(self, nodo, hay_senal, publicador=""):
        if nodo in self.insignias:
            self.insignias[nodo].poner(hay_senal, publicador)
            self._actualizar_planta()

    def _actualizar_planta(self):
        activos = sum(1 for i in self.insignias.values() if i.estado.text() == "EN LÍNEA")
        texto, color = (("PLANTA EN LÍNEA", VERDE) if activos == len(self.insignias)
                        else ("PLANTA PARCIAL", AMBAR) if activos else ("SIN SEÑAL DE NODOS", GRIS))
        self.lbl_planta.setText(texto)
        self.lbl_planta.setStyleSheet(f"font-size:14px;font-weight:700;letter-spacing:1px;color:{color}")

    def poner_nube(self, ok):
        self.led_nube.poner(VERDE if ok else ROJO)
        self.lbl_nube.setText("Nube: conectada" if ok else "Nube: sin conexión")

    def poner_sonido(self, activo):
        self.btn_sonido.setText("Sonido: sí" if activo else "Sonido: no")


class PanelEventos(QtWidgets.QPlainTextEdit):
    """Registro de eventos de esta sesión (local). El historial compartido y permanente llega con la pantalla Planta."""
    COLORES = {"info": "#94a3b8", "ok": VERDE, "warn": AMBAR, "error": ROJO}

    def __init__(self):
        super().__init__()
        self.setObjectName("eventos")
        self.setReadOnly(True)
        self.setMaximumBlockCount(300)
        self.setFixedHeight(112)

    def registrar(self, nivel, texto):
        color = self.COLORES.get(nivel, self.COLORES["info"])
        self.appendHtml(f'<span style="color:#64748b">{time.strftime("%H:%M:%S")}</span> '
                        f'<span style="color:{color}">[{html.escape(nivel.upper())}]</span> {html.escape(texto)}')


class FondoCentral(QtWidgets.QWidget):
    """Raíz de la ventana: pinta el fondo propio (si falta el archivo, queda el color liso)."""

    def __init__(self, recurso="fondos/background_dashboard.jpg"):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._recurso, self._cache, self._tam = recurso, None, None

    def paintEvent(self, _evento):
        if self._tam != self.size():
            self._cache, self._tam = branding.fondo_cubriendo(self._recurso, self.size()), self.size()
        if self._cache is not None:
            from PyQt5 import QtGui
            pintor = QtGui.QPainter(self)
            pintor.drawPixmap(0, 0, self._cache)
            pintor.end()
