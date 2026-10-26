from pathlib import Path

from PyQt5 import QtCore, QtWidgets

from core.auth import AuthError
from core.nodos import NODOS, PUERTOS_POR_DEFECTO, validar_endpoint
from core.secretos_local import SecretosError, destruir
from core.zeno_enlace import probar
from ui.panel import scroll


class NodosPage(QtWidgets.QWidget):
    """Registro de las IPs de los nodos (una por red) y token de Zeno cifrado. Solo el Admin edita las IPs."""

    def __init__(self, role, registro, almacen, ejecutar, evento, al_cambiar):
        super().__init__()
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setObjectName("pagina")
        self.registro, self.almacen, self.ejecutar, self.evento, self.al_cambiar = registro, almacen, ejecutar, evento, al_cambiar
        self.es_admin, self._lista = role == "ADMIN", []

        self.tabla = QtWidgets.QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Nodo", "Red", "Dirección IP", "Puerto"])
        self.tabla.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.tabla.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tabla.itemSelectionChanged.connect(self._seleccion)

        self.nodo = QtWidgets.QComboBox()
        for n in NODOS:
            self.nodo.addItem(n, n)
        self.red = QtWidgets.QLineEdit(placeholderText="Red (Casa, Equipo, Universidad…)")
        self.ip = QtWidgets.QLineEdit(placeholderText="Dirección IP del nodo en esa red")
        self.puerto = QtWidgets.QSpinBox()
        self.puerto.setRange(1, 65535)
        self.puerto.setValue(PUERTOS_POR_DEFECTO["ZENO-01"])
        self.nodo.currentIndexChanged.connect(lambda _i: self.puerto.setValue(PUERTOS_POR_DEFECTO.get(self.nodo.currentData(), 1)))
        self.btn_guardar = QtWidgets.QPushButton("Guardar dirección")
        self.btn_borrar = QtWidgets.QPushButton("Eliminar la seleccionada")
        self.btn_probar = QtWidgets.QPushButton("Probar conexión")
        self.btn_guardar.clicked.connect(self._guardar)
        self.btn_borrar.clicked.connect(self._borrar)
        self.btn_probar.clicked.connect(self._probar)
        caja = QtWidgets.QGroupBox("Agregar o actualizar una dirección" + ("" if self.es_admin else " (solo Admin)"))
        form = QtWidgets.QFormLayout(caja)
        for etiqueta, w in (("Nodo", self.nodo), ("Red", self.red), ("IP", self.ip), ("Puerto", self.puerto)):
            form.addRow(etiqueta, w)
        form.addRow(self.btn_guardar)
        form.addRow(self.btn_borrar)
        for w in (self.nodo, self.red, self.ip, self.puerto, self.btn_guardar, self.btn_borrar):
            w.setEnabled(self.es_admin)
        form.addRow(self.btn_probar)

        self.token = QtWidgets.QLineEdit(placeholderText="Token de Zeno (no se muestra)")
        self.token.setEchoMode(QtWidgets.QLineEdit.Password)
        self.btn_token = QtWidgets.QPushButton("Guardar token cifrado")
        self.btn_importar = QtWidgets.QPushButton("Importar desde archivo…")
        self.btn_quitar = QtWidgets.QPushButton("Borrar token")
        self.lbl_token = QtWidgets.QLabel("")
        self.lbl_token.setObjectName("muted")
        self.lbl_token.setWordWrap(True)
        self.btn_token.clicked.connect(self._guardar_token)
        self.btn_importar.clicked.connect(self._importar)
        self.btn_quitar.clicked.connect(self._quitar_token)
        cajat = QtWidgets.QGroupBox("Token de Zeno (solo en esta PC, cifrado)")
        ft = QtWidgets.QVBoxLayout(cajat)
        for w in (self.token, self.btn_token, self.btn_importar, self.btn_quitar, self.lbl_token):
            ft.addWidget(w)

        self.estado = QtWidgets.QLabel("Cargando el registro…")
        self.estado.setObjectName("muted")
        self.estado.setWordWrap(True)
        panel = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(panel)
        for w in (caja, cajat, self.estado):
            pl.addWidget(w)
        pl.addStretch(1)
        lay = QtWidgets.QHBoxLayout(self)
        lay.addWidget(self.tabla, 1)
        lay.addWidget(scroll(panel, 380))
        self._estado_token()

    # ---------------- tabla ----------------
    def mostrar(self, lista):
        self._lista = list(lista)
        self.tabla.setRowCount(len(lista))
        for i, e in enumerate(lista):
            for j, v in enumerate((e.nodo, e.red, e.ip, str(e.puerto))):
                self.tabla.setItem(i, j, QtWidgets.QTableWidgetItem(v))
        self._msg(f"{len(lista)} dirección(es) registrada(s).", "#94a3b8")

    def _seleccion(self):
        filas = self.tabla.selectionModel().selectedRows() if self.tabla.selectionModel() else []
        if filas and filas[0].row() < len(self._lista):
            e = self._lista[filas[0].row()]
            self.nodo.setCurrentIndex(max(0, self.nodo.findData(e.nodo)))
            self.red.setText(e.red)
            self.ip.setText(e.ip)
            self.puerto.setValue(e.puerto)

    def _msg(self, texto, color):
        self.estado.setText(texto)
        self.estado.setStyleSheet(f"color:{color}")

    def _fallo(self, texto):
        self._msg(texto, "#f87171")

    def _refrescar(self, *_):
        self.ejecutar(self.registro.listar, self._listado, self._fallo)

    def _listado(self, lista):
        self.mostrar(lista)
        self.al_cambiar(lista)

    # ---------------- direcciones ----------------
    def _datos_form(self):
        return validar_endpoint(self.nodo.currentData(), self.red.text(), self.ip.text(), self.puerto.value())

    def _guardar(self):
        try:
            e = self._datos_form()
        except AuthError as ex:
            return self._fallo(str(ex))
        self._msg("Guardando…", "#94a3b8")
        self.ejecutar(self.registro.guardar, lambda _r: (self.evento("info", f"Dirección de {e.nodo} guardada para la red «{e.red}»"),
                                                         self._refrescar()), self._fallo, e.nodo, e.red, e.ip, e.puerto)

    def _borrar(self):
        filas = self.tabla.selectionModel().selectedRows() if self.tabla.selectionModel() else []
        if not filas or filas[0].row() >= len(self._lista):
            return self._fallo("Selecciona primero una fila de la tabla.")
        e = self._lista[filas[0].row()]
        if QtWidgets.QMessageBox.question(self, "Eliminar", f"¿Eliminar la dirección de {e.nodo} en la red «{e.red}»?") != QtWidgets.QMessageBox.Yes:
            return
        self.ejecutar(self.registro.borrar, lambda _r: (self.evento("warn", f"Dirección de {e.nodo} eliminada de la red «{e.red}»"),
                                                        self._refrescar()), self._fallo, e.nodo, e.red)

    def _probar(self):
        try:
            e = self._datos_form()
            token = self.almacen.token_zeno()
        except (AuthError, SecretosError) as ex:
            return self._fallo(str(ex))
        if e.nodo != "ZENO-01":
            return self._fallo("La prueba de conexión solo existe para Zeno por ahora.")
        self._msg("Probando conexión…", "#94a3b8")
        self.ejecutar(probar, lambda r: self._msg(r[1], "#4ade80" if r[0] else "#f87171"), self._fallo, e.ip, e.puerto, token)

    # ---------------- token ----------------
    def _estado_token(self):
        self.lbl_token.setText("Token de Zeno: " + ("guardado (cifrado en esta PC)." if self.almacen.hay_token() else "no hay ninguno guardado."))

    def _guardar_token(self):
        try:
            self.almacen.guardar_token_zeno(self.token.text())
        except SecretosError as ex:
            return self._fallo(str(ex))
        self.token.clear()
        self._estado_token()
        self.evento("info", "Token de Zeno guardado cifrado")

    def _importar(self):
        ruta, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Archivo con el token de Zeno")
        if not ruta:
            return
        try:
            if Path(ruta).stat().st_size > 4096:
                return self._fallo("Ese archivo es demasiado grande para ser un token.")
            self.almacen.guardar_token_zeno(Path(ruta).read_text(encoding="utf-8").strip())
        except (OSError, UnicodeDecodeError, SecretosError) as ex:
            return self._fallo(str(ex) if isinstance(ex, SecretosError) else "No se pudo leer el archivo.")
        self._estado_token()
        self.evento("info", "Token de Zeno importado y cifrado")
        if QtWidgets.QMessageBox.question(self, "Borrar el original", "El token ya está guardado cifrado.\n¿Sobrescribir y borrar el archivo original? "
                                          "(recomendado)") == QtWidgets.QMessageBox.Yes:
            try:
                destruir(ruta)
                self._msg("Token importado y archivo original borrado.", "#4ade80")
            except OSError:
                self._fallo("No se pudo borrar el archivo original: bórralo tú.")

    def _quitar_token(self):
        try:
            self.almacen.borrar_token_zeno()
        except SecretosError as ex:
            return self._fallo(str(ex))
        self._estado_token()
        self.evento("warn", "Token de Zeno borrado de esta PC")
