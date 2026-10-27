import time

from PyQt5 import QtCore, QtWidgets

from core.estado import sanear_zeno
from core.permissions import nota_rol, puede_calibrar, puede_controlar
from core.sim import ZenoSimulator
from core.zeno_enlace import detectar_estacion
from ui.panel import grupo_valores, marcas, scroll
from ui.twins.zeno_twin import ZenoDigitalTwin
from ui.calibracion_dialog import CalibracionDialog
from ui.zeno_camara import VisorCamara

DIRECCIONES = {"F": "Adelante", "B": "Atrás", "L": "Izquierda", "R": "Derecha", "S": "Detenido",
               "FL": "Adelante-izquierda", "FR": "Adelante-derecha", "BL": "Atrás-izquierda",
               "BR": "Atrás-derecha", "ESTACION": "En estación"}
SENSORES_CENTRO = [0, 0, 1, 0, 0]
NODO = "ZENO-01"
PUBLICAR_CADA = 0.5  # segundos entre envíos al publicar


class ZenoPage(QtWidgets.QWidget):
    """Gemelo de Zeno (AGV) con su panel de telemetría y simulación."""

    NODO = NODO

    def __init__(self, role, auditar, sync=None, evento=None, real=None):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setObjectName("pagina")
        self.role, self.auditar, self.sync = role, auditar, sync
        self.evento = evento or (lambda *a, **k: None)  # el HMI recoge lo que merece verse, oírse o decirse
        self.sim = ZenoSimulator()
        self.corriendo = False
        self._ultimo = time.monotonic()
        self._acum_pub = 0.0
        self._publicador = ""
        self._seg_remoto = ""
        self.real, self.enlace = real, None            # acceso al Zeno real (si el HMI lo ofrece)
        self._conectado_real, self._modo_sincronizado, self._origen_remoto = False, False, "simulacion"
        self.visor, self.calibracion, self._qr_previo, self._logi_previa = None, None, "NINGUNO", {}

        self.twin = ZenoDigitalTwin(self)

        self.fuente = QtWidgets.QComboBox()
        if sync:
            self.fuente.addItem("Ver la planta (compartido)", "VER")
        if sync and puede_controlar(role):
            self.fuente.addItem("Publicar mi simulación", "PUBLICAR")
        if real and puede_controlar(role):
            self.fuente.addItem("Zeno real (conectar por red)", "REAL")
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
            ("modo", "Modo"), ("origen", "Origen de los datos"), ("dir", "Dirección"), ("pwm", "Potencia"), ("dist", "Distancia frontal"),
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

        caja_logi, self.vl = grupo_valores("Ruta y rampas", [
            ("fase", "Fase"), ("estacion", "Estación (QR)"), ("rampa1", "Rampa 1 (izquierda)"), ("rampa2", "Rampa 2 (derecha)"),
            ("espera", "Espera de descarga"), ("alarma", "Alarma"), ("servos", "Servos")])
        self.btn_r1 = QtWidgets.QPushButton("Rampa 1 cargada")
        self.btn_r2 = QtWidgets.QPushButton("Rampa 2 cargada")
        self.btn_abortar = QtWidgets.QPushButton("Abortar fase (seguir la línea)")
        self.btn_camara = QtWidgets.QPushButton("Abrir cámara de Zeno")
        self.btn_calibrar = QtWidgets.QPushButton("Calibración…")
        for b, cmd, txt in ((self.btn_r1, "CARGA_RAMPA,1", "Rampa 1 cargada"), (self.btn_r2, "CARGA_RAMPA,2", "Rampa 2 cargada"),
                            (self.btn_abortar, "ABORTAR", "Fase abortada")):
            b.clicked.connect(lambda _c, c=cmd, t=txt: self._orden_logistica(c, t))
            caja_logi.layout().addRow(b)
        self.btn_camara.clicked.connect(lambda: self._abrir_visor("manual"))
        self.btn_calibrar.clicked.connect(self._abrir_calibracion)
        caja_logi.layout().addRow(self.btn_camara)
        caja_logi.layout().addRow(self.btn_calibrar)

        self.lbl_rol = QtWidgets.QLabel(nota_rol(role))
        self.lbl_rol.setObjectName("alerta")
        self.lbl_rol.setWordWrap(True)

        panel = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(panel)
        for w in (caja_fuente, estado, caja_logi, simulacion, self.manual, self.lbl_rol):
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
        return self._fuente in ("PUBLICAR", "REAL")

    def _aplicar_permisos(self):
        ok = puede_controlar(self.role) and self._fuente != "VER"
        real = self._fuente == "REAL"
        auto = self.modo.currentData() == "AUTO"
        for w in (self.btn_inicio, self.vel, self.btn_reinicio):
            w.setEnabled(ok and not real)       # la simulación no se usa con el robot real
        self.modo.setEnabled(ok and (not real or self._conectado_real))
        self.btn_obstaculo.setEnabled(ok and auto and not real)
        self.manual.setEnabled(ok and not auto and (not real or self._conectado_real))
        enlazado = ok and real and self._conectado_real
        for w in (self.btn_r1, self.btn_r2, self.btn_abortar, self.btn_camara):
            w.setEnabled(enlazado)      # la ruta, las rampas y la cámara son del robot real
        self.btn_calibrar.setEnabled(real and self._conectado_real and puede_calibrar(self.role))

    def _texto_fuente(self):
        if self._fuente == "VER":
            txt = (f"Viendo la planta. Publica: {self._publicador}." if self._publicador
                   else "Sin señal: nadie publica este nodo todavía.")
        elif self._fuente == "PUBLICAR":
            txt = "Publicando: todos ven tu simulación."
        elif self._fuente == "REAL":
            txt = "Zeno real: conectando…"
        else:
            txt = "Local: lo que hagas aquí no lo ve nadie."
        self.lbl_fuente.setText(txt)

    def _cambiar_fuente(self):
        nueva, anterior = self.fuente.currentData(), self._fuente
        if nueva == anterior:
            return
        if anterior == "PUBLICAR":
            self._soltar()
        if anterior == "REAL":
            self._detener_real()
        if self.corriendo:
            self._alternar()
        self._fuente = nueva
        if nueva == "PUBLICAR":
            self._acum_pub = PUBLICAR_CADA
            self.auditar("PUBLICAR_INICIAR", {"nodo": NODO})
        if nueva == "REAL":
            self._iniciar_real()
        self._aplicar_permisos()
        self._texto_fuente()

    # ---------------- Zeno real ----------------
    def _iniciar_real(self):
        self.enlace = self.real.crear_enlace()
        self._conectado_real, self._modo_sincronizado, self._acum_pub = False, False, PUBLICAR_CADA
        self.enlace.iniciar()
        self.auditar("ZENO_REAL_CONECTAR", {"destinos": len(self.enlace.candidatos), "con_token": bool(self.enlace.token)})
        self.evento("info", "Conectando con Zeno real…")

    def _detener_real(self):
        self.cerrar()
        self._soltar()  # libera el nodo en la nube para que otros no vean datos viejos
        self.auditar("ZENO_REAL_DESCONECTAR", {})
        self.evento("warn", "Enlace con Zeno real cerrado")

    def _abrir_visor(self, motivo):
        if self.enlace is None:
            return
        if self.visor is None:
            self.visor = VisorCamara(lambda: self.enlace.url_video() if self.enlace is not None else "", self)
        self.visor.abrir(motivo)
        self.auditar("ZENO_CAMARA_ABRIR", {"motivo": motivo})   # nunca se registra la URL: lleva el token

    def _abrir_calibracion(self):
        if self.enlace is None or not puede_calibrar(self.role):
            return
        if self.calibracion is None:
            self.calibracion = CalibracionDialog(lambda: self.enlace, lambda: self.modo.currentData(), puede_calibrar(self.role),
                                                 self.auditar, self)
        self.calibracion.show()
        self.calibracion.raise_()
        self.auditar("ZENO_CAL_ABRIR", {})

    def _orden_logistica(self, orden, texto):
        salio = self.enlace is not None and self.enlace.enviar(orden)
        self.auditar("ZENO_REAL_LOGISTICA", {"orden": orden, "enviada": salio})
        self.evento("info" if salio else "warn", f"{texto}: enviada a Zeno" if salio else f"Sin enlace: «{texto}» no salió")

    def _mostrar_logistica(self, d):
        v = self.vl
        if not d:
            for w in v.values():
                w.setText("—")
            return
        fases = {"ST1_CARGA_R1": "Estación 1: esperando carga de la rampa 1", "ST1_INDEXANDO": "Estación 1: avance de indexación",
                 "ST1_CARGA_R2": "Estación 1: esperando carga de la rampa 2", "SEGUIMIENTO": "Siguiendo la línea",
                 "ESCANEANDO_QR": "En intersección: buscando QR", "DESCARGANDO": "Descargando", "SALIENDO": "Saliendo de la estación",
                 "MANUAL": "Modo manual"}
        v["fase"].setText(fases.get(d["fase"], d["fase"]))
        v["estacion"].setText(d["estacion"] if d["estacion"] != "NINGUNA" else "—")
        v["rampa1"].setText("Cargada" if d["carga_r1"] else "Vacía")
        v["rampa2"].setText("Cargada" if d["carga_r2"] else "Vacía")
        v["espera"].setText(f"{d['restante_s']:.0f} s" if d["fase"] == "DESCARGANDO" else "—")
        v["alarma"].setText({"NINGUNA": "Sin alarma", "TIMEOUT_CARGA": "La carga tarda demasiado",
                             "QR_NO_LEIDO": "No se lee el QR"}.get(d["alarma"], d["alarma"]))
        a = d["servos"]
        v["servos"].setText(d["backend"] + ("" if d["i2c"] or d["backend"] != "GPIO" else " (sin I2C)") +
                            " · dir " + ("—" if a.get("direccion") is None else f"{a['direccion']:.0f}°"))

    def _eventos_logistica(self, d):
        previa, self._logi_previa = self._logi_previa, d or {}
        if not d:
            return
        if d["alarma"] != "NINGUNA" and d["alarma"] != previa.get("alarma"):
            self.evento("error", "Zeno en alarma: " + ("la carga tarda demasiado" if d["alarma"] == "TIMEOUT_CARGA" else "no lee el QR"))
        if d["fase"] != previa.get("fase") and previa:
            if d["fase"] == "DESCARGANDO":
                self.evento("info", f"Zeno descarga en {d['estacion']}")
            elif d["fase"] == "ST1_CARGA_R1":
                self.evento("info", "Zeno está en la Estación 1 esperando la carga")
        if d["backend"] == "GPIO" and previa.get("backend") == "PCA9685":
            self.evento("warn", "Los servos pasaron del PCA9685 a GPIO (falló el I2C)")

    def cerrar(self):
        """Corta el enlace con el robot (al cambiar de fuente o al cerrar el HMI: Zeno frena solo al perder al HMI)."""
        if self.visor is not None:
            self.visor.cerrar_video()
            self.visor.close()
            self.visor = None
        if self.calibracion is not None:
            self.calibracion.close()
            self.calibracion = None
        enlace, self.enlace, self._conectado_real = self.enlace, None, False
        if enlace is not None:
            enlace.detener()

    def _actualizar_real(self, snap):
        conectado = snap["estado"] == "conectado" and snap["telemetria"] is not None
        if conectado != self._conectado_real:
            self._conectado_real = conectado
            self._aplicar_permisos()
            if conectado:
                self.evento("ok", f"Zeno real conectado por la red «{snap['red']}»", "nodo_en_linea", NODO)
            else:
                self._parar_twin()  # nunca se muestran datos viejos como si fueran actuales
                self._qr_previo = "NINGUNO"
                self.twin.set_logistica(None)
                self._mostrar_logistica(None)
                self.evento("warn", "Se perdió el enlace con Zeno real", "nodo_sin_senal", NODO)
        if conectado:
            t = sanear_zeno(snap["telemetria"])
            self.twin.set_telemetria(t["direccion"], t["velocidad"], t["distancia"], t["sensores"], t["subestado"], t["qr"])
            ruta = snap.get("ruta")
            self.twin.set_logistica(ruta)
            self._mostrar_logistica(ruta)
            self._eventos_logistica(ruta)
            estacion = detectar_estacion(self._qr_previo, t["qr"])   # disparador: el QR pasó a una estación distinta
            self._qr_previo = t["qr"]
            if estacion:
                self._abrir_visor(estacion)
            if not self._modo_sincronizado and snap["modo"]:  # Zeno dice en qué modo está: la pantalla se alinea, no al revés
                self._modo_sincronizado = True
                self.modo.blockSignals(True)
                self.modo.setCurrentIndex(max(0, self.modo.findData(snap["modo"])))
                self.modo.blockSignals(False)
                self.twin.set_modo(snap["modo"])
                self._aplicar_permisos()
            self.lbl_fuente.setText(f"Zeno real conectado por «{snap['red']}»" + (f" (v{snap['version']})." if snap["version"] else "."))
            return
        textos = {"rechazado": "Zeno rechazó el token. Corrígelo en la pantalla Nodos y vuelve a elegir «Zeno real».",
                  "sin_destino": "No hay ninguna IP de Zeno registrada. Un Admin debe agregarla en la pantalla Nodos."}
        self.lbl_fuente.setText(textos.get(snap["estado"], f"Zeno real: {snap['detalle'] or 'conectando…'}"))

    def _mover_real(self, direccion):
        orden = "S" if direccion == "S" else f"{direccion},{self.pwm.value()}"
        salio = self.enlace is not None and self.enlace.enviar(orden)
        self.auditar("ZENO_REAL_ORDEN", {"orden": orden, "enviada": salio})
        if not salio:
            self.evento("warn", "Sin enlace con Zeno: la orden no salió")

    def _soltar(self):
        if self.sync:
            self.sync.liberar(NODO)
        self.auditar("PUBLICAR_DETENER", {"nodo": NODO})

    def _error_publicar(self, msg):
        if msg.startswith("OCUPADO"):
            quien = msg.split(":", 1)[1] if ":" in msg else "otra persona"
            self.fuente.setCurrentIndex(0)
            self.lbl_fuente.setText(f"{quien} ya publica este nodo. Pasaste a ver la planta.")
            self.evento("warn", f"{quien} ya publica {NODO}; pasaste a ver la planta")
        else:
            self.lbl_fuente.setText(f"No se pudo publicar: {msg}")
            self.evento("error", f"No se pudo publicar {NODO}: {msg}", "error_publicacion", NODO)

    def _on_estado(self, nodo, e, _publicador):
        if nodo != NODO or self._fuente != "VER":
            return
        t = sanear_zeno(e)  # lo publica otra persona: nunca se aplica sin validar
        try:
            self.twin.set_modo(t["modo"])
            self.twin.set_telemetria(t["direccion"], t["velocidad"], t["distancia"], t["sensores"], t["subestado"], t["qr"])
            self.twin.set_logistica(t["logistica"])
            self._mostrar_logistica(t["logistica"])
        except Exception as ex:  # datos ajenos nunca deben romper la pantalla
            self.lbl_fuente.setText(f"No se pudo aplicar el estado recibido ({type(ex).__name__}).")
            self.evento("error", f"Estado de {NODO} no aplicable ({type(ex).__name__}); se ignoró", "estado_invalido", NODO)
            return
        self._seg_remoto, self._origen_remoto = t["tramo"], t["origen"]

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
        if self._fuente in ("VER", "REAL"):
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
        modo = self.modo.currentData()
        self.twin.set_modo(modo)
        self._aplicar_permisos()
        if self._fuente == "REAL" and self.enlace is not None:
            salio = self.enlace.enviar(f"MODE,{modo}")
            self.auditar("ZENO_REAL_MODO", {"modo": modo, "enviada": salio})
            self.evento("info" if salio else "warn", f"Modo {modo} enviado a Zeno" if salio else "Sin enlace: el modo no se envió")

    def _obstaculo(self):
        self.sim.provocar_obstaculo(4.0)
        self.auditar("SIM_ZENO_OBSTACULO", {})

    def _reiniciar(self):
        self.sim.reset()
        self._parar_twin()

    def _manual(self, direccion):
        if self._fuente == "REAL":
            return self._mover_real(direccion)
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
        if self._fuente == "REAL" and self.enlace is not None:
            self._actualizar_real(self.enlace.snapshot())
        publica = self._fuente == "PUBLICAR" or (self._fuente == "REAL" and self._conectado_real)  # sin enlace no se publica
        if publica and self.sync:
            self._acum_pub += dt
            if self._acum_pub >= PUBLICAR_CADA:
                self._acum_pub = 0.0
                tramo = self.sim.segmento if (self.corriendo and auto) else ""
                self.sync.publicar(NODO, {"modo": t.modo, "dir": t.direccion, "pwm": t.velocidad_pwm,
                                          "dist": t.distancia_frontal, "sens": [int(x) for x in t.sensores_linea],
                                          "sub": t.subestado, "qr": t.estacion_qr, "seg": tramo,
                                          "corriendo": self.corriendo or self._fuente == "REAL",
                                          "origen": "real" if self._fuente == "REAL" else "simulacion",
                                          "logi": self.twin.logistica if self._fuente == "REAL" else None}, self._error_publicar)
        v["modo"].setText("Automático" if t.modo == "AUTO" else "Manual")
        v["origen"].setText("Zeno REAL (esta PC)" if self._fuente == "REAL" else
                            ("Zeno REAL" if ver and self._origen_remoto == "real" else "Simulación"))
        v["dir"].setText(DIRECCIONES.get(t.direccion, t.direccion))
        v["pwm"].setText(f"{t.velocidad_pwm} %")
        v["dist"].setText(f"{t.distancia_frontal:.0f} cm")
        v["sub"].setText(t.subestado)
        v["qr"].setText(t.estacion_qr)
        tramo_vivo = self._seg_remoto if ver else (self.sim.segmento if (self.corriendo and auto) else "")
        v["seg"].setText(tramo_vivo or "—")
        v["sens"].setText(marcas(t.sensores_linea))
