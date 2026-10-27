"""Visor de la cámara de Zeno (ventana flotante). Se abre sola cuando Zeno llega a una estación y se puede abrir a mano."""
from PyQt5 import QtCore, QtGui, QtWidgets

from core.video_zeno import LectorVideo


class VisorCamara(QtWidgets.QDialog):
    _cuadro = QtCore.pyqtSignal(bytes)       # los hilos de red no tocan widgets: todo pasa por señales
    _estado = QtCore.pyqtSignal(str)

    def __init__(self, url_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cámara de Zeno")
        self.setModal(False)
        self.resize(660, 540)
        self._url_fn, self._lector, self.cuadros = url_fn, None, 0
        self.titulo = QtWidgets.QLabel("")
        self.titulo.setObjectName("muted")
        self.imagen = QtWidgets.QLabel("Sin imagen")
        self.imagen.setAlignment(QtCore.Qt.AlignCenter)
        self.imagen.setMinimumSize(640, 480)
        self.imagen.setObjectName("camara")
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.titulo)
        lay.addWidget(self.imagen, 1)
        self._cuadro.connect(self._mostrar)
        self._estado.connect(self.titulo.setText)

    def abrir(self, motivo=""):
        if motivo:
            self.setWindowTitle("Cámara de Zeno · " + motivo)
        if self._lector is None:
            self._lector = LectorVideo(self._url_fn, self._cuadro.emit, self._estado.emit)
            self._lector.iniciar()
        self.show()
        self.raise_()

    def cerrar_video(self):
        lector, self._lector = self._lector, None
        if lector is not None:
            lector.detener()

    def _mostrar(self, jpeg):
        pm = QtGui.QPixmap()
        if pm.loadFromData(jpeg, "JPG"):
            self.cuadros += 1
            self.imagen.setPixmap(pm.scaled(self.imagen.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation))

    def closeEvent(self, e):
        self.cerrar_video()
        super().closeEvent(e)
