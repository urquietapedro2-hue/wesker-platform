import time

from PyQt5 import QtCore, QtWidgets

from core.permissions import nota_rol, puede_controlar
from core.sim import ZenoSimulator
from ui.panel import grupo_valores, marcas, scroll
from ui.twins.zeno_twin import ZenoDigitalTwin

DIRECCIONES = {"F": "Adelante", "B": "Atrás", "L": "Izquierda", "R": "Derecha", "S": "Detenido",
               "FL": "Adelante-izquierda", "FR": "Adelante-derecha", "BL": "Atrás-izquierda",
               "BR": "Atrás-derecha", "ESTACION": "En estación"}
SENSORES_CENTRO = [0, 0, 1, 0, 0]


class ZenoPage(QtWidgets.QWidget):
    """Gemelo de Zeno (AGV) con su panel de telemetría y simulación."""

    def __init__(self, role, auditar):
        super().__init__()
        self.role, self.auditar = role, auditar
        self.sim = ZenoSimulator()
        self.corriendo = False
        self._ultimo = time.monotonic()

        self.twin = ZenoDigitalTwin(self)

        estado, self.v = grupo_valores("Telemetría en vivo", [
            ("modo", "Modo"), ("dir", "Dirección"), ("pwm", "Potencia"), ("dist", "Distancia frontal"),
            ("sub", "Subestado"), ("qr", "Estación (QR)"), ("seg", "Tramo simulado"),
            ("sens", "Línea S1 a S5")])

        self.btn_inicio = QtWidgets.QPushButton("Iniciar recorrido")
        self.modo = QtWidgets.QComboBox()
        self.modo.addItem("Automático", "AUTO")
        self.modo.addItem("Manual", "MANUAL")
        self.vel = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.vel.setRange(50, 200)
        self.vel.setValue(100)
        self.lbl_vel = QtWidgets.QLabel("Velocidad de simulación 100 %")
        self.vel.valueChanged.connect(lambda x: self.lbl_vel.setText(f"Velocidad de simulación {x} %"))
        self.btn_obstaculo = QtWidgets.QPushButton("Provocar obstáculo")
        self.btn_reinicio = QtWidgets.QPushButton("Reiniciar recorrido")

        simulacion = QtWidgets.QGroupBox("Simulación")
        form = QtWidgets.QFormLayout(simulacion)
        form.addRow(self.btn_inicio)
        form.addRow("Modo", self.modo)
        form.addRow(self.lbl_vel)
        form.addRow(self.vel)
        form.addRow(self.btn_obstaculo)
        form.addRow(self.btn_reinicio)

        self.manual = QtWidgets.QGroupBox("Control manual")
        g = QtWidgets.QGridLayout(self.manual)
        for clave, texto, fila, col in (("F", "Adelante", 0, 1), ("L", "Izquierda", 1, 0), ("S", "Alto", 1, 1),
                                        ("R", "Derecha", 1, 2), ("B", "Atrás", 2, 1)):
            b = QtWidgets.QPushButton(texto)
            b.clicked.connect(lambda _c, d=clave: self._manual(d))
            g.addWidget(b, fila, col)
        self.pwm = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pwm.setRange(10, 100)
        self.pwm.setValue(50)
        self.lbl_pwm = QtWidgets.QLabel("Potencia 50 %")
        self.pwm.valueChanged.connect(lambda x: self.lbl_pwm.setText(f"Potencia {x} %"))
        g.addWidget(self.lbl_pwm, 3, 0, 1, 3)
        g.addWidget(self.pwm, 4, 0, 1, 3)

        self.lbl_rol = QtWidgets.QLabel(nota_rol(role))
        self.lbl_rol.setObjectName("alerta")
        self.lbl_rol.setWordWrap(True)

        panel = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(panel)
        for w in (estado, simulacion, self.manual, self.lbl_rol):
            pl.addWidget(w)
        pl.addStretch(1)

        vista = QtWidgets.QScrollArea()
        vista.setWidgetResizable(True)
        vista.setFrameShape(QtWidgets.QFrame.NoFrame)
        vista.setWidget(self.twin)
        lay = QtWidgets.QHBoxLayout(self)
        lay.addWidget(vista, 1)
        lay.addWidget(scroll(panel, 340))

        self.btn_inicio.clicked.connect(self._alternar)
        self.modo.currentIndexChanged.connect(self._cambiar_modo)
        self.btn_obstaculo.clicked.connect(self._obstaculo)
        self.btn_reinicio.clicked.connect(self._reiniciar)

        self._aplicar_permisos()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    def _aplicar_permisos(self):
        ok = puede_controlar(self.role)
        auto = self.modo.currentData() == "AUTO"
        for w in (self.btn_inicio, self.modo, self.vel, self.btn_reinicio):
            w.setEnabled(ok)
        self.btn_obstaculo.setEnabled(ok and auto)
        self.manual.setEnabled(ok and not auto)

    def _parar_twin(self):
        self.twin.set_telemetria("S", 0, 85.0, [0, 0, 0, 0, 0])

    def _alternar(self):
        if self.corriendo:
            self.corriendo = False
            self.btn_inicio.setText("Iniciar recorrido")
            self._parar_twin()
            self.auditar("SIM_ZENO_DETENER", {})
            return
        self.corriendo = True
        self._ultimo = time.monotonic()
        self.btn_inicio.setText("Detener recorrido")
        self.auditar("SIM_ZENO_INICIAR", {"modo": self.modo.currentData()})

    def _cambiar_modo(self):
        self.twin.set_modo(self.modo.currentData())
        self._aplicar_permisos()

    def _obstaculo(self):
        self.sim.provocar_obstaculo(4.0)
        self.auditar("SIM_ZENO_OBSTACULO", {})

    def _reiniciar(self):
        self.sim.reset()
        self._parar_twin()

    def _manual(self, direccion):
        parado = direccion == "S"
        self.twin.set_telemetria(direccion, 0 if parado else self.pwm.value(), 85.0,
                                 [0, 0, 0, 0, 0] if parado else SENSORES_CENTRO, "SEGUIMIENTO", "NINGUNO")

    def _tick(self):
        ahora = time.monotonic()
        dt, self._ultimo = ahora - self._ultimo, ahora
        auto = self.modo.currentData() == "AUTO"
        if self.corriendo and auto:
            self.twin.set_telemetria(**self.sim.tick(dt, self.vel.value() / 100.0))
        t, v = self.twin, self.v
        v["modo"].setText("Automático" if t.modo == "AUTO" else "Manual")
        v["dir"].setText(DIRECCIONES.get(t.direccion, t.direccion))
        v["pwm"].setText(f"{t.velocidad_pwm} %")
        v["dist"].setText(f"{t.distancia_frontal:.0f} cm")
        v["sub"].setText(t.subestado)
        v["qr"].setText(t.estacion_qr)
        v["seg"].setText(self.sim.segmento if (self.corriendo and auto) else "—")
        v["sens"].setText(marcas(t.sensores_linea))
