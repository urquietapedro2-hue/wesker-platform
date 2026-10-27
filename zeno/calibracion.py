"""Calibración de Zeno: todos los valores ajustables viven aquí (esquema + valores en un JSON), nunca en el código.
- Esquema único: cada parámetro trae tipo, rango, unidad y valor de fábrica. El HMI construye su panel a partir de él.
- Los cambios (`set`) se aplican en memoria al instante y validados; solo `guardar()` los escribe al JSON (escritura atómica).
- Un archivo dañado o con valores inválidos nunca impide arrancar: se usan los valores de fábrica y se avisa.
Ubicación del JSON: variable ZENO_CALIBRACION o ~/.config/wesker/zeno_calibracion.json (sin secretos)."""
import json
import logging
import math
import os
import threading
import time

log = logging.getLogger("zeno.calibracion")
FORMATO = 1


class ErrorCalibracion(ValueError):
    """Valor rechazado (clave desconocida, tipo, rango o incoherencia entre valores). El mensaje se muestra al usuario."""


def _p(grupo, etiqueta, tipo, minimo, maximo, defecto, unidad="", probar=None, ayuda=""):
    return {"grupo": grupo, "etiqueta": etiqueta, "tipo": tipo, "min": minimo, "max": maximo, "defecto": defecto,
            "unidad": unidad, "probar": probar, "ayuda": ayuda}


# Rangos físicos: la dirección y la cámara no pueden salir de lo que la mecánica soporta aunque se calibre mal.
ESQUEMA = {
    "direccion_centro": _p("Dirección", "Centro", "float", 45.0, 135.0, 90.0, "°", "direccion", "Ruedas rectas"),
    "direccion_min": _p("Dirección", "Mínimo (giro a la derecha)", "float", 45.0, 135.0, 70.0, "°", "direccion"),
    "direccion_max": _p("Dirección", "Máximo (giro a la izquierda)", "float", 45.0, 135.0, 125.0, "°", "direccion"),
    "direccion_invertida": _p("Dirección", "Invertir izquierda/derecha", "bool", None, None, False, "", None,
                              "Actívalo si Zeno gira al revés"),
    "direccion_trim": _p("Dirección", "Ajuste fino mecánico", "float", -20.0, 20.0, -8.6, "°", None,
                         "Corrige el desfase del brazo del servo (se suma a todos los ángulos)"),
    "direccion_pausa_s": _p("Dirección", "Tiempo de asentamiento", "float", 0.0, 1.0, 0.18, "s"),
    "camara_centro": _p("Cámara", "Centro", "float", 20.0, 160.0, 90.0, "°", "camara"),
    "camara_min": _p("Cámara", "Mínimo (izquierda)", "float", 20.0, 160.0, 30.0, "°", "camara"),
    "camara_max": _p("Cámara", "Máximo (derecha)", "float", 20.0, 160.0, 150.0, "°", "camara"),
    "camara_velocidad_dps": _p("Cámara", "Velocidad de barrido", "float", 5.0, 120.0, 40.0, "°/s"),
    "camara_invertida": _p("Cámara", "Invertir sentido del barrido", "bool", None, None, False, "", None,
                           "Actívalo si al subir el ángulo la cámara mira a la izquierda"),
    "rampa1_cerrado": _p("Rampa 1 (izquierda)", "Bloqueo (cerrada)", "float", 0.0, 180.0, 90.0, "°", "rampa1"),
    "rampa1_abierto": _p("Rampa 1 (izquierda)", "Liberación (abierta)", "float", 0.0, 180.0, 130.0, "°", "rampa1"),
    "rampa2_cerrado": _p("Rampa 2 (derecha)", "Bloqueo (cerrada)", "float", 0.0, 180.0, 90.0, "°", "rampa2"),
    "rampa2_abierto": _p("Rampa 2 (derecha)", "Liberación (abierta)", "float", 0.0, 180.0, 50.0, "°", "rampa2"),
    "vel_auto_max": _p("Tracción automática", "Límite de PWM en seguimiento de línea", "int", 10, 100, 45, "%", None,
                       "Tope para las órdenes automáticas; el modo manual no se limita"),
    "t_espera_descarga_s": _p("Temporizadores", "Espera con la rampa abierta", "float", 0.0, 300.0, 20.0, "s"),
    "t_indexacion_ms": _p("Temporizadores", "Pulso del avance de indexación", "int", 50, 3000, 400, "ms",
                          None, "Cuánto avanza Zeno en la Estación 1 para alinear la rampa 2"),
    "vel_indexacion": _p("Temporizadores", "PWM del avance de indexación", "int", 10, 100, 30, "%"),
    "t_salida_s": _p("Temporizadores", "Avance ciego al salir de una estación", "float", 0.2, 5.0, 1.0, "s",
                     None, "Evita volver a detectar la misma intersección"),
    "t_carga_max_s": _p("Temporizadores", "Aviso si la carga tarda más de", "float", 5.0, 600.0, 120.0, "s"),
    "t_escaneo_qr_s": _p("Temporizadores", "Aviso si no se lee QR en", "float", 1.0, 60.0, 8.0, "s"),
    "debounce_interseccion_ms": _p("Filtro de línea", "Tiempo con los 5 sensores activos", "int", 0, 2000, 150, "ms",
                                   None, "Evita falsos positivos por brillo o charolazos de la cinta"),
}
DEFECTOS = {k: v["defecto"] for k, v in ESQUEMA.items()}
GRUPOS_COHERENCIA = (("direccion_min", "direccion_centro", "direccion_max"), ("camara_min", "camara_centro", "camara_max"))
SEPARACION_RAMPA_MIN = 5.0   # grados entre bloqueo y liberación: menos que eso no abre de verdad


def ruta_por_defecto():
    return os.environ.get("ZENO_CALIBRACION") or os.path.join(os.path.expanduser("~"), ".config", "wesker", "zeno_calibracion.json")


def _convertir(clave, valor):
    """Valida un valor contra su especificación. Rechaza (no recorta): quien calibra debe ver el error."""
    esp = ESQUEMA.get(clave)
    if esp is None:
        raise ErrorCalibracion("parámetro desconocido: %s" % str(clave)[:40])
    if esp["tipo"] == "bool":
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, str) and valor.strip().lower() in ("true", "false"):
            return valor.strip().lower() == "true"
        raise ErrorCalibracion("%s: debe ser true o false" % clave)
    if isinstance(valor, bool):
        raise ErrorCalibracion("%s: debe ser un número" % clave)
    try:
        n = float(valor)
    except (TypeError, ValueError):
        raise ErrorCalibracion("%s: debe ser un número" % clave) from None
    if not math.isfinite(n):
        raise ErrorCalibracion("%s: número no válido" % clave)
    if not esp["min"] <= n <= esp["max"]:
        raise ErrorCalibracion("%s: fuera de rango (%g a %g %s)" % (clave, esp["min"], esp["max"], esp["unidad"]))
    if esp["tipo"] == "int":
        if n != int(n):
            raise ErrorCalibracion("%s: debe ser un entero" % clave)
        return int(n)
    return float(n)


def _coherente(v):
    """Reglas entre varios valores. Devuelve el mensaje de error o None."""
    for lo, centro, hi in GRUPOS_COHERENCIA:
        if not v[lo] <= v[centro] <= v[hi]:
            return "%s ≤ %s ≤ %s no se cumple (%g, %g, %g)" % (lo, centro, hi, v[lo], v[centro], v[hi])
    for n in (1, 2):
        if abs(v["rampa%d_abierto" % n] - v["rampa%d_cerrado" % n]) < SEPARACION_RAMPA_MIN:
            return "rampa%d: bloqueo y liberación deben diferir al menos %g°" % (n, SEPARACION_RAMPA_MIN)
    return None


class Calibracion:
    def __init__(self, ruta=None):
        self.ruta = ruta or ruta_por_defecto()
        self._v, self._lock, self._subs = dict(DEFECTOS), threading.RLock(), []
        self.version, self.sin_guardar, self.avisos = 0, False, []
        self.cargar()

    # ---------------- lectura ----------------
    def get(self, clave):
        return self._v[clave]

    __getitem__ = get

    def valores(self):
        with self._lock:
            return dict(self._v)

    @staticmethod
    def esquema():
        return ESQUEMA

    def suscribir(self, fn):
        """fn() se llama (fuera del cerrojo) después de cada cambio. Para que las rampas se reposicionen en vivo."""
        self._subs.append(fn)

    def _avisar(self):
        for fn in list(self._subs):
            try:
                fn()
            except Exception:
                log.exception("Un suscriptor de la calibración falló")

    # ---------------- escritura ----------------
    def set_many(self, cambios):
        """Todo o nada: valida cada valor y la coherencia del conjunto antes de aplicar. Devuelve la versión nueva."""
        if not isinstance(cambios, dict) or not cambios:
            raise ErrorCalibracion("no hay cambios")
        with self._lock:
            nuevo = dict(self._v)
            for k, val in cambios.items():
                nuevo[k] = _convertir(k, val)
            err = _coherente(nuevo)
            if err:
                raise ErrorCalibracion(err)
            if nuevo == self._v:
                return self.version
            self._v, self.sin_guardar = nuevo, True
            self.version += 1
            version = self.version
        self._avisar()
        return version

    def set(self, clave, valor):
        return self.set_many({clave: valor})

    def defecto(self):
        with self._lock:
            self._v, self.sin_guardar = dict(DEFECTOS), True
            self.version += 1
        self._avisar()

    # ---------------- archivo ----------------
    def cargar(self):
        """Lee el JSON. Nada de lo que contenga puede impedir el arranque."""
        avisos, valores = [], dict(DEFECTOS)
        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if not isinstance(datos, dict) or not isinstance(datos.get("valores"), dict):
                raise ValueError("estructura no reconocida")
            for k, val in datos["valores"].items():
                try:
                    valores[k] = _convertir(k, val)
                except ErrorCalibracion as ex:
                    avisos.append("%s (se usa el valor de fábrica)" % ex)
            err = _coherente(valores)
            if err:
                avisos.append("%s: se usan los valores de fábrica" % err)
                valores = dict(DEFECTOS)
        except FileNotFoundError:
            log.info("Sin archivo de calibración (%s): valores de fábrica", self.ruta)
        except (OSError, ValueError) as ex:
            avisos.append("archivo de calibración ilegible (%s): valores de fábrica" % type(ex).__name__)
            self._apartar_corrupto()
        with self._lock:
            self._v, self.sin_guardar, self.avisos = valores, False, avisos
            self.version += 1
        for a in avisos:
            log.warning("Calibración: %s", a)
        self._avisar()

    def _apartar_corrupto(self):
        try:
            os.replace(self.ruta, "%s.corrupto.%d" % (self.ruta, int(time.time())))
        except OSError:
            pass

    def guardar(self):
        """Escritura atómica (archivo temporal + reemplazo): un corte de energía no deja un JSON a medias."""
        with self._lock:
            datos = {"formato": FORMATO, "valores": dict(self._v)}
        carpeta = os.path.dirname(self.ruta) or "."
        os.makedirs(carpeta, exist_ok=True)
        tmp = "%s.tmp%d" % (self.ruta, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.ruta)
        with self._lock:
            self.sin_guardar = False
        log.info("Calibración guardada en %s", self.ruta)

    def restaurar(self):
        """Descarta lo no guardado: vuelve a leer el archivo."""
        self.cargar()

    # ---------------- para el protocolo ----------------
    def instantanea(self):
        with self._lock:
            return {"version": self.version, "sin_guardar": self.sin_guardar, "valores": dict(self._v)}

    def esquema_publico(self):
        orden = []
        for k, e in ESQUEMA.items():
            orden.append({"clave": k, **e})
        return orden
