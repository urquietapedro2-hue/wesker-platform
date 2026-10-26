"""Servidor de control y telemetría de Zeno (TCP). Mismo protocolo que V2 más: autenticación opcional, vigilancia de enlace,
comandos partidos entre paquetes, reemplazo de conexiones muertas y ninguna desconexión puede tumbar el servidor."""
import hmac
import logging
import socket
import threading
import time

from zeno import __version__, config
from zeno.logica import VigilanteEnlace, formatear_telemetria, parsear_comando

log = logging.getLogger("zeno.servidor")


class ServidorControl:
    def __init__(self, hw, nav, camara, token="", host=config.HOST, puerto=config.PUERTO_CONTROL,
                 vigilancia_s=config.VIGILANCIA_MANUAL_S, reloj=time.monotonic, auth_s=config.TIEMPO_AUTENTICACION_S):
        self.hw, self.nav, self.camara, self.token = hw, nav, camara, token
        self._reloj, self._auth_s = reloj, auth_s
        self.vigilante = VigilanteEnlace(vigilancia_s, reloj)
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((host, puerto))
        self._srv.listen(4)
        self._srv.settimeout(0.5)
        self.puerto = self._srv.getsockname()[1]  # permite puerto 0 en las pruebas
        self._cliente, self._lock = None, threading.Lock()
        self._envio = threading.Lock()
        self._parado_por_silencio = False
        self._detener = threading.Event()

    # ------------------------------------------------------------ ciclo de vida
    def iniciar(self):
        for destino in (self._aceptar, self._telemetria, self._vigilancia):
            threading.Thread(target=destino, daemon=True).start()
        if not self.token:
            log.warning("SIN AUTENTICACION: cualquiera en la red puede mover a Zeno. Crea un token: python3 -m zeno --generar-token")

    def detener(self):
        self._detener.set()
        with self._lock:
            c, self._cliente = self._cliente, None
        self._cerrar(c)
        self._cerrar(self._srv)

    @staticmethod
    def _cerrar(sock):
        try:
            sock.close()
        except Exception:
            pass

    # ------------------------------------------------------------ conexiones
    def _aceptar(self):
        while not self._detener.is_set():
            try:
                conn, addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(target=self._atender, args=(conn, addr), daemon=True).start()

    def _registrar(self, conn):
        """Esta conexión pasa a ser el HMI activo; si había otra (posiblemente muerta), se cierra."""
        with self._lock:
            anterior, self._cliente = self._cliente, conn
        if anterior is not None and anterior is not conn:
            log.info("Nueva conexión: se reemplaza la anterior")
            self._cerrar(anterior)
        self.vigilante.latido()
        self._parado_por_silencio = False

    def _soltar(self, conn):
        with self._lock:
            era_activa = self._cliente is conn
            if era_activa:
                self._cliente = None
        self._cerrar(conn)
        if era_activa:  # solo la conexión activa provoca el paro preventivo
            self.hw.traccion("S", 0)
            log.info("HMI desconectado: paro preventivo aplicado")

    def _atender(self, conn, addr):
        conn.settimeout(1.0)
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            for opcion, valor in (("TCP_KEEPIDLE", 5), ("TCP_KEEPINTVL", 2), ("TCP_KEEPCNT", 3)):
                if hasattr(socket, opcion):
                    conn.setsockopt(socket.IPPROTO_TCP, getattr(socket, opcion), valor)
        except OSError:
            pass
        autenticado, buffer, t0 = not self.token, b"", self._reloj()
        if autenticado:
            self._registrar(conn)
            log.info("HMI conectado desde %s", addr[0])
        try:
            while not self._detener.is_set():
                try:
                    datos = conn.recv(1024)
                except socket.timeout:
                    if not autenticado and self._reloj() - t0 > self._auth_s:
                        log.warning("Conexión de %s cerrada: no se autenticó a tiempo", addr[0])
                        return
                    continue
                if not datos:
                    return
                buffer += datos
                if len(buffer) > config.MAX_LINEA and b"\n" not in buffer:
                    log.warning("Conexión de %s cerrada: línea demasiado larga", addr[0])
                    return
                while b"\n" in buffer:
                    linea, buffer = buffer.split(b"\n", 1)
                    if len(linea) > config.MAX_LINEA:
                        return
                    estado = self._procesar(conn, addr, linea.decode("utf-8", "ignore"), autenticado)
                    if estado is None:
                        return
                    autenticado = estado
        except (ConnectionError, OSError):
            log.info("Conexión de %s perdida", addr[0])
        except Exception:  # nada de lo que mande un cliente puede tumbar el servidor
            log.exception("Error inesperado atendiendo a %s", addr[0])
        finally:
            self._soltar(conn)

    # ------------------------------------------------------------ comandos
    def _enviar(self, conn, texto):
        try:
            with self._envio:
                conn.sendall(texto.encode("utf-8"))
            return True
        except Exception:
            self._soltar(conn)
            return False

    def _procesar(self, conn, addr, linea, autenticado):
        """Devuelve el nuevo estado de autenticación, o None para cerrar la conexión."""
        cmd = parsear_comando(linea)
        if not autenticado:
            if cmd.tipo == "AUTH" and hmac.compare_digest(cmd.a.encode("utf-8", "ignore"), self.token.encode("utf-8")):
                self._registrar(conn)
                log.info("HMI autenticado desde %s", addr[0])
                return True
            log.warning("Autenticación fallida desde %s", addr[0])
            self._enviar(conn, "ERR,AUTH\n")
            return None
        if cmd.tipo == "AUTH":
            return True
        self.vigilante.latido()
        self._parado_por_silencio = False
        t = cmd.tipo
        if t == "PING":
            self._enviar(conn, "PONG\n")
        elif t == "HELLO":
            self._enviar(conn, "HELLO:%s,%s,%s,%s\n" % (config.NODO_ID, __version__, self.nav.logica, self.nav.modo))
        elif t == "MODE":
            self.nav.cambiar_modo(cmd.a)
            self.hw.traccion("S", 0)
            log.info("Modo: %s", cmd.a)
        elif t == "RESUME":
            if self.nav.reanudar():
                log.info("Reanudación manual de marcha")
        elif t == "DIAG_PULSE":
            self.hw.pulso(cmd.a, cmd.b, cmd.c)
        elif t == "CAM_ON":
            self.camara.start()
        elif t == "CAM_OFF":
            self.camara.stop()
        elif t == "MOVER":
            if self.nav.modo == "MANUAL":
                self.hw.traccion(cmd.a, cmd.b)
        elif t == "INVALIDO":
            log.warning("Comando rechazado de %s: %s", addr[0], cmd.a)
        return True

    # ------------------------------------------------------------ hilos de apoyo
    def _telemetria(self):
        while not self._detener.is_set():
            with self._lock:
                conn = self._cliente
            if conn is not None:
                direccion = "ESTACION" if self.nav.sub == "ESTACION_DESCARGA" else self.hw.estado_movimiento
                self._enviar(conn, formatear_telemetria(direccion, self.hw.velocidad_actual, config.DISTANCIA_SIN_SENSOR,
                                                        self.hw.sensores, self.nav.sub, self.camara.qr))
            time.sleep(0.05)

    def _vigilancia(self):
        """En MANUAL, si el HMI deja de dar señales (ni órdenes ni PING) se frena: protege de un enlace muerto."""
        while not self._detener.is_set():
            with self._lock:
                hay_cliente = self._cliente is not None
            if hay_cliente and self.nav.modo == "MANUAL" and self.vigilante.vencido() and not self._parado_por_silencio:
                self.hw.parar_duro()
                self._parado_por_silencio = True
                log.warning("Sin señales del HMI en modo MANUAL: PARO DE SEGURIDAD")
            time.sleep(0.1)
