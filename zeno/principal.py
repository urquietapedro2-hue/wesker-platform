"""Arranque de Zeno: une hardware, cámara, navegación y servidor, con supervisión del bucle de navegación."""
import argparse
import logging
import os
import secrets
import signal
import sys
import threading
import time

from zeno import __version__, config
from zeno.logica import Navegador

log = logging.getLogger("zeno")


class Aplicacion:
    def __init__(self, hw, camara, nav, servidor, reloj=time.monotonic, paso_s=0.012):
        self.hw, self.camara, self.nav, self.servidor = hw, camara, nav, servidor
        self._reloj, self._paso_s = reloj, paso_s
        self._latido, self._detener = reloj(), threading.Event()
        self.errores_navegacion = 0

    def iniciar(self):
        self.servidor.iniciar()
        threading.Thread(target=self._bucle_navegacion, daemon=True).start()
        threading.Thread(target=self._supervisor, daemon=True).start()

    def detener(self):
        self._detener.set()
        self.servidor.detener()

    def _aplicar(self, orden):
        if orden.mensaje:
            log.info(orden.mensaje)
        if orden.camara:
            self.camara.start()
        if orden.cmd is not None:
            self.hw.traccion(orden.cmd, orden.vel)

    def _bucle_navegacion(self):
        while not self._detener.is_set():
            try:
                self._aplicar(self.nav.paso(self.hw.leer_sensores(), self.camara.qr, self._reloj()))
                self._latido = self._reloj()
            except Exception:  # V2: un error aquí mataba el hilo y Zeno seguía con el último movimiento
                self.errores_navegacion += 1
                log.exception("Error en la navegación: PARO DE SEGURIDAD")
                try:
                    self.hw.parar_duro()
                except Exception:
                    pass
                time.sleep(0.2)
                self._latido = self._reloj()
            time.sleep(self._paso_s)

    def _supervisor(self):
        """Si el bucle de navegación se cuelga (no avanza), se frena el motor."""
        while not self._detener.is_set():
            if self._reloj() - self._latido > config.LATIDO_NAVEGACION_MAX_S:
                log.error("El bucle de navegación no responde: PARO DE SEGURIDAD")
                self.hw.parar_duro()
                self._latido = self._reloj()
            time.sleep(0.25)


def _generar_token():
    ruta = config.ruta_token()
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    if os.path.exists(ruta):
        print("Ya existe un token en %s. Bórralo antes si quieres generar otro." % ruta)
        return 1
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(secrets.token_urlsafe(24))
    os.chmod(ruta, 0o600)
    print("Token creado en %s (solo tu usuario puede leerlo).\nCópialo al HMI con:  cat %s" % (ruta, ruta))
    return 0


def _prueba_sensor(logica):
    """Tu script de prueba, integrado: muestra lo que Zeno decidiría con cada lectura, sin mover los motores."""
    from zeno.hardware import Hardware
    from zeno.logica import LOGICAS
    hw = Hardware()
    print("Prueba de sensores (lógica %s). Ctrl+C para salir." % logica)
    try:
        while True:
            s = hw.leer_sensores()
            d = LOGICAS[logica](s)
            print("[%d] [%d] [%d] [%d] [%d]  ==>  %s" % (*s, "BASE/ESTACIÓN -> DETENER" if all(s) else (d if d else "SIN REGLA: mantendría el último movimiento")))
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        hw.cerrar()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m zeno", description="Nodo AGV ZENO-01 de WESKER")
    ap.add_argument("--prueba-sensor", action="store_true", help="muestra las decisiones de la regleta sin mover motores")
    ap.add_argument("--generar-token", action="store_true", help="crea el token de acceso del HMI")
    ap.add_argument("--logica", choices=("V2", "NUEVA"), default=config.LOGICA_NAVEGACION)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    if args.generar_token:
        return _generar_token()
    if args.prueba_sensor:
        return _prueba_sensor(args.logica)

    from zeno.camara import Camara, crear_servidor_video
    from zeno.hardware import Hardware
    from zeno.servidor import ServidorControl
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # systemd detiene con SIGTERM: así corre el cierre ordenado
    token = config.cargar_token()
    hw, nav = Hardware(), Navegador(args.logica)
    camara = Camara(modo_fn=lambda: nav.modo)
    servidor = ServidorControl(hw, nav, camara, token)
    app = Aplicacion(hw, camara, nav, servidor)
    video = crear_servidor_video(camara, config.HOST, config.PUERTO_VIDEO, token)
    threading.Thread(target=video.serve_forever, daemon=True).start()
    log.info("ZENO-01 v%s | lógica %s | control :%d | video :%d | autenticación %s", __version__, args.logica,
             servidor.puerto, config.PUERTO_VIDEO, "ACTIVA" if token else "DESACTIVADA")
    app.iniciar()
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        log.info("Cerrando...")
    finally:
        app.detener()
        camara.stop()
        hw.cerrar()
    return 0
