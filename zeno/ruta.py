"""Máquina de estados de la ruta de Zeno (3 estaciones, 2 rampas). Sin GPIO ni red: recibe sensores, QR y reloj, y devuelve la
orden de tracción; las rampas y el pan de la cámara se manejan a través de objetos inyectados. Todo valor ajustable sale de la calibración.

Ciclo:  ST1_CARGA_R1 -> ST1_INDEXANDO -> ST1_CARGA_R2 -> SALIENDO -> SEGUIMIENTO
        -> (5 sensores activos durante debounce_interseccion_ms) -> ESCANEANDO_QR
        -> QR ESTACION_2: DESCARGANDO rampa 1 | QR ESTACION_3: DESCARGANDO rampa 2 | QR ESTACION_1: vuelve a ST1_CARGA_R1
        -> (t_espera_descarga_s, rampa cerrada) -> SALIENDO -> SEGUIMIENTO
Seguridad: no sale de la Estación 1 sin la confirmación de ambas cargas (solo avisa con alarma, o el operador usa ABORTAR);
si no lee el QR de una intersección se queda parado con alarma; cualquier orden fuera de su fase se ignora."""
import logging
import threading
import time
from collections import namedtuple

from zeno import config
from zeno.logica import LOGICAS

log = logging.getLogger("zeno.ruta")
Orden = namedtuple("Orden", "cmd vel camara mensaje")   # cmd None = no cambiar; camara: None nada, True encender, False apagar
SIN_CAMBIO = Orden(None, 0, None, "")
ST1_R1, ST1_IDX, ST1_R2, SEGUIMIENTO, ESCANEO, DESCARGA, SALIENDO, MANUAL = (
    "ST1_CARGA_R1", "ST1_INDEXANDO", "ST1_CARGA_R2", "SEGUIMIENTO", "ESCANEANDO_QR", "DESCARGANDO", "SALIENDO", "MANUAL")
FASES = (ST1_R1, ST1_IDX, ST1_R2, SEGUIMIENTO, ESCANEO, DESCARGA, SALIENDO, MANUAL)
RAMPA_DE_QR = {"ESTACION_2": 1, "ESTACION_3": 2}


class Ruta:
    def __init__(self, cal, rampas, pan, logica="V2", reloj=time.monotonic, fase_inicial=ST1_R1):
        if logica not in LOGICAS:
            raise ValueError("lógica de navegación desconocida: %s" % logica)
        self.cal, self.rampas, self.pan, self._reloj = cal, rampas, pan, reloj
        self._decidir, self.logica = LOGICAS[logica], logica
        self._lock = threading.Lock()
        if fase_inicial not in FASES:
            raise ValueError("fase inicial desconocida: %s" % fase_inicial)
        self.modo, self.fase = "AUTO", fase_inicial   # arranca en la Estación 1; fase_inicial solo se usa en pruebas
        self.estacion, self.alarma = "NINGUNA", ""
        self.carga = {1: False, 2: False}
        self._t, self._t_inter, self._ahora, self._rampa = reloj(), None, reloj(), 0
        self._ok_carga, self._abortar = {1: False, 2: False}, False

    # ---------------- compatibilidad con el servidor / HMI ----------------
    @property
    def sub(self):
        """Subestado del formato TELEM de siempre: la fase fina viaja en la línea RUTA."""
        return "SEGUIMIENTO" if self.fase in (SEGUIMIENTO, SALIENDO, MANUAL) else "ESTACION_DESCARGA"

    def cambiar_modo(self, modo):
        with self._lock:
            self.modo = modo
            self._abortar = False
            self._ok_carga = {1: False, 2: False}
            if modo == "AUTO":     # se asume que Zeno está parado en la Estación 1 esperando la carga
                self._entrar(ST1_R1, self._reloj())
            else:
                self.fase, self.alarma, self._t_inter = MANUAL, "", None
                self.rampas.olvidar()      # en manual las rampas no se reposicionan solas (se prueban con CAL_PROBAR)

    # ---------------- eventos externos (hilo del servidor) ----------------
    def carga_rampa(self, n):
        """La rampa n está cargada. Solo vale en su turno (primero la 1, luego la 2): una señal fuera de orden se ignora."""
        with self._lock:
            if self.modo == "AUTO" and self.fase == {1: ST1_R1, 2: ST1_R2}.get(n):
                self._ok_carga[n] = True
                return True
        return False

    def abortar(self):
        """Abandona la fase actual y sigue la línea: salta la carga, la descarga o la lectura de QR. No actúa en seguimiento."""
        with self._lock:
            if self.modo == "AUTO" and self.fase not in (SEGUIMIENTO, SALIENDO, MANUAL):
                self._abortar = True
                return True
        return False

    def estado(self):
        with self._lock:
            restante = 0.0
            if self.fase == DESCARGA:
                restante = max(0.0, self.cal["t_espera_descarga_s"] - (self._ahora - self._t))
            return {"fase": self.fase, "estacion": self.estacion, "carga_r1": self.carga[1], "carga_r2": self.carga[2],
                    "alarma": self.alarma or "NINGUNA", "restante_s": restante}

    # ---------------- ciclo ----------------
    def _entrar(self, fase, ahora):
        """Acciones de entrada de cada fase (se llama con el cerrojo tomado)."""
        self.fase, self._t, self.alarma, self._t_inter = fase, ahora, "", None
        if fase == ST1_R1:
            self.rampas.cerrar_todas()      # bloqueo: la carga queda retenida mientras se llena
            self.pan.centrar()
        elif fase == ESCANEO:
            self.pan.barrido()
        elif fase == DESCARGA:
            self.pan.centrar()
            self.rampas.abrir(self._rampa)
        log.info("Fase -> %s", fase)

    def _salir(self, ahora, mensaje):
        self._entrar(SALIENDO, ahora)
        return Orden("F", self.cal["vel_auto_max"], False, mensaje)

    def paso(self, sensores, qr, ahora=None):
        ahora = self._reloj() if ahora is None else ahora
        with self._lock:
            self._ahora = ahora
            if self.modo != "AUTO":
                return SIN_CAMBIO
            if self._abortar:
                self._abortar = False
                if self.fase == DESCARGA:
                    self.rampas.cerrar(self._rampa)
                return self._salir(ahora, "Fase abortada por el operador: se sigue la línea")
            cal, f, espera = self.cal, self.fase, ahora - self._t
            if f == ST1_R1 or f == ST1_R2:
                n = 1 if f == ST1_R1 else 2
                if self._ok_carga[n]:
                    self._ok_carga[n], self.carga[n] = False, True
                    if n == 1:
                        self._entrar(ST1_IDX, ahora)
                        return Orden("F", cal["vel_indexacion"], None, "Rampa 1 cargada: avance de indexación")
                    return self._salir(ahora, "Rampa 2 cargada: inicia el seguimiento de línea")
                if espera > cal["t_carga_max_s"] and not self.alarma:
                    self.alarma = "TIMEOUT_CARGA"
                    log.error("La rampa %d no se cargó a tiempo: Zeno sigue esperando", n)
                return Orden("S", 0, None, "")
            if f == ST1_IDX:
                if espera * 1000.0 >= cal["t_indexacion_ms"]:
                    self._entrar(ST1_R2, ahora)
                    return Orden("S", 0, None, "Alineado: esperando la carga de la rampa 2")
                return Orden("F", cal["vel_indexacion"], None, "")
            if f == SALIENDO:
                if espera >= cal["t_salida_s"]:
                    self._entrar(SEGUIMIENTO, ahora)
                    return SIN_CAMBIO
                return Orden("F", cal["vel_auto_max"], None, "")
            if f == ESCANEO:
                return self._escanear(qr, ahora, espera)
            if f == DESCARGA:
                if espera >= cal["t_espera_descarga_s"]:
                    self.rampas.cerrar(self._rampa)
                    self.carga[self._rampa] = False
                    return self._salir(ahora, "Descarga terminada: se sigue la línea")
                return Orden("S", 0, None, "")
            return self._seguir(sensores, ahora)   # SEGUIMIENTO

    def _seguir(self, sensores, ahora):
        if all(sensores):                                      # candidata a intersección: debe durar el filtro completo
            if self._t_inter is None:
                self._t_inter = ahora
            if (ahora - self._t_inter) * 1000.0 >= self.cal["debounce_interseccion_ms"]:
                self._entrar(ESCANEO, ahora)
                return Orden("S", 0, True, "Intersección: se detiene y busca el QR")
            return SIN_CAMBIO                                  # mientras se confirma, mantiene lo que hacía
        self._t_inter = None
        d = self._decidir(sensores)
        return SIN_CAMBIO if d is None else Orden(d[0], min(d[1], self.cal["vel_auto_max"]), None, "")

    def _escanear(self, qr, ahora, espera):
        if qr in config.ESTACIONES_VALIDAS:
            self.estacion = qr
            if qr == "ESTACION_1":
                self._entrar(ST1_R1, ahora)
                return Orden("S", 0, False, "Estación 1: espera la carga de la rampa 1")
            self._rampa = RAMPA_DE_QR[qr]
            self._entrar(DESCARGA, ahora)
            return Orden("S", 0, False, "%s: se abre la rampa %d" % (qr, self._rampa))
        if espera > self.cal["t_escaneo_qr_s"] and not self.alarma:
            self.alarma = "QR_NO_LEIDO"
            log.error("No se leyó ningún QR en la intersección: Zeno sigue parado buscando")
        return Orden("S", 0, None, "")
