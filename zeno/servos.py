"""Servos de Zeno: PCA9685 (I2C) con respaldo automático a PWM por GPIO. Canales: direccion, camara, rampa1, rampa2.
Si el PCA9685 no existe, no responde o falla N veces seguidas, se usa GPIO sin reconfigurar nada y se reaplican las posiciones.
Los ángulos de trabajo (centro, mínimo, máximo, rampas) llegan de la calibración; aquí solo se imponen los límites FÍSICOS."""
import logging
import threading
import time

from zeno import config
from zeno.calibracion import DEFECTOS

log = logging.getLogger("zeno.servos")
US_MIN, US_MAX = 500.0, 2500.0   # 0°..180°  (equivale a duty 2.5%..12.5% a 50 Hz)


def angulo_a_us(angulo):
    return US_MIN + (US_MAX - US_MIN) * max(0.0, min(180.0, angulo)) / 180.0


class _PCAReal:
    """Envoltorio mínimo de adafruit_pca9685 con la interfaz que usa GestorServos."""

    def __init__(self):
        import board
        import busio
        from adafruit_pca9685 import PCA9685
        self.pca = PCA9685(busio.I2C(board.SCL, board.SDA), address=config.PCA_DIRECCION_I2C)
        self.pca.frequency = 50

    def pulso_us(self, canal, us):
        self.pca.channels[canal].duty_cycle = int(us / 20000.0 * 65535)

    def apagar(self, canal):
        self.pca.channels[canal].duty_cycle = 0

    def cerrar(self):
        self.pca.deinit()


def fabrica_pca_real():
    return _PCAReal()


class _Servo:
    def __init__(self, nombre, pin, canal, limites, soltar, trim=lambda: 0.0):
        self.nombre, self.pin, self.canal, self.limites, self.soltar, self.trim = nombre, pin, canal, limites, soltar, trim
        self.angulo, self.pwm, self.ok = None, None, True


def servos_por_defecto(cal=None):
    cal = DEFECTOS if cal is None else cal
    f = config.LIMITES_FISICOS
    return [_Servo("direccion", config.PIN_SERVO, config.CANAL_PCA["direccion"], f["direccion"], True,
                   lambda: cal["direccion_trim"]),
            _Servo("camara", config.PIN_SERVO_CAMARA, config.CANAL_PCA["camara"], f["camara"], False),
            _Servo("rampa1", config.PIN_SERVO_RAMPA[1], config.CANAL_PCA["rampa1"], f["rampa1"], False),   # bloqueo: se mantiene
            _Servo("rampa2", config.PIN_SERVO_RAMPA[2], config.CANAL_PCA["rampa2"], f["rampa2"], False)]


class GestorServos:
    def __init__(self, gpio=None, fabrica_pca=fabrica_pca_real, intentar_pca=True, servos=None, cal=None, reloj=time.monotonic,
                 dormir=time.sleep, umbral_fallos=config.UMBRAL_FALLOS_I2C):
        self._gpio, self._reloj, self._dormir, self._umbral = gpio, reloj, dormir, umbral_fallos
        self._servos = {s.nombre: s for s in (servos or servos_por_defecto(cal))}
        self._lock = threading.RLock()
        self._pca, self._fallos, self.motivo_fallback, self.alarma = None, 0, "", ""
        self.backend = "NINGUNO"
        if intentar_pca:
            try:
                self._pca = fabrica_pca()
                self.backend = "PCA9685"
                log.info("Servos: PCA9685 por I2C")
            except Exception as ex:  # sin placa, sin librería, I2C apagado...
                self.motivo_fallback = "%s: %s" % (type(ex).__name__, ex)
                log.warning("PCA9685 no disponible (%s): se usa GPIO", self.motivo_fallback)
        else:
            self.motivo_fallback = "desactivado"
        if self._pca is None:
            self._activar_gpio()

    # ---------------- respaldo GPIO ----------------
    def _activar_gpio(self):
        with self._lock:
            if self._gpio is None:
                try:
                    import RPi.GPIO as gpio
                    self._gpio = gpio
                    gpio.setmode(gpio.BCM)
                    gpio.setwarnings(False)
                except Exception as ex:
                    self.backend, self.alarma = "NINGUNO", "SIN_SERVOS"
                    log.error("Ni PCA9685 ni GPIO disponibles: servos desactivados (%s)", ex)
                    return
            for s in self._servos.values():
                if s.pwm is None:
                    try:
                        self._gpio.setup(s.pin, self._gpio.OUT)
                        s.pwm = self._gpio.PWM(s.pin, 50)
                        s.pwm.start(0)
                    except Exception:
                        s.ok = False
                        log.exception("Pin de servo %s (GPIO%s) no disponible", s.nombre, s.pin)
            self.backend = "GPIO"

    def _degradar(self, motivo):
        log.error("I2C/PCA9685 falla (%s): paso automático a GPIO", motivo)
        self.motivo_fallback = motivo
        pca, self._pca = self._pca, None
        try:
            pca.cerrar()
        except Exception:
            pass
        self._activar_gpio()
        for s in self._servos.values():       # reaplica lo último conocido
            if s.angulo is not None and s.ok:
                self._salida(s, s.angulo + s.trim())

    # ---------------- salida física ----------------
    @property
    def i2c_ok(self):
        return self._pca is not None

    def _salida(self, s, angulo):
        lo, hi = s.limites
        us = angulo_a_us(max(lo, min(hi, angulo)))
        if self._pca is not None:
            try:
                self._pca.pulso_us(s.canal, us)
                self._fallos = 0
                return True
            except Exception as ex:
                self._fallos += 1
                if self._fallos >= self._umbral:
                    self._degradar("%s: %s" % (type(ex).__name__, ex))
                return False
        if s.pwm is None or not s.ok:
            return False
        try:
            s.pwm.ChangeDutyCycle(us / 200.0)
            return True
        except Exception:
            log.exception("Servo %s: error de GPIO", s.nombre)
            return False

    def _apagar(self, s):
        try:
            if self._pca is not None:
                self._pca.apagar(s.canal)
            elif s.pwm is not None:
                s.pwm.ChangeDutyCycle(0)
        except Exception:
            log.exception("Servo %s: no se pudo soltar", s.nombre)

    def _servo(self, nombre):
        s = self._servos.get(nombre)
        if s is None:
            raise KeyError("servo desconocido: %s" % nombre)
        return s

    # ---------------- API ----------------
    def disponible(self, nombre):
        s = self._servos.get(nombre)
        return bool(s) and s.ok and self.backend != "NINGUNO"

    def angulo(self, nombre):
        return self._servo(nombre).angulo

    def mover(self, nombre, angulo, esperar_s=None):
        """Mueve al ángulo (acotado a los límites FÍSICOS; el trim solo afecta a la dirección). Con esperar_s (aunque sea 0)
        bloquea ese tiempo y suelta el servo si es de los que se sueltan (igual que V2 con la dirección)."""
        with self._lock:
            s = self._servo(nombre)
            lo, hi = s.limites
            s.angulo = max(lo, min(hi, float(angulo)))
            ok = self._salida(s, s.angulo + s.trim())
        if esperar_s is not None:
            self._dormir(esperar_s)
            with self._lock:
                if s.soltar:
                    self._apagar(s)
        return ok

    def estado(self):
        with self._lock:
            return {"backend": self.backend, "i2c": self.i2c_ok, "motivo": self.motivo_fallback, "alarma": self.alarma,
                    "servos": {n: {"angulo": s.angulo, "ok": s.ok} for n, s in self._servos.items()}}

    def liberar_todo(self):
        with self._lock:
            for s in self._servos.values():
                self._apagar(s)

    def cerrar(self):
        with self._lock:
            self.liberar_todo()
            for s in self._servos.values():
                if s.pwm is not None:
                    try:
                        s.pwm.stop()
                    except Exception:
                        pass
            if self._pca is not None:
                try:
                    self._pca.cerrar()
                except Exception:
                    pass
                self._pca = None


class Rampas:
    """Las dos rampas de descarga (1 = izquierda, 2 = derecha). Cerrada = bloqueo (carga retenida), abierta = liberación.
    Los ángulos se leen de la calibración en cada orden, y si cambian con la rampa en una posición, se reaplican en vivo."""

    def __init__(self, gestor, cal):
        self.g, self.cal, self._est = gestor, cal, {1: None, 2: None}
        cal.suscribir(self.reaplicar)

    @staticmethod
    def _check(n):
        if n not in (1, 2):
            raise ValueError("rampa inexistente: %r" % (n,))

    def _poner(self, n, estado):
        self._check(n)
        self._est[n] = estado
        self.g.mover("rampa%d" % n, self.cal["rampa%d_%s" % (n, "abierto" if estado == "ABIERTA" else "cerrado")])

    def abrir(self, n):
        self._poner(n, "ABIERTA")

    def cerrar(self, n):
        self._poner(n, "CERRADA")

    def cerrar_todas(self):
        self.cerrar(1)
        self.cerrar(2)

    def estado(self, n):
        self._check(n)
        return self._est[n]

    def olvidar(self):
        """Deja de seguir la posición de las rampas (modo manual / pruebas de calibración)."""
        self._est = {1: None, 2: None}

    def reaplicar(self):
        for n, est in self._est.items():
            if est is not None:
                self._poner(n, est)


class PanCamara:
    """Servo de cámara: BARRIDO (de izquierda a derecha buscando QR), SEGUIMIENTO (centra el QR visto) o FIJO."""

    def __init__(self, gestor, cal, reloj=time.monotonic):
        self.g, self.cal, self._reloj = gestor, cal, reloj
        self.modo, self.angulo, self.alineado = "FIJO", cal["camara_centro"], False
        self._mov, self._t, self._visto, self._barre = 1, None, None, False   # _mov: sentido del barrido en grados (+1 sube)

    def _poner(self, angulo, calibrado=True):
        lo, hi = (self.cal["camara_min"], self.cal["camara_max"]) if calibrado else config.LIMITES_FISICOS["camara"]
        nuevo = max(lo, min(hi, angulo))
        if abs(nuevo - self.angulo) >= 0.3 or self.g.angulo("camara") is None:
            self.angulo = nuevo
            self.g.mover("camara", nuevo)

    def fijar(self, angulo, calibrado=False):
        """Posición fija. Desde el HMI/banco se acota solo a la mecánica; el seguimiento usa el rango calibrado."""
        self._barre, self.modo, self.alineado = False, "FIJO", False
        self._poner(angulo, calibrado)

    def centrar(self):
        self.fijar(self.cal["camara_centro"], calibrado=False)

    def barrido(self):
        if not self._barre:
            self._barre, self.modo, self.alineado, self._t = True, "BARRIDO", False, None
            self._mov = -1 if self.cal["camara_invertida"] else 1
            self._poner(self.cal["camara_max"] if self.cal["camara_invertida"] else self.cal["camara_min"])   # empieza por la izquierda

    def tick(self, qr_centro=None, ahora=None):
        """qr_centro: posición horizontal del QR en la imagen (-1 izquierda ... +1 derecha) o None si no se ve."""
        ahora = self._reloj() if ahora is None else ahora
        dt = 0.0 if self._t is None else min(0.2, ahora - self._t)
        self._t = ahora
        if not self._barre:
            return
        signo = -1.0 if self.cal["camara_invertida"] else 1.0
        if qr_centro is not None:
            self._visto = ahora
            self.modo = "SEGUIMIENTO"
            error = qr_centro * config.CAMARA_FOV_H / 2.0
            self.alineado = abs(error) <= config.PAN_TOLERANCIA_DEG
            if not self.alineado:
                self._poner(self.angulo + signo * config.PAN_GANANCIA * error)
            return
        self.alineado = False
        if self.modo == "SEGUIMIENTO" and self._visto is not None and ahora - self._visto < config.PAN_PERDIDA_S:
            return     # lo acaba de perder: se queda quieto un momento
        self.modo = "BARRIDO"
        lo, hi = self.cal["camara_min"], self.cal["camara_max"]
        nuevo = self.angulo + self._mov * self.cal["camara_velocidad_dps"] * dt
        if nuevo >= hi:
            nuevo, self._mov = hi, -1      # rebota solo al llegar al extremo, no al salir de él
        elif nuevo <= lo:
            nuevo, self._mov = lo, 1
        self._poner(nuevo)
