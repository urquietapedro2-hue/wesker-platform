"""Transmisión MJPEG de Zeno (puerto 8080). Ligero y concurrente: un hilo por espectador, solo se envían cuadros nuevos,
la cámara solo codifica JPEG si alguien mira y el acceso pide el token (?t=...) cuando hay uno.
Uso independiente:  python3 -m zeno.camara_stream   (prueba de video sin navegación; no usar a la vez que `python3 -m zeno`)."""
import hmac
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

from zeno import config

log = logging.getLogger("zeno.stream")


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
                ultimo, t_envio = None, 0.0
                while True:
                    actual = camara.frame()
                    # cuadro nuevo, o repetir el último cada 1 s: así se detecta pronto al espectador que se fue
                    if actual is not None and (actual is not ultimo or time.monotonic() - t_envio > 1.0):
                        ultimo, t_envio = actual, time.monotonic()
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(actual))
                        self.wfile.write(actual)
                        self.wfile.write(b"\r\n")
                    time.sleep(0.04)
            except Exception:
                pass
            finally:
                camara.espectadores = max(0, camara.espectadores - 1)

    return _ServidorVideo((host, puerto), Manejador)


def main():
    from zeno.camara import Camara
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    token = config.cargar_token()
    camara = Camara()
    srv = crear_servidor_video(camara, config.HOST, config.PUERTO_VIDEO, token)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log.info("Video en :%d/stream.mjpg (token %s). Ctrl+C para salir.", config.PUERTO_VIDEO, "requerido" if token else "NO requerido")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        camara.stop()
        srv.shutdown()


if __name__ == "__main__":
    main()
