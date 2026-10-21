"""Corazón de V.E.R.A.: recibe eventos, decide qué decir, obtiene el audio (caché o proveedor) y lo reproduce.
Si el proveedor de voz falla, V.E.R.A. no se cae: se pone en pausa y sigue registrando."""
import logging
import queue
import threading
import time

from vera.cache import CacheAudio
from vera.dialogo import redactar
from vera.eventos import Evento
from vera.voz.base import VozError, VozNoDisponible

log = logging.getLogger("vera")
PAUSA_CORTA_S, PAUSA_LARGA_S, FALLOS_PARA_PAUSAR = 60.0, 600.0, 3


class Vera:
    def __init__(self, motor, reproductor, cache=None, enfriamiento_s=20.0, reloj=time.monotonic, max_cola=20):
        self.motor, self.reproductor, self.cache = motor, reproductor, cache
        self.enfriamiento_s, self._reloj = enfriamiento_s, reloj
        self._cola, self._ultimo_aviso = queue.Queue(maxsize=max_cola), {}
        self._fallos, self._pausado_hasta, self._ultimo_error = 0, 0.0, None
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def iniciar(self):
        self._hilo.start()

    def detener(self):
        self._cola.put(None)
        self._hilo.join(timeout=5)

    def encolar(self, evento: Evento) -> str:
        """'encolado' | 'enfriamiento' (mismo aviso hace poco) | 'cola_llena'. Nunca bloquea al que llama."""
        clave, ahora = (evento.codigo, evento.nodo), self._reloj()
        if ahora - self._ultimo_aviso.get(clave, -1e9) < self.enfriamiento_s:
            log.info("evento %s omitido: ya se anunció hace menos de %.0f s", evento.codigo, self.enfriamiento_s)
            return "enfriamiento"
        try:
            self._cola.put_nowait(evento)
        except queue.Full:
            log.warning("evento %s descartado: la cola está llena", evento.codigo)
            return "cola_llena"
        self._ultimo_aviso[clave] = ahora
        return "encolado"

    def estado(self) -> dict:
        return {"motor": self.motor.nombre, "cola": self._cola.qsize(), "ultimo_error": self._ultimo_error,
                "en_pausa": self._reloj() < self._pausado_hasta}

    def _bucle(self):
        while True:
            evento = self._cola.get()
            if evento is None:
                return
            try:
                self.procesar(evento)
            except Exception as ex:  # un evento defectuoso nunca debe matar el servicio
                self._ultimo_error = f"error interno ({type(ex).__name__})"
                log.error("error interno al procesar %s: %s", evento.codigo, type(ex).__name__)

    def procesar(self, evento: Evento) -> bool:
        """Síncrono (lo usa el hilo y las pruebas). True si se reprodujo algo. Cada paso queda en el registro."""
        texto = redactar(evento)
        if not texto:
            log.info("evento %s: no se anuncia", evento.codigo)
            return False
        log.info('evento %s -> "%s" (motor: %s)', evento.codigo, texto, self.motor.nombre)
        clave = CacheAudio.clave(self.motor.huella(), texto) if self.cache else None
        audio = self.cache.obtener(clave) if self.cache else None
        if audio is not None:
            log.info("voz tomada de la caché")
        else:
            restante = self._pausado_hasta - self._reloj()
            if restante > 0:
                log.warning("voz en pausa (%.0f s restantes) por el último error: %s", restante, self._ultimo_error)
                return False
            inicio = self._reloj()
            try:
                audio = self.motor.sintetizar(texto)
            except VozNoDisponible as ex:
                log.error("el proveedor de voz no puede atender: %s", ex)
                self._fallar(str(ex), PAUSA_LARGA_S, inmediato=True)
                return False
            except VozError as ex:
                log.error("fallo del proveedor de voz: %s", ex)
                self._fallar(str(ex), PAUSA_CORTA_S)
                return False
            self._fallos = 0
            if audio.datos:
                log.info("voz generada por %s (%d bytes, %.1f s)", self.motor.nombre, len(audio.datos), self._reloj() - inicio)
                if self.cache:
                    self.cache.guardar(clave, audio)
        if not audio.datos:
            log.warning("el motor «%s» no devolvió audio: V.E.R.A. no hablará. Ejecuta: python -m vera --diagnostico",
                        self.motor.nombre)
            return False
        self.reproductor.reproducir(audio)
        log.info("audio reproducido")
        return True

    def _fallar(self, mensaje, pausa, inmediato=False):
        self._fallos += 1
        self._ultimo_error = mensaje[:120]
        if inmediato or self._fallos >= FALLOS_PARA_PAUSAR:
            self._pausado_hasta, self._fallos = self._reloj() + pausa, 0
            log.error("voz en pausa durante %.0f s", pausa)
