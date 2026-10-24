"""Cámara USB, detección de QR y transmisión MJPEG. Basado en ZENO_V2, con tres mejoras: el QR se mantiene un instante
(evita falsas 'pérdidas' entre cuadros), el JPEG solo se codifica si alguien mira el video, y el video pide el token si hay uno."""
import hmac
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

from zeno import config

log = logging.getLogger("zeno.camara")
QR_PERSISTENCIA_S = 0.6


class Camara:
    def __init__(self, cv2=None, reloj=time.monotonic, nodo=config.NODO_ID, modo_fn=lambda: "AUTO"):
        if cv2 is None:
            import cv2  # solo existe en la Raspberry
        self.cv2, self._reloj, self._nodo, self._modo = cv2, reloj, nodo, modo_fn
        self.detector = cv2.QRCodeDetector()
        self._qr, self._qr_t = "NINGUNO", -1e9
        self._lock_qr, self._lock_frame = threading.Lock(), threading.Lock()
        self.running, self._frame, self.espectadores = False, None, 0

    @property
    def qr(self):
        with self._lock_qr:
            return self._qr if self._reloj() - self._qr_t <= QR_PERSISTENCIA_S else "NINGUNO"

    def frame(self):
        with self._lock_frame:
            return self._frame

    def _abrir(self):
        cv = self.cv2
        for idx in (0, 1):
            cap = cv.VideoCapture(idx, cv.CAP_V4L2)
            if cap.isOpened():
                cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*"MJPG"))
                cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv.CAP_PROP_FPS, 20)
                ok, _ = cap.read()
                if ok:
                    log.info("Cámara lista en /dev/video%d", idx)
                    return cap
                cap.release()
        log.warning("No se detectó cámara USB")
        return None

    def _leer_qr(self, frame):
        """Busca un QR en el cuadro. Solo cuentan los códigos de estaciones válidas; un cuadro defectuoso no mata la cámara."""
        try:
            dato, bbox, _ = self.detector.detectAndDecode(frame)
        except Exception:
            return "", None
        if dato in config.ESTACIONES_VALIDAS:
            with self._lock_qr:
                self._qr, self._qr_t = dato, self._reloj()
        return dato, bbox

    def start(self):
        if not self.running:
            self.running = True
            threading.Thread(target=self._bucle, daemon=True).start()

    def stop(self):
        self.running = False
        with self._lock_frame:
            self._frame = None

    def _bucle(self):
        cap = self._abrir()
        if cap is None:
            self.running = False
            return
        cv = self.cv2
        try:
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.02)
                    continue
                dato, bbox = self._leer_qr(frame)
                if self.espectadores > 0:  # codificar JPEG cuesta CPU: solo si alguien mira
                    self._publicar(frame, dato, bbox)
                time.sleep(0.035)
        finally:
            cap.release()

    def _publicar(self, frame, dato, bbox):
        cv = self.cv2
        try:
            if dato in config.ESTACIONES_VALIDAS and bbox is not None:
                p = bbox.astype(int).reshape(-1, 2)
                for i in range(len(p)):
                    cv.line(frame, tuple(p[i]), tuple(p[(i + 1) % len(p)]), (0, 255, 0), 2)
            cv.putText(frame, "%s [%s] | MODO: %s | QR: %s" % (self._nodo, time.strftime("%H:%M:%S"), self._modo(), self.qr),
                       (10, 30), cv.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 2)
            ok, jpeg = cv.imencode(".jpg", frame, [cv.IMWRITE_JPEG_QUALITY, 60])
            if ok:
                with self._lock_frame:
                    self._frame = jpeg.tobytes()
        except Exception:
            log.exception("Error al preparar el cuadro de video")


class _ServidorVideo(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def crear_servidor_video(camara, host, puerto, token=""):
    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def do_GET(self):
            url = urlparse(self.path)
            if url.path != "/stream.mjpg":
                self.send_response(404)
                self.end_headers()
                return
            enviado = (parse_qs(url.query).get("t") or [""])[0]
            if token and not hmac.compare_digest(enviado.encode("utf-8", "ignore"), token.encode("utf-8")):
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            camara.espectadores += 1
            camara.start()
            try:
                while True:
                    actual = camara.frame()
                    if actual is not None:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(actual))
                        self.wfile.write(actual)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.04)
            except Exception:
                pass
            finally:
                camara.espectadores = max(0, camara.espectadores - 1)

    return _ServidorVideo((host, puerto), Manejador)
