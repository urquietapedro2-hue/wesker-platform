"""Lo que la página de Zeno necesita para hablar con el robot real: destinos (del registro), token (cifrado) y el enlace."""
from core.secretos_local import SecretosError
from core.zeno_enlace import Candidato, EnlaceZeno


class AccesoReal:
    def __init__(self, obtener_endpoints, almacen, fabrica=EnlaceZeno):
        self._endpoints, self._almacen, self._fabrica = obtener_endpoints, almacen, fabrica

    def candidatos(self):
        return [Candidato(e.red, e.ip, e.puerto) for e in self._endpoints() if e.nodo == "ZENO-01"]

    def token(self):
        try:
            return self._almacen.token_zeno()
        except SecretosError:
            return ""

    def crear_enlace(self):
        return self._fabrica(self.candidatos(), self.token())
