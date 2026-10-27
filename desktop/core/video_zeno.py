"""Lector del video MJPEG de Zeno (http://IP:8080/stream.mjpg?t=TOKEN). Sin Qt ni OpenCV: urllib + hilo.
Reconecta solo; entrega cada JPEG por `al_cuadro(bytes)` y los cambios por `al_estado(texto)`. El token nunca se escribe en mensajes."""
import threading
import urllib.error
import urllib.request

MAX_CUADRO = 2_000_000       # bytes: un cuadro más grande se descarta (flujo corrupto u hostil)
MAX_BUFER = 4_000_000
ESPERA_REINTENTO_S = 2.0
TIMEOUT_S = 4.0


class ExtractorMJPEG:
    """Separa los cuadros JPEG de un flujo multipart/x-mixed-replace usando Content-Length. Tolera cortes en cualquier byte."""

    def __init__(self):
        self.buf = b""

    def alimentar(self, datos):
        self.buf += datos
        cuadros = []
        while True:
            i = self.buf.find(b"Content-Length:")
            if i < 0:
                self.buf = self.buf[-32:]            # solo se conserva la cola por si la cabecera quedó partida
                break
            fin_cab = self.buf.find(b"\r\n\r\n", i)
            if fin_cab < 0:
                self.buf = self.buf[i:]
                break
            try:
                n = int(self.buf[i + 15:self.buf.index(b"\r\n", i)].strip())
            except ValueError:
                self.buf = self.buf[fin_cab + 4:]
                continue
            if not 0 < n <= MAX_CUADRO:
                self.buf = self.buf[fin_cab + 4:]
                continue
            ini = fin_cab + 4
            if len(self.buf) < ini + n:
                self.buf = self.buf[i:]
                break
            cuadros.append(self.buf[ini:ini + n])
            self.buf = self.buf[ini + n:]
        if len(self.buf) > MAX_BUFER:
            self.buf = b""
        return cuadros


class LectorVideo:
    def __init__(self, url_fn, al_cuadro, al_estado=lambda t: None):
        self._url_fn, self._al_cuadro, self._al_estado = url_fn, al_cuadro, al_estado
        self._detener, self._hilo = threading.Event(), None

    def iniciar(self):
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()

    def detener(self):
        self._detener.set()

    def _bucle(self):
        while not self._detener.is_set():
            url = self._url_fn()           # se pide en cada intento: la IP puede haber cambiado de red
            if not url:
                self._al_estado("Sin dirección de Zeno todavía")
                self._detener.wait(ESPERA_REINTENTO_S)
                continue
            try:
                self._al_estado("Conectando al video…")
                with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
                    self._al_estado("En vivo")
                    ext = ExtractorMJPEG()
                    while not self._detener.is_set():
                        datos = r.read1(65536) if hasattr(r, "read1") else r.read(4096)
                        if not datos:
                            break
                        for c in ext.alimentar(datos):
                            self._al_cuadro(c)
                self._al_estado("Video cortado; reintentando…")
            except urllib.error.HTTPError as ex:
                if ex.code == 401:
                    self._al_estado("Zeno rechazó el token del video")
                    return
                self._al_estado("Zeno respondió %s; reintentando…" % ex.code)
            except Exception as ex:      # red caída, timeout, flujo roto: nunca tumba al HMI
                self._al_estado("Sin video (%s); reintentando…" % type(ex).__name__)
            self._detener.wait(ESPERA_REINTENTO_S)
