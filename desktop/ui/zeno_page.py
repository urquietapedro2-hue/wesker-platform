import time

from PyQt5 import QtCore, QtWidgets

from core.estado import sanear_zeno
from core.permissions import nota_rol, puede_controlar
from core.sim import ZenoSimulator
from ui.panel import grupo_valores, marcas, scroll
from ui.twins.zeno_twin import ZenoDigitalTwin

DIRECCIONES = {"F": "Adelante", "B": "Atrás", "L": "Izquierda", "R": "Derecha", "S": "Detenido",
               "FL": "Adelante-izquierda", "FR": "Adelante-derecha", "BL": "Atrás-izquierda",
               "BR": "Atrás-derecha", "ESTACION": "En estación"}
SENSORES_CENTRO = [0, 0, 1, 0, 0]
NODO = "ZENO-01"
PUBLICAR_CADA = 0.5  # segundos entre envíos al publicar


class ZenoPage(QtWidgets.QWidget):
    """Gemelo de Zeno (AGV) con su panel de telemetría y simulación."""

    NODO = NODO

    def __init__(self, role, auditar, sync=None):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.role, self.auditar, self.sync = role, auditar, sync
        self.sim = ZenoSimulator()
        self.corriendo = False
        self._ultimo = time.monotonic()
        self._acum_pub = 0.0
        self._publicador = ""
        self._seg_remoto = ""

        self.twin = ZenoDigitalTwin(self)

        self.fuente = QtWidgets.QComboBox()
        if sync:
            self.fuente.addItem("Ver la planta (compartido)", "VER")
        if sync and puede_controlar(role):
            self.fuente.addItem("Publicar mi simulación", "PUBLICAR")
        if puede_controlar(role) or not sync:
            self.fuente.addItem("Local (solo en esta PC)", "LOCAL")
        self._fuente = self.fuente.itemData(0)
        self.lbl_fuente = QtWidgets.QLabel("")
        self.lbl_fuente.setWordWrap(True)
        self.lbl_fuente.setObjectName("muted")
        caja_fuente = QtWidgets.QGroupBox("Fuente de datos")
        fl = QtWidgets.QVBoxLayout(caja_fuente)
        fl.addWidget(self.fuente)
        fl.addWidget(self.lbl_fuente)

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
        for w in (caja_fuente, estado, simulacion, self.manual, self.lbl_rol):
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
        self._texto_fuente()
        self.fuente.currentIndexChanged.connect(self._cambiar_fuente)
        if sync:
            sync.estado.connect(self._on_estado)
            sync.senal.connect(self._on_senal)
            sync.error.connect(self._on_error_sync)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(100)

    @property
    def publicando(self):
        return self._fuente == "PUBLICAR"

    def _aplicar_permisos(self):
        ok = puede_controlar(self.role) and self._fuente != "VER"
        auto = self.modo.currentData() == "AUTO"
        for w in (self.btn_inicio, self.modo, self.vel, self.btn_reinicio):
            w.setEnabled(ok)
        self.btn_obstaculo.setEnabled(ok and auto)
        self.manual.setEnabled(ok and not auto)

    def _texto_fuente(self):
        if self._fuente == "VER":
            txt = (f"Viendo la planta. Publica: {self._publicador}." if self._publicador
                   else "Sin señal: nadie publica este nodo todavía.")
        elif self._fuente == "PUBLICAR":
            txt = "Publicando: todos ven tu simulación."
        else:
            txt = "Local: lo que hagas aquí no lo ve nadie."
        self.lbl_fuente.setText(txt)

    def _cambiar_fuente(self):
        nueva, anterior = self.fuente.currentData(), self._fuente
        if nueva == anterior:
            return
        if anterior == "PUBLICAR":
            self._soltar()
        if self.corriendo:
            self._alternar()
        self._fuente = nueva
        if nueva == "PUBLICAR":
            self._acum_pub = PUBLICAR_CADA
            self.auditar("PUBLICAR_INICIAR", {"nodo": NODO})
        self._aplicar_permisos()
        self._texto_fuente()

    def _soltar(self):
        if self.sync:
            self.sync.liberar(NODO)
        self.auditar("PUBLICAR_DETENER", {"nodo": NODO})

    def _error_publicar(self, msg):
        if msg.startswith("OCUPADO"):
            quien = msg.split(":", 1)[1] if ":" in msg else "otra persona"
            self.fuente.setCurrentIndex(0)
            self.lbl_fuente.setText(f"{quien} ya publica este nodo. Pasaste a ver la planta.")
        else:
            self.lbl_fuente.setText(f"No se pudo publicar: {msg}")

    def _on_estado(self, nodo, e, _publicador):
        if nodo != NODO or self._fuente != "VER":
            return
        t = sanear_zeno(e)  # lo publica otra persona: nunca se aplica sin validar
        try:
            self.twin.set_modo(t["modo"])
            self.twin.set_telemetria(t["direccion"], t["velocidad"], t["distancia"], t["sensores"], t["subestado"], t["qr"])
        except Exception as ex:  # datos ajenos nunca deben romper la pantalla
            self.lbl_fuente.setText(f"No se pudo aplicar el estado recibido ({type(ex).__name__}).")
            return
        self._seg_remoto = t["tramo"]

    def _on_senal(self, nodo, publicador):
        if nodo == NODO:
            self._publicador = publicador
            if self._fuente == "VER":
                self._texto_fuente()

    def _on_error_sync(self, msg):
        if self._fuente == "VER":
            self.lbl_fuente.setText(f"Estado compartido no disponible: {msg}")

    def _parar_twin(self):
        self.twin.set_telemetria("S", 0, 85.0, [0, 0, 0, 0, 0])

    def _alternar(self):
        if self._fuente == "VER":
            return
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
        ver = self._fuente == "VER"
        if self.corriendo and auto and not ver:
            self.twin.set_telemetria(**self.sim.tick(dt, self.vel.value() / 100.0))
        t, v = self.twin, self.v
        if self._fuente == "PUBLICAR" and self.sync:
            self._acum_pub += dt
            if self._acum_pub >= PUBLICAR_CADA:
                self._acum_pub = 0.0
                tramo = self.sim.segmento if (self.corriendo and auto) else ""
                self.sync.publicar(NODO, {"modo": t.modo, "dir": t.direccion, "pwm": t.velocidad_pwm,
                                          "dist": t.distancia_frontal, "sens": [int(x) for x in t.sensores_linea],
                                          "sub": t.subestado, "qr": t.estacion_qr, "seg": tramo,
                                          "corriendo": self.corriendo}, self._error_publicar)
        v["modo"].setText("Automático" if t.modo == "AUTO" else "Manual")
        v["dir"].setText(DIRECCIONES.get(t.direccion, t.direccion))
        v["pwm"].setText(f"{t.velocidad_pwm} %")
        v["dist"].setText(f"{t.distancia_frontal:.0f} cm")
        v["sub"].setText(t.subestado)
        v["qr"].setText(t.estacion_qr)
        tramo_vivo = self._seg_remoto if ver else (self.sim.segmento if (self.corriendo and auto) else "")
        v["seg"].setText(tramo_vivo or "—")
        v["sens"].setText(marcas(t.sensores_linea))
