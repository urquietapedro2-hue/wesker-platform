"""Enlace del HMI con el nodo Zeno por TCP. Sin Qt: hilo propio, reconexión con espera creciente y datos consultables.
Protocolo de Zeno: ver zeno/README.md. El HMI nunca guarda la IP: recibe candidatos (red, ip, puerto) del registro de nodos."""
import json
import socket
import threading
import time
from collections import namedtuple
from urllib.parse import quote

Candidato = namedtuple("Candidato", "red ip puerto")
ESPERAS = (1.0, 2.0, 4.0, 8.0, 15.0)   # segundos entre intentos; crece y se queda en 15
SIN_DATOS_S = 3.0                      # sin recibir nada de Zeno durante este tiempo = enlace muerto
TIMEOUT_CONEXION_S = 1.5
DIRECCIONES = ("F", "B", "L", "R", "S", "FL", "FR", "BL", "BR", "ESTACION")
ESTACIONES = ("ESTACION_1", "ESTACION_2", "ESTACION_3")
PUERTO_VIDEO = 8080
FASES = ("ST1_CARGA_R1", "ST1_INDEXANDO", "ST1_CARGA_R2", "SEGUIMIENTO", "ESCANEANDO_QR", "DESCARGANDO", "SALIENDO", "MANUAL")
ALARMAS = ("NINGUNA", "TIMEOUT_CARGA", "QR_NO_LEIDO")
BACKENDS = ("PCA9685", "GPIO", "NINGUNO")
NOMBRES_SERVO = ("direccion", "camara", "rampa1", "rampa2")
TIPOS_CAL = ("float", "int", "bool")
MAX_PARAMETROS = 80     # un esquema mayor que esto no es de Zeno: se descarta


class Rechazado(Exception):
    """Zeno rechazó el token. Reintentar no sirve: hay que corregirlo."""


def detectar_estacion(previa, actual):
    """Disparador del visor de cámara: devuelve la estación si el QR pasó a una estación distinta de la anterior, o None."""
    return actual if actual in ESTACIONES and actual != previa else None


def parsear_ruta(linea):
    """`RUTA:fase,estacion,carga_r1,carga_r2,alarma,restante_s,backend,i2c,ang x4,cal_version` -> dict o None. Nunca lanza excepciones.
    Si Zeno es una versión vieja esta línea no existe y el HMI funciona igual."""
    if not linea.startswith("RUTA:"):
        return None
    p = linea[5:].strip().split(",")
    if len(p) != 13:
        return None
    fase, estacion, r1, r2, alarma, restante, backend, i2c = p[:8]
    if (fase not in FASES or alarma not in ALARMAS or backend not in BACKENDS or r1 not in ("0", "1") or r2 not in ("0", "1")
            or i2c not in ("0", "1") or not (estacion == "NINGUNA" or estacion in ESTACIONES)):
        return None
    try:
        restante, version = float(restante), int(p[12])
    except ValueError:
        return None
    if not 0.0 <= restante <= 3600.0 or not 0 <= version <= 10 ** 9:
        return None
    angulos = {}
    for nombre, texto in zip(NOMBRES_SERVO, p[8:12]):
        if texto == "-":
            angulos[nombre] = None
            continue
        try:
            a = float(texto)
        except ValueError:
            return None
        if not 0.0 <= a <= 180.0:
            return None
        angulos[nombre] = a
    return {"fase": fase, "estacion": estacion, "carga_r1": r1 == "1", "carga_r2": r2 == "1", "alarma": alarma,
            "restante_s": restante, "backend": backend, "i2c": i2c == "1", "servos": angulos, "cal_version": version}


def _numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e9


def parsear_cal(linea):
    """`CAL:{json}` -> {"version", "sin_guardar", "valores": {clave: bool|int|float}} o None."""
    if not linea.startswith("CAL:"):
        return None
    try:
        d = json.loads(linea[4:])
    except ValueError:
        return None
    if (not isinstance(d, dict) or not isinstance(d.get("version"), int) or isinstance(d.get("version"), bool)
            or not isinstance(d.get("valores"), dict) or len(d["valores"]) > MAX_PARAMETROS):
        return None
    valores = {}
    for k, v in d["valores"].items():
        if not isinstance(k, str) or len(k) > 40 or not (isinstance(v, bool) or _numero(v)):
            return None
        valores[k] = v
    return {"version": d["version"], "sin_guardar": d.get("sin_guardar") is True, "valores": valores}


def parsear_cal_esquema(linea):
    """`CAL_ESQ:[json]` -> lista de parámetros validados (el panel se construye con esto) o None."""
    if not linea.startswith("CAL_ESQ:"):
        return None
    try:
        d = json.loads(linea[8:])
    except ValueError:
        return None
    if not isinstance(d, list) or not 0 < len(d) <= MAX_PARAMETROS:
        return None
    salida = []
    for e in d:
        if not isinstance(e, dict) or e.get("tipo") not in TIPOS_CAL:
            return None
        txt = [e.get(k) for k in ("clave", "grupo", "etiqueta", "unidad", "ayuda")]
        if not all(isinstance(t, str) and len(t) <= 120 for t in txt) or not txt[0] or not txt[1] or not txt[2]:
            return None
        if e["tipo"] != "bool" and not (_numero(e.get("min")) and _numero(e.get("max")) and e["min"] <= e["max"]):
            return None
        if not (isinstance(e.get("defecto"), bool) or _numero(e.get("defecto"))):
            return None
        probar = e.get("probar")
        if probar is not None and probar not in NOMBRES_SERVO:
            return None
        salida.append({"clave": txt[0], "grupo": txt[1], "etiqueta": txt[2], "unidad": txt[3], "ayuda": txt[4], "tipo": e["tipo"],
                       "min": e.get("min"), "max": e.get("max"), "defecto": e["defecto"], "probar": probar})
    return salida


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
        self._telem, self._t_telem, self._ruta, self._ip = None, None, None, ""
        self._cal, self._cal_esq, self._cal_err, self._cal_pedida = None, None, (0, ""), -1
        self._sock, self._lock = None, threading.Lock()
        self._detener = threading.Event()
        self._hilo = None

    # ---------------- consulta (la usa la interfaz con un temporizador, sin hilos de Qt) ----------------
    def snapshot(self):
        with self._lock:
            edad = None if self._t_telem is None else time.monotonic() - self._t_telem
            return {"estado": self._estado, "detalle": self._detalle, "telemetria": self._telem, "edad": edad,
                    "red": self._red, "version": self._version, "modo": self._modo, "ruta": self._ruta,
                    "cal": self._cal, "cal_esquema": self._cal_esq, "cal_error": self._cal_err}

    def url_video(self, puerto=PUERTO_VIDEO):
        """URL del video MJPEG de la Raspberry de Zeno (con el token). Solo para el visor: no se guarda ni se registra."""
        with self._lock:
            ip = self._ip
        if not ip:
            return ""
        return f"http://{ip}:{puerto}/stream.mjpg" + (f"?t={quote(self.token, safe='')}" if self.token else "")

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

    def _procesar_zeno(self, s, linea):
        """Líneas de ruta y calibración. True si la línea era de esas (ya no se mira como telemetría)."""
        ruta = parsear_ruta(linea)
        if ruta is not None:
            pedir = False
            with self._lock:
                self._ruta = ruta
                # otro HMI (o el propio Zeno) cambió la calibración: se vuelve a leer, una sola vez por versión
                if (self._cal is None or ruta["cal_version"] != self._cal["version"]) and ruta["cal_version"] != self._cal_pedida:
                    self._cal_pedida, pedir = ruta["cal_version"], True
            if pedir:
                s.sendall(b"CAL_GET\n")
            return True
        if linea.startswith("CAL_ERR:"):
            with self._lock:
                self._cal_err = (self._cal_err[0] + 1, linea[8:][:160])
            return True
        cal = parsear_cal(linea)
        if cal is not None:
            with self._lock:
                self._cal = cal
            return True
        esq = parsear_cal_esquema(linea)
        if esq is not None:
            with self._lock:
                self._cal_esq = esq
            return True
        return linea.startswith(("CAL:", "CAL_ESQ:"))      # inválidas de calibración: se descartan sin tocar nada

    def _sesion(self, cand):
        """True si llegó a estar conectado y luego se perdió; False si ni siquiera llegó a hablar con Zeno."""
        s = _conectar(cand, self.token)
        with self._lock:
            self._sock, self._ip = s, cand.ip
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
                        if self._procesar_zeno(s, linea):
                            continue
                        telem = parsear_telem(linea)
                        if telem is not None:
                            with self._lock:
                                self._telem, self._t_telem, self._red = telem, time.monotonic(), cand.red
                            if not conectado:
                                conectado = True
                                self._poner("conectado", f"Conectado por la red «{cand.red}»")
                                s.sendall(b"CAL_ESQUEMA\nCAL_GET\n")      # el panel de calibración se arma con lo que Zeno dice
                if ahora - t_dato > self._sin_datos:
                    self._poner("reintentando", "Zeno dejó de enviar datos")
                    break
            return conectado
        finally:
            with self._lock:
                self._sock, self._telem, self._t_telem, self._modo, self._ruta, self._ip = None, None, None, "", None, ""
            self._cal, self._cal_esq, self._cal_pedida = None, None, -1
            try:
                s.close()
            except OSError:
                pass
            if not self._detener.is_set() and self._estado == "conectado":
                self._poner("reintentando", "Se perdió el enlace con Zeno")
