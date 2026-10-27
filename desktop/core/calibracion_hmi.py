"""Lógica del panel de calibración del HMI (sin Qt, para probarla sin ventanas): agrupa el esquema que manda Zeno, arma los comandos
y junta las ediciones rápidas (arrastrar un control) en un solo CAL_SET por parámetro. El HMI no conoce rangos ni valores de fábrica:
todo viene del esquema de Zeno, así que un parámetro nuevo en Zeno aparece solo en el panel."""


def agrupar(esquema):
    """[(grupo, [parámetros])] conservando el orden en que Zeno los declara."""
    grupos = {}
    for p in esquema or []:
        grupos.setdefault(p["grupo"], []).append(p)
    return list(grupos.items())


def formatear_valor(p, valor):
    """Texto del valor para el comando, ya acotado al rango del esquema (el servidor vuelve a validar)."""
    if p["tipo"] == "bool":
        return "true" if valor else "false"
    n = max(p["min"], min(p["max"], float(valor)))
    return str(int(round(n))) if p["tipo"] == "int" else ("%.3f" % n).rstrip("0").rstrip(".")


def cmd_set(p, valor):
    return "CAL_SET,%s,%s" % (p["clave"], formatear_valor(p, valor))


def cmd_probar(p, valor):
    """Mueve el servo del parámetro a ese ángulo (solo MANUAL). None si el parámetro no tiene servo asociado."""
    if not p.get("probar"):
        return None
    return "CAL_PROBAR,%s,%d" % (p["probar"], int(round(max(0.0, min(180.0, float(valor))))))


def diferencias(esquema, valores, base):
    """Claves cuyo valor cambió respecto a `base` (para marcar lo editado)."""
    return [p["clave"] for p in esquema if p["clave"] in valores and p["clave"] in base and valores[p["clave"]] != base[p["clave"]]]


class Acumulador:
    """Junta las ediciones: por cada parámetro solo cuenta el último valor, y se entrega cuando pasó `silencio_s` sin cambios.
    Así arrastrar una barra no manda cien comandos."""

    def __init__(self, silencio_s=0.25):
        self.silencio_s, self._pend, self._t = silencio_s, {}, {}

    def editar(self, p, valor, ahora):
        self._pend[p["clave"]] = (p, valor)
        self._t[p["clave"]] = ahora

    def listos(self, ahora):
        """Comandos CAL_SET que ya pueden salir (y los quita de la cola)."""
        salida = []
        for clave in [k for k, t in self._t.items() if ahora - t >= self.silencio_s]:
            p, valor = self._pend.pop(clave)
            del self._t[clave]
            salida.append(cmd_set(p, valor))
        return salida

    def pendiente(self, clave=None):
        return bool(self._pend) if clave is None else clave in self._pend

    def descartar(self):
        self._pend.clear()
        self._t.clear()
