"""`python -m vera --diagnostico`: comprueba una por una las causas por las que la voz puede no sonar y dice cuál falla.
Nunca imprime claves; solo si están presentes y de dónde salieron."""
import time

from vera.voz.base import VozError, VozNoDisponible, VozTemporal
from vera.voz.elevenlabs import ID_VALIDO


def _enmascarar(valor: str) -> str:
    return valor if len(valor) <= 8 else f"{valor[:4]}…{valor[-4:]}"


def diagnosticar(cfg, info, motor, reproductor, estado_servicio, salida=print) -> int:
    """Devuelve 0 si no hay fallas, 1 si las hay. `estado_servicio()` -> dict | None."""
    fallas = []

    def linea(nivel, texto):
        salida(f"[{nivel}] {texto}")
        if nivel == "FALLA":
            fallas.append(texto)

    o = info.origenes
    if info.ruta_env:
        linea("INFO", f".env leído: {info.ruta_env} (codificación: {info.codificacion_env})")
    else:
        linea("INFO", ".env no encontrado. Buscado en: " + "; ".join(info.buscado_en[:7]) if info.buscado_en else ".env no buscado")
    linea("INFO", "Almacén cifrado: " + ("existe y se descifró" if info.almacen_existe else "no existe (usa --guardar-secretos)"))
    for aviso in info.avisos:
        linea("AVISO", aviso)

    if cfg.motor == "silencioso":
        causa = ("VERA_MOTOR no está definido en el entorno, en el almacén cifrado ni en un .env, así que se usa el valor por defecto"
                 if o.get("VERA_MOTOR") == "valor por defecto" else f"VERA_MOTOR=silencioso (origen: {o.get('VERA_MOTOR')})")
        linea("FALLA", f"Motor efectivo: SILENCIOSO. V.E.R.A. NO hablará. Causa: {causa}.")
        salida(f"\nResultado: {len(fallas)} falla(s).")
        return 1
    linea("OK", f"Motor: {cfg.motor} (origen: {o.get('VERA_MOTOR')})")
    linea("OK" if cfg.api_key else "FALLA", f"Clave del proveedor: {'presente' if cfg.api_key else 'AUSENTE'} (origen: {o.get('ELEVENLABS_API_KEY')})")
    if ID_VALIDO.match(cfg.voice_id or ""):
        linea("OK", f"voice_id con formato válido: {_enmascarar(cfg.voice_id)} (origen: {o.get('VERA_VOICE_ID')})")
    else:
        linea("FALLA", "voice_id ausente o con formato no válido (debe ser alfanumérico, 10 a 40 caracteres).")
    linea("INFO", f"Modelo: {cfg.model_id} (origen: {o.get('VERA_MODEL_ID')})")

    audio = None
    if not fallas:
        t0 = time.monotonic()
        try:
            audio = motor.sintetizar("Prueba de voz de V.E.R.A.")
            linea("OK", f"El proveedor respondió: {len(audio.datos)} bytes de audio en {time.monotonic() - t0:.1f} s")
        except VozTemporal as ex:
            linea("AVISO", f"Fallo pasajero del proveedor: {ex}")
        except (VozNoDisponible, VozError) as ex:
            linea("FALLA", f"El proveedor rechazó la petición: {ex}")
    if audio is not None and audio.datos:
        try:
            reproductor.reproducir(audio)
            linea("OK", "Audio enviado a la salida de Windows. Si no lo escuchaste, revisa el volumen y el dispositivo de salida predeterminado.")
        except Exception as ex:
            linea("FALLA", f"No se pudo reproducir el audio localmente ({type(ex).__name__}).")

    estado = estado_servicio()
    if estado is None:
        linea("INFO", "V.E.R.A. no está en ejecución en este momento (normal si solo diagnosticas).")
    else:
        linea("INFO", f"V.E.R.A. en ejecución: motor={estado.get('motor')}, en_pausa={estado.get('en_pausa')}, "
                      f"último error: {estado.get('ultimo_error') or 'ninguno'}")
    salida(f"\nResultado: {'sin fallas' if not fallas else f'{len(fallas)} falla(s)'}.")
    return 1 if fallas else 0
