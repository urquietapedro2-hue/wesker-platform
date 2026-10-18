from PyQt5 import QtCore

from ui.common import run_async


class Sincronizador(QtCore.QObject):
    """Único punto que habla con la nube sobre los gemelos: consulta cada segundo y publica sin bloquear.
    Los hilos cuelgan de la ventana principal para que main.py los espere al cerrar."""
    estado = QtCore.pyqtSignal(str, object, str)  # nodo, estado, publicador
    senal = QtCore.pyqtSignal(str, str)           # nodo, publicador ('' = nadie publica)
    error = QtCore.pyqtSignal(str)                # mensaje cuando la nube no responde

    def __init__(self, shared, owner):
        super().__init__(owner)
        self.shared, self.owner = shared, owner
        self._leyendo, self._publicando = False, set()
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._consultar)
        self.timer.start(1000)

    def _consultar(self):
        if self._leyendo:
            return
        self._leyendo = True
        run_async(self.owner, self.shared.leer, self._leido, self._fallo)

    def _leido(self, resultado):
        self._leyendo = False
        for nodo, info in resultado.items():
            self.senal.emit(nodo, info["publicador"])
            if info["cambio"]:
                self.estado.emit(nodo, info["estado"], info["publicador"])

    def _fallo(self, msg):
        self._leyendo = False
        self.error.emit(msg)

    def publicar(self, nodo, estado, on_error=None):
        """Un envío por nodo a la vez; si el anterior no terminó, se omite este."""
        if nodo in self._publicando:
            return
        self._publicando.add(nodo)

        def ok(_v):
            self._publicando.discard(nodo)

        def fail(msg):
            self._publicando.discard(nodo)
            if on_error:
                on_error(msg)
        run_async(self.owner, self.shared.publicar, ok, fail, nodo, estado)

    def liberar(self, nodo):
        run_async(self.owner, self.shared.liberar, lambda _r: None, None, nodo)

    def detener(self):
        self.timer.stop()
