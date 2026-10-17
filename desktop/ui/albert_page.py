import time

from PyQt5 import QtCore, QtWidgets

from core.permissions import nota_rol, puede_controlar
from core.sim import AlbertSimulator
from ui.panel import grupo_valores, marcas, scroll
from ui.twins.albert_twin import AlbertDigitalTwin

RECETAS = [("Pinto", "PINTO"), ("Negro", "NEGRO"), ("Peruano", "PERUANO"), ("Rotativo", "ROTATIVO"),
           ("Doble", "DOBLE"), ("Aleatorio", "ALEATORIO"), ("3 negro + 1 pinto", "3NEGRO_1PINTO"),
           ("Bicolor", "BICOLOR"), ("Gourmet", "GOURMET")]
FASES = {"REPOSO": "En reposo", "ABRIENDO": "Abriendo silo", "VERTIDO": "Vertiendo grano",
         "BARRIDO_CIERRE": "Cerrando silo"}
ESTACION1 = {"STANDBY": "Lista", "DISPENSING": "Soltando vaso", "SIN_VASOS": "Sin vasos"}
SILOS = [("Silo negro", 0), ("Silo pinto", 1), ("Silo peruano", 2)]


class AlbertPage(QtWidgets.QWidget):
    """Gemelo de Albert (dosificadora) con su panel de estado y simulación."""

    def __init__(self, role, auditar):
        super().__init__()
        self.role, self.auditar = role, auditar
        self.sim = AlbertSimulator()
        self._ultimo = time.monotonic()

        self.twin = AlbertDigitalTwin(self)
        self.twin.alerta_silo_vacio.connect(self._silo_vacio)

        estado, self.v = grupo_valores("Estado en vivo", [
            ("modo", "Modo"), ("terminados", "Vasos terminados"), ("silo", "Vasos en el silo"),
            ("est1", "Estación 1"), ("tolva", "Tolva"), ("dosif", "Dosificación"),
            ("sensores", "Sensores (E1 E2 E3 tolva)")])

        self.btn_inicio = QtWidgets.QPushButton("Iniciar simulación")
        self.modo = QtWidgets.QComboBox()
        self.modo.addItem("Automático", "AUTO")
        self.modo.addItem("Manual", "MANUAL")
        self.receta = QtWidgets.QComboBox()
        for nombre, clave in RECETAS:
            self.receta.addItem(nombre, clave)
        self.periodo = QtWidgets.QSpinBox()
        self.periodo.setRange(int(AlbertSimulator.PERIODO_MIN), 30)
        self.periodo.setSuffix(" s por paso")
        self.periodo.setToolTip("Mínimo 8 s: así el sellado termina antes del siguiente paso.")
        self.chk_recarga = QtWidgets.QCheckBox("Recargar vasos automáticamente")
        self.chk_recarga.setChecked(True)
        self.chk_recarga.setToolTip("Desmárcalo para probar la alerta de silo vacío.")
        self.lbl_proximo = QtWidgets.QLabel("")
        self.lbl_proximo.setObjectName("muted")
        self.btn_paso = QtWidgets.QPushButton("Avanzar un paso")
        self.btn_recarga = QtWidgets.QPushButton("Recargar vasos")
        self.btn_reset = QtWidgets.QPushButton("Reiniciar contador")
        self.lbl_alerta = QtWidgets.QLabel("")
        self.lbl_alerta.setObjectName("alerta")
        self.lbl_alerta.setWordWrap(True)

        simulacion = QtWidgets.QGroupBox("Simulación")
        form = QtWidgets.QFormLayout(simulacion)
        form.addRow(self.btn_inicio)
        form.addRow("Modo", self.modo)
        form.addRow("Receta", self.receta)
        form.addRow("Ritmo", self.periodo)
        form.addRow(self.chk_recarga)
        form.addRow(self.lbl_proximo)
        form.addRow(self.btn_paso)
        form.addRow(self.btn_recarga)
        form.addRow(self.btn_reset)

        self.manual = QtWidgets.QGroupBox("Control manual")
        ml = QtWidgets.QVBoxLayout(self.manual)
        for texto, idx in SILOS:
            b = QtWidgets.QPushButton(texto)
            b.clicked.connect(lambda _c, i=idx: self.twin.abrir_silo_manual(i))
            ml.addWidget(b)
        b = QtWidgets.QPushButton("Vaciar tolva")
        b.clicked.connect(lambda _c: self.twin.vaciar_tolva_manual())
        ml.addWidget(b)

        self.lbl_rol = QtWidgets.QLabel(nota_rol(role))
        self.lbl_rol.setObjectName("alerta")
        self.lbl_rol.setWordWrap(True)

        panel = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(panel)
        for w in (estado, simulacion, self.manual, self.lbl_alerta, self.lbl_rol):
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
        self.receta.currentIndexChanged.connect(self._cambiar_receta)
        self.periodo.valueChanged.connect(self.sim.set_periodo)
        self.btn_paso.clicked.connect(lambda _c: self.twin.animar_rotacion())
        self.btn_recarga.clicked.connect(self._recargar)
        self.btn_reset.clicked.connect(lambda _c: self.twin.reset_contador())

        self._aplicar_permisos()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(200)

    def _aplicar_permisos(self):
        ok = puede_controlar(self.role)
        auto = self.modo.currentData() == "AUTO"
        for w in (self.btn_inicio, self.modo, self.receta, self.periodo, self.chk_recarga, self.btn_recarga, self.btn_reset):
            w.setEnabled(ok)
        self.btn_paso.setEnabled(ok and not auto)
        self.manual.setEnabled(ok and not auto)

    def _alternar(self):
        if self.sim.activo:
            self.sim.detener()
            self.btn_inicio.setText("Iniciar simulación")
            self.auditar("SIM_ALBERT_DETENER", {})
            return
        modo = self.modo.currentData()
        self.twin.set_modo(modo)
        self._cambiar_receta()
        self.sim.iniciar()
        self._ultimo = time.monotonic()
        self.btn_inicio.setText("Detener simulación")
        self.auditar("SIM_ALBERT_INICIAR", {"receta": self.receta.currentData(), "modo": modo})

    def _cambiar_modo(self):
        self.twin.set_modo(self.modo.currentData())
        self._aplicar_permisos()

    def _cambiar_receta(self):
        self.twin.set_secuencia_auto(self.receta.currentData())

    def _silo_vacio(self, texto):
        self.lbl_alerta.setText(texto)

    def _recargar(self):
        self.twin.recargar_silo(4)
        self.lbl_alerta.setText("")

    def _tick(self):
        ahora = time.monotonic()
        dt, self._ultimo = ahora - self._ultimo, ahora
        auto = self.modo.currentData() == "AUTO"
        if auto:
            for _ in range(self.sim.tick(dt)):
                self.twin.animar_rotacion()
        t, v = self.twin, self.v
        if self.chk_recarga.isChecked() and t.estado_estacion1 == "SIN_VASOS":
            self._recargar()
        v["modo"].setText("Automático" if t.modo_operacion == "AUTO" else "Manual")
        v["terminados"].setText(str(t.vasos_terminados))
        v["silo"].setText(f"{t.vasos_en_silo} de 4")
        v["est1"].setText(ESTACION1.get(t.estado_estacion1, t.estado_estacion1))
        v["tolva"].setText(f"{t.nivel_tolva:.0f} %")
        v["dosif"].setText(FASES.get(t.fase_dosif, t.fase_dosif))
        v["sensores"].setText(marcas([t.sensor_fc51_e1, t.sensor_fc51_e2, t.sensor_fc51_e3, t.sensor_ky032_tolva]))
        self.lbl_proximo.setText(f"Próximo paso en {self.sim.restante:.0f} s" if (auto and self.sim.activo) else "")
