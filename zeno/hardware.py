"""Hardware de Zeno: tracción BTS7960, servo MG995 y regleta de 5 sensores. Mismo comportamiento que ZENO_V2.
`gpio` se inyecta en las pruebas; en la Raspberry se importa RPi.GPIO."""
import threading
import time

from zeno import config


class Hardware:
    def __init__(self, gpio=None, pausa_servo=config.PAUSA_SERVO_S):
        if gpio is None:
            import RPi.GPIO as gpio  # solo existe en la Raspberry
        self.g, self.pausa_servo = gpio, pausa_servo
        gpio.setmode(gpio.BCM)
        gpio.setwarnings(False)
        gpio.setup(config.PIN_RPWM, gpio.OUT)
        gpio.setup(config.PIN_LPWM, gpio.OUT)
        self.pwm_fwd, self.pwm_rev = gpio.PWM(config.PIN_RPWM, 1000), gpio.PWM(config.PIN_LPWM, 1000)
        self.pwm_fwd.start(0)
        self.pwm_rev.start(0)
        gpio.setup(config.PIN_SERVO, gpio.OUT)
        self.pwm_servo = gpio.PWM(config.PIN_SERVO, 50)
        self.pwm_servo.start(0)
        for pin in config.PINS_LINEA:
            gpio.setup(pin, gpio.IN, pull_up_down=gpio.PUD_OFF)
        self._lock = threading.Lock()
        self.estado_movimiento, self.velocidad_actual = "S", 0
        self.angulo_servo, self.sensores = 90.0, [0, 0, 0, 0, 0]
        self.fijar_angulo(90.0)

    # ---- dirección ----
    def fijar_angulo(self, angulo):
        corregido = max(45.0, min(135.0, float(angulo) + config.OFFSET_SERVO_TRIM))
        self.pwm_servo.ChangeDutyCycle(2.5 + corregido / 18.0)
        self.angulo_servo = angulo
        time.sleep(self.pausa_servo)
        self.pwm_servo.ChangeDutyCycle(0)

    # ---- tracción (misma lógica que aplicar_traccion de V2) ----
    def traccion(self, comando, velocidad=45):
        with self._lock:
            if comando == "S" and self.estado_movimiento == "S":
                return
            v = max(0, min(100, int(velocidad)))
            if comando == "S":
                self.pwm_fwd.ChangeDutyCycle(0)
                self.pwm_rev.ChangeDutyCycle(0)
                self.fijar_angulo(config.ANGULO_CENTRO)
                self.estado_movimiento, self.velocidad_actual = "S", 0
                return
            if comando == "B":
                self.pwm_fwd.ChangeDutyCycle(0)
                if self.estado_movimiento != "B":
                    self.fijar_angulo(config.ANGULO_CENTRO)
                self.pwm_rev.ChangeDutyCycle(v)
            elif comando in ("F", "L", "R"):
                self.pwm_rev.ChangeDutyCycle(0)
                if self.estado_movimiento != comando:
                    self.fijar_angulo({"F": config.ANGULO_CENTRO, "L": config.ANGULO_IZQ, "R": config.ANGULO_DER}[comando])
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
                self.fijar_angulo(config.ANGULO_IZQ if direccion == "L" else config.ANGULO_DER)
                time.sleep(duracion_ms / 1000.0)
                self.fijar_angulo(config.ANGULO_CENTRO)
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
        for pwm in (self.pwm_fwd, self.pwm_rev, self.pwm_servo):
            pwm.stop()
        self.g.cleanup()
