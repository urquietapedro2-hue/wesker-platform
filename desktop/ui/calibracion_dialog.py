"""Panel de calibración de Zeno (ventana flotante). Se construye solo con el esquema que manda Zeno: grupos -> pestañas,
parámetros -> controles. Los cambios salen en vivo (CAL_SET, validados por Zeno); «Guardar» los escribe en el JSON de Zeno."""
import time

from PyQt5 import QtCore, QtWidgets

from core.calibracion_hmi import Acumulador, agrupar, cmd_probar
from core.calibracion_hmi import cmd_set  # noqa: F401  (se re-exporta para quien lo necesite)


class CalibracionDialog(QtWidgets.QDialog):
    def __init__(self, enlace_fn, modo_fn, puede_editar, auditar, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibración de Zeno")
        self.setModal(False)
        self.resize(560, 520)
        self._enlace_fn, self._modo_fn, self._puede, self._auditar = enlace_fn, modo_fn, puede_editar, auditar
        self._esquema, self._ctl, self._version, self._err_visto = None, {}, -1, 0
        self._acum = Acumulador()
        self.tabs = QtWidgets.QTabWidget()
        self.estado = QtWidgets.QLabel("Esperando el esquema de Zeno…")
        self.estado.setWordWrap(True)
        self.estado.setObjectName("muted")
        self.aviso = QtWidgets.QLabel("")
        self.aviso.setWordWrap(True)
        self.aviso.setObjectName("alerta")
        self.btn_guardar = QtWidgets.QPushButton("Guardar en Zeno")
        self.btn_descartar = QtWidgets.QPushButton("Descartar cambios")
        self.btn_fabrica = QtWidgets.QPushButton("Valores de fábrica")
        for b in (self.btn_guardar, self.btn_descartar, self.btn_fabrica):
            b.setEnabled(False)
        self.btn_guardar.clicked.connect(lambda: self._orden("CAL_GUARDAR", "CAL_GUARDAR"))
        self.btn_descartar.clicked.connect(lambda: self._orden("CAL_RESTAURAR", "CAL_RESTAURAR"))
        self.btn_fabrica.clicked.connect(self._fabrica)
        fila = QtWidgets.QHBoxLayout()
        for b in (self.btn_guardar, self.btn_descartar, self.btn_fabrica):
            fila.addWidget(b)
        lay = QtWidgets.QVBoxLayout(self)
        for w in (self.estado, self.tabs, self.aviso):
            lay.addWidget(w)
        lay.addLayout(fila)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(150)

    # ---------------- envío ----------------
    def _enviar(self, comando):
        enlace = self._enlace_fn()
        return enlace is not None and enlace.enviar(comando)

    def _orden(self, comando, accion):
        salio = self._enviar(comando)
        self._auditar("ZENO_CAL_" + accion.replace("CAL_", ""), {"enviada": salio})
        if not salio:
            self.aviso.setText("Sin enlace con Zeno: no se envió.")

    def _fabrica(self):
        if QtWidgets.QMessageBox.question(self, "Calibración", "¿Volver todos los parámetros a los valores de fábrica?\n"
                                          "(No se guardan hasta que pulses «Guardar en Zeno».)") == QtWidgets.QMessageBox.Yes:
            self._orden("CAL_DEFECTO", "DEFECTO")

    def _cambio(self, p, valor):
        if self._puede:
            self._acum.editar(p, valor, time.monotonic())

    def _probar(self, p):
        cmd = cmd_probar(p, self._valor(p))
        if cmd and not self._enviar(cmd):
            self.aviso.setText("Sin enlace con Zeno: no se envió.")

    # ---------------- construcción ----------------
    def _construir(self, esquema):
        self.tabs.clear()
        self._ctl = {}
        for grupo, params in agrupar(esquema):
            pag = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(pag)
            for p in params:
                if p["tipo"] == "bool":
                    w = QtWidgets.QCheckBox()
                    w.toggled.connect(lambda v, p=p: self._cambio(p, v))
                else:
                    w = QtWidgets.QSpinBox() if p["tipo"] == "int" else QtWidgets.QDoubleSpinBox()
                    w.setRange(p["min"], p["max"])
                    if p["tipo"] == "float":
                        w.setDecimals(2)
                        w.setSingleStep(1.0 if p["max"] > 10 else 0.05)
                    w.setSuffix(" " + p["unidad"] if p["unidad"] else "")
                    w.valueChanged.connect(lambda v, p=p: self._cambio(p, v))
                w.setEnabled(self._puede)
                w.setToolTip(p["ayuda"])
                self._ctl[p["clave"]] = (p, w)
                if p["probar"]:
                    caja = QtWidgets.QHBoxLayout()
                    caja.addWidget(w, 1)
                    b = QtWidgets.QPushButton("Probar")
                    b.setToolTip("Mueve el servo a este ángulo (solo con Zeno en modo Manual)")
                    b.clicked.connect(lambda _c, p=p: self._probar(p))
                    b.setEnabled(self._puede)
                    caja.addWidget(b)
                    form.addRow(p["etiqueta"], caja)
                else:
                    form.addRow(p["etiqueta"], w)
            self.tabs.addTab(pag, grupo)

    def _valor(self, p):
        w = self._ctl[p["clave"]][1]
        return w.isChecked() if p["tipo"] == "bool" else w.value()

    def _aplicar_valores(self, valores):
        """Pone en pantalla lo que Zeno tiene, sin pisar lo que el usuario está tocando en este momento."""
        for clave, (p, w) in self._ctl.items():
            if clave not in valores or w.hasFocus() or self._acum.pendiente(clave):
                continue
            w.blockSignals(True)
            if p["tipo"] == "bool":
                w.setChecked(bool(valores[clave]))
            else:
                w.setValue(valores[clave])
            w.blockSignals(False)

    # ---------------- sincronía ----------------
    def _tick(self):
        enlace = self._enlace_fn()
        if enlace is None:
            self.estado.setText("Sin enlace con Zeno real.")
            return
        snap = enlace.snapshot()
        if snap["cal_esquema"] and self._esquema != snap["cal_esquema"]:
            self._esquema = snap["cal_esquema"]
            self._construir(self._esquema)
            self._version = -1
        for comando in self._acum.listos(time.monotonic()):
            if self._enviar(comando):
                self._auditar("ZENO_CAL_SET", {"comando": comando})
        cal = snap["cal"]
        if cal and cal["version"] != self._version and self._esquema:
            self._version = cal["version"]
            self._aplicar_valores(cal["valores"])
        if cal:
            self.estado.setText(("Hay cambios sin guardar en Zeno. " if cal["sin_guardar"] else "Calibración guardada. ") +
                                ("Edición habilitada." if self._puede else "Solo lectura (tu rol no calibra)."))
        n, msg = snap["cal_error"]
        if n != self._err_visto:
            self._err_visto = n
            self.aviso.setText("Zeno rechazó el cambio: " + msg)
        ok = bool(self._puede and cal)          # sin los valores reales de Zeno no se deja editar (se mandaría el mínimo)
        for b in (self.btn_guardar, self.btn_descartar, self.btn_fabrica):
            b.setEnabled(ok)
        for _p, w in self._ctl.values():
            w.setEnabled(ok)

    def closeEvent(self, e):
        self._timer.stop()
        super().closeEvent(e)
