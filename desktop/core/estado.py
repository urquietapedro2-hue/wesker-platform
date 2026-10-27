"""Validación del estado que llega de la nube (sin Qt). Lo publica otra persona, así que nunca se confía en él:
cada campo se comprueba (tipo, rango, valores permitidos) y lo inválido se descarta. Nunca lanza excepciones."""

VASOS = {None, "VACIO", "NEGRO", "PINTO", "PERUANO"}
FRIJOLES = {None, "NEGRO", "PINTO", "PERUANO"}
RECETAS = {"PINTO", "NEGRO", "PERUANO", "ROTATIVO", "DOBLE", "ALEATORIO", "3NEGRO_1PINTO", "BICOLOR", "GOURMET"}
MODOS = {"AUTO", "MANUAL"}
ESTACION1 = {"STANDBY", "DISPENSING", "SIN_VASOS"}
FASES = {"REPOSO", "ABRIENDO", "VERTIDO", "BARRIDO_CIERRE"}
DIRECCIONES = {"F", "B", "L", "R", "FL", "FR", "BL", "BR", "S", "ESTACION"}
SUBESTADOS = {"SEGUIMIENTO", "ESTACION_DESCARGA"}


def _real(v, lo, hi):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:  # texto, listas o NaN
        return None
    return max(lo, min(hi, float(v)))


def _entero(v, lo, hi):
    r = _real(v, lo, hi)
    return None if r is None else int(r)


def _enum(v, permitidos):
    return v if isinstance(v, (str, type(None))) and v in permitidos else None


def _texto(v, largo):
    return v[:largo] if isinstance(v, str) else None


def _bool(v):
    return v if isinstance(v, bool) else None


_NO = object()  # «este elemento no es válido» (distinto de None, que en las casillas de vaso SÍ es un valor válido)


def _lista(v, largo, conv, defecto):
    """Lista de exactamente `largo` elementos; cada uno pasa por `conv` y, si devuelve _NO, toma `defecto`."""
    if not isinstance(v, list) or len(v) != largo:
        return None
    return [defecto if (c := conv(x)) is _NO else c for x in v]


def _booleano(x):
    return x if isinstance(x, bool) else _NO


def _real_o_no(x, lo, hi):
    r = _real(x, lo, hi)
    return _NO if r is None else r


def _poner(salida, clave, valor):
    if valor is not None:
        salida[clave] = valor


def sanear_albert(e) -> dict:
    """Devuelve solo los campos válidos del estado de Albert (los que falten conservan su valor actual)."""
    if not isinstance(e, dict):
        return {}
    s = {}
    _poner(s, "modo", _enum(e.get("modo"), MODOS))
    _poner(s, "receta", _enum(e.get("receta"), RECETAS))
    _poner(s, "dinamica", _bool(e.get("dinamica")))
    _poner(s, "resumen", _texto(e.get("resumen"), 200))
    _poner(s, "motor", _texto(e.get("motor"), 40))
    _poner(s, "ang_obj", _real(e.get("ang_obj"), -1e7, 1e7))
    _poner(s, "silo", _entero(e.get("silo"), 0, 99))
    _poner(s, "slots", _lista(e.get("slots"), 8, lambda x: x if isinstance(x, (str, type(None))) and x in VASOS else _NO, "VACIO"))
    _poner(s, "tapas", _lista(e.get("tapas"), 8, _booleano, False))
    _poner(s, "terminados", _entero(e.get("terminados"), 0, 10 ** 9))
    _poner(s, "est1", _enum(e.get("est1"), ESTACION1))
    _poner(s, "tolva", _real(e.get("tolva"), 0.0, 100.0))
    if isinstance(e.get("tipo_tolva"), (str, type(None))) and e.get("tipo_tolva") in FRIJOLES and "tipo_tolva" in e:
        s["tipo_tolva"] = e["tipo_tolva"]  # None es un valor válido (tolva sin grano)
    _poner(s, "servo_tolva", _bool(e.get("servo_tolva")))
    _poner(s, "servos", _lista(e.get("servos"), 3, _booleano, False))
    _poner(s, "fase", _enum(e.get("fase"), FASES))
    _poner(s, "silo_desc", _entero(e.get("silo_desc"), -1, 2))
    _poner(s, "comp_obj", _lista(e.get("comp_obj"), 3, lambda x: _real_o_no(x, -10.0, 180.0), 0.0))
    sel = e.get("silos_sel")
    if isinstance(sel, list) and len(sel) <= 3:
        s["silos_sel"] = [i for i in (_entero(x, 0, 2) for x in sel) if i is not None]
    _poner(s, "tapa_obj", _real(e.get("tapa_obj"), -10.0, 190.0))
    _poner(s, "tapa_anim", _bool(e.get("tapa_anim")))
    _poner(s, "piston_obj", _real(e.get("piston_obj"), 0.0, 1.0))
    _poner(s, "sellando", _bool(e.get("sellando")))
    _poner(s, "corriendo", _bool(e.get("corriendo")))
    _poner(s, "restante", _real(e.get("restante"), 0.0, 3600.0))
    return s


def sanear_logistica(d):
    """Estado de la ruta de Zeno (fase, cargas de rampas, servos) publicado por otra persona. None si no hay o no es válido."""
    from core.zeno_enlace import ALARMAS, BACKENDS, ESTACIONES, FASES as FASES_RUTA, NOMBRES_SERVO
    if not isinstance(d, dict):
        return None
    fase = _enum(d.get("fase"), FASES_RUTA)
    if fase is None:
        return None
    est = d.get("estacion")
    servos = d.get("servos") if isinstance(d.get("servos"), dict) else {}
    return {"fase": fase, "estacion": est if est in ESTACIONES else "NINGUNA",
            "carga_r1": d.get("carga_r1") is True, "carga_r2": d.get("carga_r2") is True,
            "alarma": _enum(d.get("alarma"), ALARMAS) or "NINGUNA", "restante_s": _real(d.get("restante_s"), 0.0, 3600.0) or 0.0,
            "backend": _enum(d.get("backend"), BACKENDS) or "NINGUNO", "i2c": d.get("i2c") is True,
            "servos": {n: _real(servos.get(n), 0.0, 180.0) for n in NOMBRES_SERVO}}


def sanear_zeno(e) -> dict:
    """Devuelve la telemetría de Zeno lista para set_telemetria() (siempre completa y válida)."""
    e = e if isinstance(e, dict) else {}
    sens = e.get("sens")
    sens = [1 if (x is True or x == 1) else 0 for x in sens] if isinstance(sens, list) and len(sens) == 5 else [0] * 5
    dist = _real(e.get("dist"), 0.0, 500.0)
    qr = e.get("qr")
    return {
        "modo": _enum(e.get("modo"), MODOS) or "AUTO",
        "direccion": _enum(e.get("dir"), DIRECCIONES) or "S",
        "velocidad": _entero(e.get("pwm"), 0, 100) or 0,
        "distancia": 85.0 if dist is None else dist,
        "sensores": sens,
        "subestado": _enum(e.get("sub"), SUBESTADOS) or "SEGUIMIENTO",
        "qr": qr[:24] if isinstance(qr, str) and qr else "NINGUNO",
        "tramo": _texto(e.get("seg"), 30) or "",
        "corriendo": e.get("corriendo") is True,
        "origen": "real" if e.get("origen") == "real" else "simulacion",
        "logistica": sanear_logistica(e.get("logi")),
    }
