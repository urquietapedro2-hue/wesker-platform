"""Simuladores de nodos. Sin Qt: se prueban solos y producen datos con la misma forma que el hardware real,
así que más adelante el nodo real (o la nube) ocupará su lugar sin tocar las pantallas."""


class ZenoSimulator:
    """Recorrido de ZENO-01: rectas, curvas, parada en estación (QR) y obstáculos.
    tick() devuelve exactamente los argumentos de ZenoDigitalTwin.set_telemetria()."""

    # (segmento, segundos, dirección, PWM %, sensores BFD-1000 S1..S5, subestado, QR)
    RUTA = (
        ("recta", 4.0, "F", 60, (0, 0, 1, 0, 0), "SEGUIMIENTO", "NINGUNO"),
        ("curva izquierda", 2.0, "L", 45, (1, 1, 0, 0, 0), "SEGUIMIENTO", "NINGUNO"),
        ("recta", 3.0, "F", 60, (0, 0, 1, 0, 0), "SEGUIMIENTO", "NINGUNO"),
        ("curva derecha", 2.0, "R", 45, (0, 0, 0, 1, 1), "SEGUIMIENTO", "NINGUNO"),
        ("recta", 3.0, "F", 55, (0, 0, 1, 0, 0), "SEGUIMIENTO", "NINGUNO"),
        ("estación", 5.0, "S", 0, (0, 0, 1, 0, 0), "ESTACION_DESCARGA", "ESTACION_2"),
    )
    DISTANCIA_LIBRE = 85.0      # cm
    DISTANCIA_OBSTACULO = 18.0  # cm (el gemelo pinta el cono en rojo por debajo de 35)

    def __init__(self):
        self.reset()

    def reset(self):
        self.t = 0.0
        self.obstaculo_restante = 0.0
        self.segmento = self.RUTA[0][0]
        self.vueltas = 0

    @property
    def duracion_vuelta(self) -> float:
        return sum(seg[1] for seg in self.RUTA)

    def provocar_obstaculo(self, segundos: float = 4.0):
        self.obstaculo_restante = max(0.0, float(segundos))

    def tick(self, dt: float, escala: float = 1.0) -> dict:
        dt = max(0.0, dt) * max(0.0, escala)
        if self.obstaculo_restante > 0.0:  # el recorrido se congela mientras haya obstáculo
            self.obstaculo_restante = max(0.0, self.obstaculo_restante - dt)
            return self._salida("obstáculo", "S", 0, self.DISTANCIA_OBSTACULO, (0, 0, 1, 0, 0), "SEGUIMIENTO", "NINGUNO")
        self.t += dt
        total = self.duracion_vuelta
        self.vueltas = int(self.t // total)
        pos = self.t % total
        for nombre, dur, direccion, pwm, sensores, subestado, qr in self.RUTA:
            if pos < dur:
                break
            pos -= dur
        return self._salida(nombre, direccion, pwm, self.DISTANCIA_LIBRE, sensores, subestado, qr)

    def _salida(self, nombre, direccion, pwm, distancia, sensores, subestado, qr) -> dict:
        self.segmento = nombre
        return {"direccion": direccion, "velocidad": pwm, "distancia": distancia,
                "sensores": list(sensores), "subestado": subestado, "qr": qr}


class AlbertSimulator:
    """Marca el ritmo de la estrella de Albert: un paso de 45° cada `periodo` segundos.
    El propio gemelo simula el resto (soltar vaso, dosificar, tapa, sellado, descarga)."""

    PERIODO_MIN = 8.0  # el sellado del gemelo dura ~7 s y debe terminar antes del siguiente paso
    PRIMER_PASO = 3.0  # tras iniciar, el primer paso llega pronto

    def __init__(self, periodo: float = PERIODO_MIN):
        self.activo = False
        self.periodo = max(self.PERIODO_MIN, float(periodo))
        self._acum = 0.0

    def set_periodo(self, segundos: float):
        self.periodo = max(self.PERIODO_MIN, float(segundos))

    def iniciar(self):
        self.activo = True
        self._acum = max(0.0, self.periodo - self.PRIMER_PASO)

    def detener(self):
        self.activo = False

    @property
    def restante(self) -> float:
        return max(0.0, self.periodo - self._acum)

    def tick(self, dt: float) -> int:
        """Pasos que toca dar ahora (0 o 1: nunca acumula pasos atrasados)."""
        if not self.activo:
            return 0
        self._acum += max(0.0, dt)
        if self._acum >= self.periodo:
            self._acum = 0.0
            return 1
        return 0
