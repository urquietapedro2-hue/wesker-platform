"""Lógica pura de Zeno (sin GPIO, sin cámara, sin red): se prueba entera en una PC. Decisiones idénticas a ZENO_V2."""
import time
from collections import namedtuple

from zeno import config

Orden = namedtuple("Orden", "cmd vel camara mensaje")  # cmd None = no cambiar lo que ya hace
SIN_CAMBIO = Orden(None, 0, False, "")


def decidir_v2(s):
    """Reglas de SEGUIMIENTO de ZENO_V2, tal cual. Devuelve (cmd, vel) o None si ninguna regla aplica (mantiene)."""
    s1, s2, s3, s4, s5 = s
    if (s1 == 1 and s2 == 1) or (s1 == 1 and s5 == 0):
        return ("L", 42)
    if (s4 == 1 and s5 == 1) or (s5 == 1 and s1 == 0):
        return ("R", 42)
    if s3 == 1 and s1 == 0 and s5 == 0:
        return ("F", 45)
    if s2 == 1 and s1 == 0 and s5 == 0:
        return ("L", 40)
    if s4 == 1 and s1 == 0 and s5 == 0:
        return ("R", 40)
    if not s1 and not s2 and not s3 and not s4 and not s5:
        return ("S", 0)
    return None


def decidir_nueva(s):
    """Lógica de tu script de prueba con el sensor nuevo: el centro tiene prioridad y nunca queda una combinación sin regla."""
    s1, s2, s3, s4, s5 = s
    if (s2 == 1 and s3 == 1 and s4 == 1) or (s3 == 1 and s1 == 0 and s5 == 0):
        return ("F", 45)
    if s1 == 1 or s2 == 1:
        return ("L", 42)
    if s4 == 1 or s5 == 1:
        return ("R", 42)
    return ("S", 0)


LOGICAS = {"V2": decidir_v2, "NUEVA": decidir_nueva}


class Navegador:
    """Máquina de estados del modo AUTO (SEGUIMIENTO -> ESTACION_DESCARGA -> SALIENDO_ESTACION). Sin esperas bloqueantes."""

    def __init__(self, logica="V2", reloj=time.monotonic):
        if logica not in LOGICAS:
            raise ValueError("lógica de navegación desconocida: %s" % logica)
        self._decidir, self._reloj = LOGICAS[logica], reloj
        self.logica = logica
        self.modo, self.sub = "AUTO", "SEGUIMIENTO"
        self.ultima_estacion = "NINGUNO"
        self._t_arribo, self._t_salida = 0.0, None

    def cambiar_modo(self, modo):
        self.modo, self._t_salida = modo, None
        if modo == "AUTO":
            self.sub = "SEGUIMIENTO"

    def reanudar(self):
        if self.sub == "ESTACION_DESCARGA":
            self.sub = "SALIENDO_ESTACION"
            self._t_salida = None
            return True
        return False

    def paso(self, sensores, qr, ahora=None):
        ahora = self._reloj() if ahora is None else ahora
        if self.modo != "AUTO":
            return SIN_CAMBIO
        if self.sub == "ESTACION_DESCARGA":
            if ahora - self._t_arribo >= config.TIEMPO_ESPERA_ESTACION:
                self.sub = "SALIENDO_ESTACION"
                self._t_salida = None
                return Orden("S", 0, True, "Ciclo cumplido en %s. Desalojando bahía..." % self.ultima_estacion)
            return Orden("S", 0, True, "")
        if self.sub == "SALIENDO_ESTACION":  # avance ciego: ignora los sensores durante SALIDA_CIEGA_S
            if self._t_salida is None:
                self._t_salida = ahora
            if ahora - self._t_salida < config.SALIDA_CIEGA_S:
                return Orden("F", 45, False, "")
            self.sub, self._t_salida = "SEGUIMIENTO", None
            return SIN_CAMBIO
        s1, s2, s3, s4, s5 = sensores
        es_base = (s1 == 1 and s2 == 1 and s3 == 1 and s4 == 1 and s5 == 1)
        es_nuevo_qr = (qr in config.ESTACIONES_VALIDAS and qr != self.ultima_estacion)
        if es_base or es_nuevo_qr:
            self.sub, self._t_arribo = "ESTACION_DESCARGA", ahora
            self.ultima_estacion = qr if qr != "NINGUNO" else "ZONA_DESCARGA"
            grano = config.GRANOS_ESTACION.get(qr, "ZONA GENERAL")
            return Orden("S", 0, True, "Arribo a %s (%s)" % (self.ultima_estacion, grano))
        if qr == "NINGUNO" and self.ultima_estacion != "NINGUNO":
            self.ultima_estacion = "NINGUNO"
        decision = self._decidir(sensores)
        return SIN_CAMBIO if decision is None else Orden(decision[0], decision[1], False, "")


# ---------------------------------------------------------------- protocolo
Comando = namedtuple("Comando", "tipo a b c")
MOVIMIENTOS = ("F", "B", "L", "R", "S")


def _entero(texto, minimo, maximo):
    try:
        n = int(texto)
    except (TypeError, ValueError):
        return None
    return n if minimo <= n <= maximo else None


def parsear_comando(linea):
    """Valida una línea del protocolo. Nunca lanza excepciones. tipo = INVALIDO si algo no cuadra."""
    partes = [p.strip() for p in linea.strip().split(",")]
    cmd = partes[0].upper()
    if not cmd:
        return Comando("VACIO", None, None, None)
    if cmd in ("PING", "HELLO", "RESUME", "CAM_ON", "CAM_OFF") and len(partes) == 1:
        return Comando(cmd, None, None, None)
    if cmd == "AUTH" and len(partes) == 2:
        return Comando("AUTH", partes[1], None, None)  # el token se conserva tal cual (distingue mayúsculas)
    if cmd == "MODE":
        modo = partes[1].upper() if len(partes) == 2 else ""
        return Comando("MODE", modo, None, None) if modo in ("AUTO", "MANUAL") else Comando("INVALIDO", "MODE debe ser AUTO o MANUAL", None, None)
    if cmd == "DIAG_PULSE":
        d = partes[1].upper() if len(partes) > 1 else "F"
        v = _entero(partes[2], 0, 100) if len(partes) > 2 else 45
        ms = _entero(partes[3], 50, 3000) if len(partes) > 3 else 450
        if d not in ("F", "B", "L", "R") or v is None or ms is None or len(partes) > 4:
            return Comando("INVALIDO", "DIAG_PULSE,dir(F/B/L/R),vel(0-100),ms(50-3000)", None, None)
        return Comando("DIAG_PULSE", d, v, ms)
    if cmd in MOVIMIENTOS and len(partes) <= 2:
        v = _entero(partes[1], 0, 100) if len(partes) == 2 else 45
        return Comando("MOVER", cmd, v, None) if v is not None else Comando("INVALIDO", "la velocidad va de 0 a 100", None, None)
    return Comando("INVALIDO", "comando desconocido", None, None)


def formatear_telemetria(direccion, velocidad, distancia, sensores, subestado, qr):
    """Formato idéntico al de ZENO_V2 (el HMI ya lo entiende)."""
    s1, s2, s3, s4, s5 = sensores
    return "TELEM:%s,%d,%.1f,%d,%d,%d,%d,%d,%s,%s\n" % (direccion, int(velocidad), distancia, s1, s2, s3, s4, s5, subestado, qr)


class VigilanteEnlace:
    """Perro guardián: avisa cuando pasa demasiado tiempo sin recibir nada del HMI."""

    def __init__(self, tiempo_s, reloj=time.monotonic):
        self.tiempo_s, self._reloj, self._ultimo = tiempo_s, reloj, reloj()

    def latido(self):
        self._ultimo = self._reloj()

    def vencido(self):
        return self._reloj() - self._ultimo > self.tiempo_s
