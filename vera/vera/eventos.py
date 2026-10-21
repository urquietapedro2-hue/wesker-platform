"""Contrato de eventos que V.E.R.A. entiende (ver CONTRATO.md). Todo lo que llega se valida: nunca se confía."""
from dataclasses import dataclass, field

NIVELES = ("info", "warn", "error")
CODIGOS = ("sesion_iniciada", "login_fallo", "nodo_en_linea", "nodo_sin_senal", "nube_perdida",
           "nube_restablecida", "error_publicacion", "estado_invalido")


class EventoInvalido(ValueError):
    pass


@dataclass(frozen=True)
class Evento:
    codigo: str
    nivel: str = "info"
    nodo: str = ""
    usuario: str = ""
    datos: dict = field(default_factory=dict)


def _texto(valor, largo, nombre):
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise EventoInvalido(f"{nombre} debe ser texto")
    return "".join(c for c in valor if c.isprintable())[:largo]  # sin caracteres de control, longitud acotada


def validar_evento(crudo) -> Evento:
    if not isinstance(crudo, dict):
        raise EventoInvalido("el evento debe ser un objeto JSON")
    if crudo.get("v", 1) != 1:
        raise EventoInvalido("versión de contrato no soportada")
    codigo = crudo.get("codigo")
    if not isinstance(codigo, str) or codigo not in CODIGOS:
        raise EventoInvalido("código de evento desconocido")
    nivel = crudo.get("nivel", "info")
    if not isinstance(nivel, str) or nivel not in NIVELES:
        raise EventoInvalido("nivel desconocido")
    datos = crudo.get("datos", {})
    if not isinstance(datos, dict) or len(datos) > 10:
        raise EventoInvalido("datos debe ser un objeto de hasta 10 campos")
    limpios = {str(k)[:30]: (v if isinstance(v, (int, float, bool)) else str(v)[:60]) for k, v in datos.items()}
    return Evento(codigo, nivel, _texto(crudo.get("nodo"), 30, "nodo"), _texto(crudo.get("usuario"), 40, "usuario"), limpios)
