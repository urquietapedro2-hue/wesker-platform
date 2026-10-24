"""Configuración de Zeno. Sin IPs fijas y sin secretos en el código: todo viene del entorno o de un archivo local."""
import os

# ---- Pines (BCM). Iguales a ZENO_V2 ----
PIN_RPWM, PIN_LPWM, PIN_SERVO = 18, 13, 21
PINS_LINEA = (5, 6, 19, 20, 26)  # S1..S5
INVERTIR_LOGICA = True           # blanco = 0, negro = 1

# ---- Dirección y tracción (iguales a V2) ----
OFFSET_SERVO_TRIM = -8.6
ANGULO_IZQ, ANGULO_CENTRO, ANGULO_DER = 65, 90, 115
PAUSA_SERVO_S = 0.18

# ---- Estaciones ----
ESTACIONES_VALIDAS = ("ESTACION_1", "ESTACION_2", "ESTACION_3")
GRANOS_ESTACION = {"ESTACION_1": "FRIJOL PINTO", "ESTACION_2": "FRIJOL NEGRO", "ESTACION_3": "FRIJOL PERUANO"}
TIEMPO_ESPERA_ESTACION = 5.0
SALIDA_CIEGA_S = 1.0
DISTANCIA_SIN_SENSOR = 35.0  # V2 enviaba siempre 35.0: NO hay sensor ultrasónico leído en el código

# ---- Red (se enlaza a todas las interfaces; la IP real la decide el router, nunca el código) ----
HOST = os.environ.get("ZENO_HOST", "0.0.0.0")
PUERTO_CONTROL = int(os.environ.get("ZENO_PUERTO", "65432"))
PUERTO_VIDEO = int(os.environ.get("ZENO_PUERTO_VIDEO", "8080"))
NODO_ID = "ZENO-01"

# ---- Seguridad y fiabilidad ----
LOGICA_NAVEGACION = os.environ.get("ZENO_LOGICA", "V2").upper()   # V2 (la de siempre) | NUEVA (la de tu prueba)
VIGILANCIA_MANUAL_S = float(os.environ.get("ZENO_VIGILANCIA_S", "2.0"))  # en MANUAL, sin latidos este tiempo = paro
TIEMPO_AUTENTICACION_S = 3.0
MAX_LINEA = 256                  # bytes: una línea más larga que esto cierra la conexión
LATIDO_NAVEGACION_MAX_S = 1.0    # si el bucle de navegación no avanza este tiempo = paro


def ruta_token():
    return os.environ.get("ZENO_TOKEN_FILE") or os.path.join(os.path.expanduser("~"), ".config", "wesker", "zeno_token")


def cargar_token():
    """Token de acceso: variable ZENO_TOKEN o archivo (permisos 600). Vacío = SIN autenticación (se avisa al arrancar)."""
    t = (os.environ.get("ZENO_TOKEN") or "").strip()
    if t:
        return t
    try:
        with open(ruta_token(), "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""
