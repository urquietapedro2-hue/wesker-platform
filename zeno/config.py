"""Configuración ESTRUCTURAL de Zeno: pines, puertos, límites físicos de seguridad. Sin IPs fijas y sin secretos.
Todo lo que se ajusta a mano (ángulos, velocidades, tiempos, filtros) vive en `calibracion.py` + su JSON y se cambia desde el HMI."""
import os

# ---- Pines (BCM) ----
PIN_RPWM, PIN_LPWM, PIN_SERVO = 18, 13, 21
PINS_LINEA = (5, 6, 19, 20, 26)  # S1..S5
INVERTIR_LOGICA = True           # blanco = 0, negro = 1

# ---- Servos: PCA9685 (I2C) con respaldo a GPIO ----
PCA_DIRECCION_I2C = 0x40
CANAL_PCA = {"direccion": 0, "camara": 1, "rampa1": 2, "rampa2": 3}
PIN_SERVO_CAMARA = 16
PIN_SERVO_RAMPA = {1: 17, 2: 22}                    # libres y fuera de I2C(2,3)/UART/SPI
UMBRAL_FALLOS_I2C = 3                               # fallos seguidos de I2C antes de pasar a GPIO
# Límites FÍSICOS (mecánica): ninguna calibración ni prueba puede mandar un servo fuera de ellos.
LIMITES_FISICOS = {"direccion": (45.0, 135.0), "camara": (20.0, 160.0), "rampa1": (0.0, 180.0), "rampa2": (0.0, 180.0)}

# ---- Cámara (óptica; no se calibra a mano) ----
CAMARA_FOV_H = 60.0
PAN_GANANCIA = 0.6
PAN_TOLERANCIA_DEG = 2.0
PAN_PERDIDA_S = 1.5                                 # sin ver el QR este tiempo = vuelve a barrer

# ---- Estaciones (contenido de los QR) ----
ESTACIONES_VALIDAS = ("ESTACION_1", "ESTACION_2", "ESTACION_3")
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
