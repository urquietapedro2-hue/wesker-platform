"""Lógica pura de Zeno (sin GPIO, sin cámara, sin red): se prueba entera en una PC.
Reglas de seguimiento de línea (idénticas a ZENO_V2 / la lógica NUEVA) y protocolo de red. La máquina de estados está en ruta.py."""
import time
from collections import namedtuple


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
    if cmd in ("PING", "HELLO", "CAM_ON", "CAM_OFF", "ABORTAR", "CAL_GET", "CAL_ESQUEMA", "CAL_GUARDAR", "CAL_RESTAURAR",
               "CAL_DEFECTO") and len(partes) == 1:
        return Comando(cmd, None, None, None)
    if cmd == "AUTH" and len(partes) == 2:
        return Comando("AUTH", partes[1], None, None)  # el token se conserva tal cual (distingue mayúsculas)
    if cmd == "MODE":
        modo = partes[1].upper() if len(partes) == 2 else ""
        return Comando("MODE", modo, None, None) if modo in ("AUTO", "MANUAL") else Comando("INVALIDO", "MODE debe ser AUTO o MANUAL", None, None)
    if cmd == "CARGA_RAMPA":    # la rampa n ya fue cargada (botón del HMI o, más adelante, Albert)
        n = _entero(partes[1], 1, 2) if len(partes) == 2 else None
        return Comando("CARGA_RAMPA", n, None, None) if n else Comando("INVALIDO", "CARGA_RAMPA,1|2", None, None)
    if cmd == "CAL_SET":        # CAL_SET,clave,valor  (el valor se valida en Calibracion)
        if len(partes) == 3 and partes[1] and partes[2]:
            return Comando("CAL_SET", partes[1], partes[2], None)
        return Comando("INVALIDO", "CAL_SET,clave,valor", None, None)
    if cmd == "CAL_PROBAR":     # CAL_PROBAR,servo,grados: mueve un servo para ver el efecto mientras se calibra (solo MANUAL)
        ang = _entero(partes[2], 0, 180) if len(partes) == 3 else None
        if len(partes) == 3 and partes[1].lower() in ("direccion", "camara", "rampa1", "rampa2") and ang is not None:
            return Comando("CAL_PROBAR", partes[1].lower(), ang, None)
        return Comando("INVALIDO", "CAL_PROBAR,direccion|camara|rampa1|rampa2,0-180", None, None)
    if cmd == "PAN":
        arg = partes[1].upper() if len(partes) == 2 else ""
        if arg in ("AUTO", "CENTRO"):
            return Comando("PAN", arg, None, None)
        ang = _entero(arg, 0, 180)
        return Comando("PAN", ang, None, None) if ang is not None else Comando("INVALIDO", "PAN,AUTO|CENTRO|0-180", None, None)
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


def formatear_ruta(r, servos, cal_version):
    """Línea adicional después de TELEM (un HMI viejo la ignora):
    RUTA:fase,estacion,carga_r1,carga_r2,alarma,restante_s,backend,i2c,ang_dir,ang_cam,ang_r1,ang_r2,cal_version
    `r` es Ruta.estado(); `servos` es GestorServos.estado(); '-' = servo aún sin mover."""
    ang = [("-" if servos["servos"][n]["angulo"] is None else "%.0f" % servos["servos"][n]["angulo"])
           for n in ("direccion", "camara", "rampa1", "rampa2")]
    return "RUTA:%s,%s,%d,%d,%s,%.0f,%s,%d,%s,%d\n" % (r["fase"], r["estacion"], int(r["carga_r1"]), int(r["carga_r2"]), r["alarma"],
                                                  r["restante_s"], servos["backend"], int(servos["i2c"]), ",".join(ang), cal_version)


class VigilanteEnlace:
    """Perro guardián: avisa cuando pasa demasiado tiempo sin recibir nada del HMI."""

    def __init__(self, tiempo_s, reloj=time.monotonic):
        self.tiempo_s, self._reloj, self._ultimo = tiempo_s, reloj, reloj()

    def latido(self):
        self._ultimo = self._reloj()

    def vencido(self):
        return self._reloj() - self._ultimo > self.tiempo_s
