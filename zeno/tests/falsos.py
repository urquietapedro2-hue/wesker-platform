"""Piezas falsas para probar Zeno en una PC: GPIO, cámara y cv2."""
import threading


class FakePWM:
    def __init__(self, pin, freq):
        self.pin, self.freq, self.duty, self.historial, self.detenido = pin, freq, None, [], False

    def start(self, d):
        self.duty = d
        self.historial.append(d)

    def ChangeDutyCycle(self, d):
        self.duty = d
        self.historial.append(d)

    def stop(self):
        self.detenido = True


class FakeGPIO:
    BCM, OUT, IN, PUD_OFF = "BCM", "OUT", "IN", "OFF"

    def __init__(self):
        self.entradas, self.pwms, self.limpio = {}, {}, False

    def setmode(self, m): pass
    def setwarnings(self, f): pass
    def setup(self, *a, **k): pass

    def PWM(self, pin, freq):
        self.pwms[pin] = FakePWM(pin, freq)
        return self.pwms[pin]

    def input(self, pin):
        return self.entradas.get(pin, 1)  # 1 = blanco (con la lógica invertida eso lee 0)

    def cleanup(self):
        self.limpio = True


class FakeCamara:
    def __init__(self):
        self.qr, self.inicios, self.paros = "NINGUNO", 0, 0

    def start(self): self.inicios += 1
    def stop(self): self.paros += 1


class FakeCapture:
    def __init__(self, cuadros=10 ** 6): self.cuadros, self.liberada = cuadros, False
    def isOpened(self): return True
    def set(self, *a): return True
    def release(self): self.liberada = True

    def read(self):
        self.cuadros -= 1
        return self.cuadros >= 0, b"cuadro"


class FakeDetector:
    def __init__(self, respuestas): self.respuestas = list(respuestas)

    def detectAndDecode(self, frame):
        r = self.respuestas.pop(0) if self.respuestas else ""
        if isinstance(r, Exception):
            raise r
        return r, None, None


class FakeCv2:
    CAP_V4L2 = CAP_PROP_FOURCC = CAP_PROP_FRAME_WIDTH = CAP_PROP_FRAME_HEIGHT = CAP_PROP_FPS = 1
    FONT_HERSHEY_SIMPLEX, IMWRITE_JPEG_QUALITY = 0, 1

    def __init__(self, respuestas=()):
        self._respuestas, self.codificados, self.captura = respuestas, 0, FakeCapture()

    def QRCodeDetector(self): return FakeDetector(self._respuestas)
    def VideoCapture(self, idx, api): return self.captura
    def VideoWriter_fourcc(self, *a): return 0
    def putText(self, *a, **k): pass
    def line(self, *a, **k): pass

    def imencode(self, ext, frame, params):
        self.codificados += 1
        return True, type("J", (), {"tobytes": lambda s: b"JPEG"})()


def esperar(condicion, segundos=3.0, paso=0.02):
    import time
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(paso)
    return condicion()
