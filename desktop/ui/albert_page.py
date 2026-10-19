import time

from PyQt5 import QtCore, QtWidgets

from core.estado import sanear_albert
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
NODO = "ALBERT-01"
PUBLICAR_CADA = 0.5  # segundos entre envíos al publicar


class AlbertPage(QtWidgets.QWidget):
    """Gemelo de Albert (dosificadora) con su panel de estado y simulación."""

    NODO = NODO

    def __init__(self, role, auditar, sync=None):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.role, self.auditar, self.sync = role, auditar, sync
        self.sim = AlbertSimulator()
        self._ultimo = time.monotonic()
        self._acum_pub = 0.0
        self._publicador = ""

        self.twin = AlbertDigitalTwin(self)
        self.twin.alerta_silo_vacio.connect(self._silo_vacio)

        self.fuente = QtWidgets.QComboBox()
        if sync:
            self.fuente.addItem("Ver la planta (compartido)", "VER")
        if sync and puede_controlar(role):
            self.fuente.addItem("Publicar mi simulación", "PUBLICAR")
        if puede_controlar(role) or not sync:
            self.fuente.addItem("Local (solo en esta PC)", "LOCAL")
        self._fuente = self.fuente.itemData(0)
        self.twin.espejo = self._fuente == "VER"
        self.lbl_fuente = QtWidgets.QLabel("")
        self.lbl_fuente.setWordWrap(True)
        self.lbl_fuente.setObjectName("muted")
        caja_fuente = QtWidgets.QGroupBox("Fuente de datos")
        fl = QtWidgets.QVBoxLayout(caja_fuente)
        fl.addWidget(self.fuente)
        fl.addWidget(self.lbl_fuente)

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
        for w in (caja_fuente, estado, simulacion, self.manual, self.lbl_alerta, self.lbl_rol):
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
        self._texto_fuente()
        self.fuente.currentIndexChanged.connect(self._cambiar_fuente)
        if sync:
            sync.estado.connect(self._on_estado)
            sync.senal.connect(self._on_senal)
            sync.error.connect(self._on_error_sync)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(200)

    @property
    def publicando(self):
        return self._fuente == "PUBLICAR"

    def _aplicar_permisos(self):
        ok = puede_controlar(self.role) and self._fuente != "VER"
        auto = self.modo.currentData() == "AUTO"
        for w in (self.btn_inicio, self.modo, self.receta, self.periodo, self.chk_recarga, self.btn_recarga, self.btn_reset):
            w.setEnabled(ok)
        self.btn_paso.setEnabled(ok and not auto)
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
        if self.sim.activo:
            self._alternar()
        self._fuente = nueva
        self.twin.espejo = nueva == "VER"
        if nueva == "PUBLICAR":
            self._acum_pub = PUBLICAR_CADA  # publica enseguida
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
            self.fuente.setCurrentIndex(0)  # vuelve a «Ver la planta»
            self.lbl_fuente.setText(f"{quien} ya publica este nodo. Pasaste a ver la planta.")
        else:
            self.lbl_fuente.setText(f"No se pudo publicar: {msg}")

    def _on_estado(self, nodo, estado, _publicador):
        if nodo != NODO or self._fuente != "VER":
            return
        limpio = sanear_albert(estado)  # lo publica otra persona: nunca se aplica sin validar
        if not limpio:
            self.lbl_fuente.setText("Se recibió un estado no válido y se ignoró.")
            return
        try:
            self.twin.importar_estado(limpio)
        except Exception as ex:  # datos ajenos nunca deben romper la pantalla
            self.lbl_fuente.setText(f"No se pudo aplicar el estado recibido ({type(ex).__name__}).")
            return
        self.lbl_proximo.setText(f"Próximo paso en {limpio.get('restante', 0):.0f} s" if limpio.get("corriendo") else "")

    def _on_senal(self, nodo, publicador):
        if nodo == NODO:
            self._publicador = publicador
            if self._fuente == "VER":
                self._texto_fuente()

    def _on_error_sync(self, msg):
        if self._fuente == "VER":
            self.lbl_fuente.setText(f"Estado compartido no disponible: {msg}")

    def _alternar(self):
        if self._fuente == "VER":
            return
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
        ver = self._fuente == "VER"
        if auto and not ver:
            for _ in range(self.sim.tick(dt)):
                self.twin.animar_rotacion()
        t, v = self.twin, self.v
        if not ver and self.chk_recarga.isChecked() and t.estado_estacion1 == "SIN_VASOS":
            self._recargar()
        if self._fuente == "PUBLICAR" and self.sync:
            self._acum_pub += dt
            if self._acum_pub >= PUBLICAR_CADA:
                self._acum_pub = 0.0
                estado = t.exportar_estado()
                estado.update({"corriendo": self.sim.activo, "restante": round(self.sim.restante)})
                self.sync.publicar(NODO, estado, self._error_publicar)
        v["modo"].setText("Automático" if t.modo_operacion == "AUTO" else "Manual")
        v["terminados"].setText(str(t.vasos_terminados))
        v["silo"].setText(f"{t.vasos_en_silo} de 4")
        v["est1"].setText(ESTACION1.get(t.estado_estacion1, t.estado_estacion1))
        v["tolva"].setText(f"{t.nivel_tolva:.0f} %")
        v["dosif"].setText(FASES.get(t.fase_dosif, t.fase_dosif))
        v["sensores"].setText(marcas([t.sensor_fc51_e1, t.sensor_fc51_e2, t.sensor_fc51_e3, t.sensor_ky032_tolva]))
        if not ver:
            self.lbl_proximo.setText(f"Próximo paso en {self.sim.restante:.0f} s" if (auto and self.sim.activo) else "")
