"""Enlace del HMI con el nodo Zeno por TCP. Sin Qt: hilo propio, reconexión con espera creciente y datos consultables.
Protocolo de Zeno: ver zeno/README.md. El HMI nunca guarda la IP: recibe candidatos (red, ip, puerto) del registro de nodos."""
import socket
import threading
import time
from collections import namedtuple

Candidato = namedtuple("Candidato", "red ip puerto")
ESPERAS = (1.0, 2.0, 4.0, 8.0, 15.0)   # segundos entre intentos; crece y se queda en 15
SIN_DATOS_S = 3.0                      # sin recibir nada de Zeno durante este tiempo = enlace muerto
TIMEOUT_CONEXION_S = 1.5
DIRECCIONES = ("F", "B", "L", "R", "S", "FL", "FR", "BL", "BR", "ESTACION")


class Rechazado(Exception):
    """Zeno rechazó el token. Reintentar no sirve: hay que corregirlo."""


def parsear_telem(linea):
    """`TELEM:dir,vel,dist,s1..s5,sub,qr` -> dict listo para sanear_zeno(), o None si no es válida. Nunca lanza excepciones."""
    if not linea.startswith("TELEM:"):
        return None
    p = linea[6:].strip().split(",")
    if len(p) != 10:
        return None
    try:
        vel, dist, sens = int(p[1]), float(p[2]), [int(x) for x in p[3:8]]
    except ValueError:
        return None
    if p[0] not in DIRECCIONES or not 0 <= vel <= 100 or not 0.0 <= dist <= 500.0 or any(x not in (0, 1) for x in sens):
        return None
    return {"dir": p[0], "pwm": vel, "dist": dist, "sens": sens, "sub": p[8][:30], "qr": p[9][:24]}


def _conectar(c, token, timeout=TIMEOUT_CONEXION_S):
    s = socket.create_connection((c.ip, c.puerto), timeout=timeout)
    s.settimeout(0.5)
    if token:
        s.sendall(("AUTH," + token + "\n").encode("utf-8"))
    s.sendall(b"HELLO\n")
    return s


def _lineas(buf, datos):
    buf += datos
    salida = []
    while b"\n" in buf:
        linea, buf = buf.split(b"\n", 1)
        salida.append(linea.decode("utf-8", "replace").strip())
    return buf, salida


def probar(ip, puerto, token="", timeout=2.5):
    """Prueba puntual (botón «Probar conexión»). Devuelve (ok, mensaje)."""
    try:
        s = _conectar(Candidato("", ip, puerto), token, timeout)
    except socket.timeout:
        return False, "Tiempo agotado: Zeno no responde en esa dirección."
    except OSError:
        return False, "No se pudo conectar. ¿Zeno está encendido, en la misma red y con esa IP?"
    fin, buf = time.monotonic() + timeout, b""
    try:
        while time.monotonic() < fin:
            try:
                datos = s.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not datos:
                break
            buf, lineas = _lineas(buf, datos)
            for linea in lineas:
                if linea.startswith("ERR,AUTH"):
                    return False, "Zeno rechazó el token. Revisa que sea el mismo que generó la Raspberry."
                if linea.startswith("HELLO:"):
                    return True, "Conectado. " + linea[6:].replace(",", " | ")
                if linea.startswith("TELEM:"):
                    return True, "Conectado (recibiendo telemetría)."
        return False, "Zeno aceptó la conexión pero no contestó (¿token faltante?)."
    finally:
        try:
            s.close()
        except OSError:
            pass


class EnlaceZeno:
    def __init__(self, candidatos, token="", esperas=ESPERAS, sin_datos_s=SIN_DATOS_S):
        self.candidatos, self.token, self._esperas, self._sin_datos = list(candidatos), token, esperas, sin_datos_s
        self._estado, self._detalle, self._red, self._version, self._modo = "detenido", "", "", "", ""
        self._telem, self._t_telem = None, None
        self._sock, self._lock = None, threading.Lock()
        self._detener = threading.Event()
        self._hilo = None

    # ---------------- consulta (la usa la interfaz con un temporizador, sin hilos de Qt) ----------------
    def snapshot(self):
        with self._lock:
            edad = None if self._t_telem is None else time.monotonic() - self._t_telem
            return {"estado": self._estado, "detalle": self._detalle, "telemetria": self._telem, "edad": edad,
                    "red": self._red, "version": self._version, "modo": self._modo}

    def _poner(self, estado, detalle=""):
        with self._lock:
            self._estado, self._detalle = estado, detalle

    # ---------------- ciclo de vida ----------------
    def iniciar(self):
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True)
            self._hilo.start()

    def detener(self):
        self._detener.set()
        with self._lock:
            s, self._sock = self._sock, None
        try:
            if s:
                s.close()
        except OSError:
            pass
        if self._hilo:
            self._hilo.join(timeout=3)
        self._poner("detenido")

    def enviar(self, comando):
        """True si el comando salió hacia Zeno. Solo si el enlace está activo."""
        with self._lock:
            s, ok = self._sock, self._estado == "conectado"
        if not s or not ok:
            return False
        try:
            s.sendall((comando + "\n").encode("utf-8"))
            return True
        except OSError:
            return False

    # ---------------- hilo ----------------
    def _bucle(self):
        intento, i = 0, 0
        while not self._detener.is_set():
            if not self.candidatos:
                self._poner("sin_destino", "No hay ninguna IP registrada para Zeno.")
                self._detener.wait(1.0)
                continue
            cand = self.candidatos[i % len(self.candidatos)]
            self._poner("conectando", f"Probando la red «{cand.red}»…")
            try:
                if self._sesion(cand):
                    intento = 0            # hubo un enlace bueno: se reintenta enseguida y por la misma red
                    continue
                i += 1
            except Rechazado:
                self._poner("rechazado", "Zeno rechazó el token.")
                return
            except OSError as ex:
                self._poner("reintentando", f"Sin enlace con «{cand.red}» ({type(ex).__name__})")
                i += 1
            espera = self._esperas[min(intento, len(self._esperas) - 1)]
            intento += 1
            self._detener.wait(espera)

    def _sesion(self, cand):
        """True si llegó a estar conectado y luego se perdió; False si ni siquiera llegó a hablar con Zeno."""
        s = _conectar(cand, self.token)
        with self._lock:
            self._sock = s
        conectado, buf, t_dato, t_ping = False, b"", time.monotonic(), 0.0
        try:
            while not self._detener.is_set():
                ahora = time.monotonic()
                if ahora - t_ping >= 1.0:       # latido: en MANUAL es lo que mantiene a Zeno en marcha
                    s.sendall(b"PING\n")
                    t_ping = ahora
                try:
                    datos = s.recv(4096)
                except socket.timeout:
                    datos = None
                if datos == b"":
                    break
                if datos:
                    t_dato = ahora
                    buf, lineas = _lineas(buf, datos)
                    for linea in lineas:
                        if linea.startswith("ERR,AUTH"):
                            raise Rechazado()
                        if linea.startswith("HELLO:"):
                            partes = linea[6:].split(",")
                            self._version = partes[1][:20] if len(partes) > 1 else ""
                            self._modo = partes[3] if len(partes) > 3 and partes[3] in ("AUTO", "MANUAL") else ""
                        telem = parsear_telem(linea)
                        if telem is not None:
                            with self._lock:
                                self._telem, self._t_telem, self._red = telem, time.monotonic(), cand.red
                            if not conectado:
                                conectado = True
                                self._poner("conectado", f"Conectado por la red «{cand.red}»")
                if ahora - t_dato > self._sin_datos:
                    self._poner("reintentando", "Zeno dejó de enviar datos")
                    break
            return conectado
        finally:
            with self._lock:
                self._sock, self._telem, self._t_telem, self._modo = None, None, None, ""
            try:
                s.close()
            except OSError:
                pass
            if not self._detener.is_set() and self._estado == "conectado":
                self._poner("reintentando", "Se perdió el enlace con Zeno")
