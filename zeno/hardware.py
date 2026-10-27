"""Hardware de Zeno: tracción BTS7960, servos (GestorServos) y regleta de 5 sensores. Sin ángulos ni tiempos fijos: salen de la calibración. Mismo comportamiento que ZENO_V2; la dirección usa GestorServos.
`gpio` se inyecta en las pruebas; en la Raspberry se importa RPi.GPIO."""
import threading
import time

from zeno import config
from zeno.servos import GestorServos


class Hardware:
    def __init__(self, cal, gpio=None, servos=None):
        if gpio is None:
            import RPi.GPIO as gpio  # solo existe en la Raspberry
        self.g, self.cal = gpio, cal
        gpio.setmode(gpio.BCM)
        gpio.setwarnings(False)
        gpio.setup(config.PIN_RPWM, gpio.OUT)
        gpio.setup(config.PIN_LPWM, gpio.OUT)
        self.pwm_fwd, self.pwm_rev = gpio.PWM(config.PIN_RPWM, 1000), gpio.PWM(config.PIN_LPWM, 1000)
        self.pwm_fwd.start(0)
        self.pwm_rev.start(0)
        for pin in config.PINS_LINEA:
            gpio.setup(pin, gpio.IN, pull_up_down=gpio.PUD_OFF)
        self.servos = servos if servos is not None else GestorServos(gpio=gpio, cal=cal)   # PCA9685 con respaldo GPIO
        self._lock = threading.Lock()
        self.estado_movimiento, self.velocidad_actual = "S", 0
        self.angulo_servo, self.sensores = cal["direccion_centro"], [0, 0, 0, 0, 0]
        self.fijar_angulo(cal["direccion_centro"])

    # ---- dirección ----
    def fijar_angulo(self, angulo):
        self.servos.mover("direccion", float(angulo), esperar_s=self.cal["direccion_pausa_s"])   # trim, límites y soltado: en GestorServos
        self.angulo_servo = angulo

    def angulo_de(self, direccion):
        """Ángulo calibrado de cada giro: izquierda = máximo, derecha = mínimo (se intercambian con direccion_invertida)."""
        c = self.cal
        if direccion == "L":
            return c["direccion_min"] if c["direccion_invertida"] else c["direccion_max"]
        if direccion == "R":
            return c["direccion_max"] if c["direccion_invertida"] else c["direccion_min"]
        return c["direccion_centro"]

    # ---- tracción (misma lógica que aplicar_traccion de V2) ----
    def traccion(self, comando, velocidad=45):
        with self._lock:
            if comando == "S" and self.estado_movimiento == "S":
                return
            v = max(0, min(100, int(velocidad)))
            if comando == "S":
                self.pwm_fwd.ChangeDutyCycle(0)
                self.pwm_rev.ChangeDutyCycle(0)
                self.fijar_angulo(self.angulo_de("F"))
                self.estado_movimiento, self.velocidad_actual = "S", 0
                return
            if comando == "B":
                self.pwm_fwd.ChangeDutyCycle(0)
                if self.estado_movimiento != "B":
                    self.fijar_angulo(self.angulo_de("F"))
                self.pwm_rev.ChangeDutyCycle(v)
            elif comando in ("F", "L", "R"):
                self.pwm_rev.ChangeDutyCycle(0)
                if self.estado_movimiento != comando:
                    self.fijar_angulo(self.angulo_de(comando))
                self.pwm_fwd.ChangeDutyCycle(v)
            else:
                return
            self.estado_movimiento, self.velocidad_actual = comando, v

    def parar_duro(self):
        """Paro de emergencia: cortes de PWM SIEMPRE, sin esperar a la dirección ni mirar el estado guardado."""
        self.pwm_fwd.ChangeDutyCycle(0)
        self.pwm_rev.ChangeDutyCycle(0)
        self.estado_movimiento, self.velocidad_actual = "S", 0

    def pulso(self, direccion, velocidad, duracion_ms):
        """Pulso de diagnóstico en segundo plano (igual que V2; la duración ya viene limitada por el protocolo)."""
        def _pulso():
            if direccion in ("L", "R"):
                self.fijar_angulo(self.angulo_de(direccion))
                time.sleep(duracion_ms / 1000.0)
                self.fijar_angulo(self.angulo_de("F"))
            else:
                self.traccion(direccion, velocidad)
                time.sleep(max(50, duracion_ms) / 1000.0)
                self.traccion("S", 0)
        threading.Thread(target=_pulso, daemon=True).start()

    # ---- sensores ----
    def leer_sensores(self):
        lecturas = []
        for pin in config.PINS_LINEA:
            v = self.g.input(pin)
            lecturas.append((1 if v == 0 else 0) if config.INVERTIR_LOGICA else v)
        self.sensores = lecturas
        return lecturas

    def cerrar(self):
        self.parar_duro()
        for pwm in (self.pwm_fwd, self.pwm_rev):
            pwm.stop()
        self.servos.cerrar()
        self.g.cleanup()
