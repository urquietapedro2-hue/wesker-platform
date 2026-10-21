"""De evento a frase. Hoy son plantillas; más adelante aquí puede entrar un modelo de lenguaje sin tocar nada más."""
from vera.eventos import Evento

NODOS_HABLADOS = {"ALBERT-01": "Albert", "ZENO-01": "Zeno"}
PLANTILLAS = {
    "sesion_iniciada": "Bienvenido, {usuario}. Sistema en línea.",
    "login_fallo": "Acceso denegado.",
    "nodo_en_linea": "{nodo} en línea.",
    "nodo_sin_senal": "Atención. {nodo} sin señal.",
    "nube_perdida": "Atención. Se perdió la conexión con la nube.",
    "nube_restablecida": "Conexión con la nube restablecida.",
    "error_publicacion": "Atención. No se pudo publicar el estado de la planta.",
    "estado_invalido": "Atención. Se recibió un estado no válido y se ignoró.",
}


def redactar(evento: Evento):
    """Frase a decir, o None si ese evento no se anuncia."""
    plantilla = PLANTILLAS.get(evento.codigo)
    if plantilla is None:
        return None
    return plantilla.format(usuario=evento.usuario or "operador",
                            nodo=NODOS_HABLADOS.get(evento.nodo, evento.nodo or "El nodo"))
