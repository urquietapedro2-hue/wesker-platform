"""Uso:  python -m vera                      arranca el servicio (muestra en consola cada evento y cada error)
        python -m vera --diagnostico        busca por qué la voz no suena (no imprime claves)
        python -m vera --guardar-secretos   guarda clave y voz CIFRADAS para tu cuenta de Windows
        python -m vera --migrar-env         cifra lo que haya en tu .env y destruye el .env
        python -m vera --borrar-secretos    elimina el almacén cifrado
        python -m vera --probar "Hola"      sintetiza y reproduce una frase y termina"""
import argparse
import getpass
import logging
import os
import secrets
import sys
from pathlib import Path

from vera import __version__, local
from vera.cache import CacheAudio
from vera.config import CAMPOS_SECRETOS, Config, ConfigError, candidatos_dotenv, encontrar_dotenv, leer_dotenv
from vera.diagnostico import _enmascarar, diagnosticar
from vera.nucleo import Vera
from vera.salida import crear_reproductor
from vera.secretos import Almacen, SecretosError, destruir
from vera.servidor import crear_servidor
from vera.voz import crear_motor
from vera.voz.base import VozError
from vera.voz.elevenlabs import ID_VALIDO


def _carpeta_cache(cfg):
    if cfg.cache_dir:
        return cfg.cache_dir
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return str(Path(base) / "WESKER" / "vera_cache")


def _guardar_secretos(almacen) -> int:
    print("Los datos se guardan CIFRADOS para tu cuenta de Windows. Lo que escribas como clave no se muestra.")
    clave = getpass.getpass("Clave (API key) de ElevenLabs: ").strip()
    voz = input("voice_id de la voz: ").strip()
    modelo = input("Modelo [eleven_multilingual_v2]: ").strip() or "eleven_multilingual_v2"
    if len(clave) < 10:
        print("La clave parece vacía o demasiado corta. No se guardó nada.")
        return 1
    if not ID_VALIDO.match(voz):
        print("El voice_id no tiene un formato válido (alfanumérico, 10 a 40 caracteres). No se guardó nada.")
        return 1
    almacen.guardar({**almacen.cargar(), "motor": "elevenlabs", "api_key": clave, "voice_id": voz, "model_id": modelo})
    print(f"Guardado cifrado en {almacen.ruta}\nSiguiente paso: python -m vera --diagnostico")
    return 0


def _migrar_env(almacen) -> int:
    ruta = encontrar_dotenv()
    if ruta is None:
        print("No se encontró ningún .env. Buscado en:\n  " + "\n  ".join(str(r) for r in candidatos_dotenv()))
        return 1
    valores, _, _ = leer_dotenv(ruta)
    datos = {campo: valores[nombre].strip() for nombre, campo in CAMPOS_SECRETOS.items() if (valores.get(nombre) or "").strip()}
    if not datos.get("api_key"):
        print(f"{ruta} no contiene ELEVENLABS_API_KEY: no hay nada que cifrar. El archivo NO se tocó.")
        return 1
    almacen.guardar({**almacen.cargar(), **datos})
    if almacen.cargar().get("api_key") != datos["api_key"]:  # se comprueba ANTES de destruir el original
        print("No se pudo verificar el almacén cifrado. El .env NO se tocó.")
        return 1
    destruir(ruta)
    print(f"Cifrado en {almacen.ruta}\nEl archivo {ruta} fue sobrescrito y borrado.")
    if "onedrive" in str(ruta).lower():
        print("ATENCIÓN: ese .env estaba dentro de OneDrive, que ya pudo haber guardado copias en la nube.\n"
              "Crea una clave nueva en el panel de ElevenLabs, deja sin efecto la anterior y ejecuta --guardar-secretos.")
    else:
        print("Recomendado: crea una clave nueva en el panel de ElevenLabs y ejecuta --guardar-secretos con ella.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--diagnostico", action="store_true")
    g.add_argument("--guardar-secretos", action="store_true")
    g.add_argument("--migrar-env", action="store_true")
    g.add_argument("--borrar-secretos", action="store_true")
    g.add_argument("--probar", metavar="TEXTO")
    ap.add_argument("--puerto", type=int, help="puerto local (por defecto VERA_PUERTO, 0 = libre)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    almacen = Almacen()
    try:
        if args.guardar_secretos:
            return _guardar_secretos(almacen)
        if args.migrar_env:
            return _migrar_env(almacen)
        if args.borrar_secretos:
            almacen.borrar()
            print("Almacén cifrado eliminado.")
            return 0
        cfg, info = Config.resolver(almacen=almacen)
        motor = crear_motor(cfg)
    except (ConfigError, VozError, SecretosError) as ex:
        print(f"Configuración inválida: {ex}")
        return 2
    reproductor = crear_reproductor()
    if args.diagnostico:
        return diagnosticar(cfg, info, motor, reproductor, local.consultar_estado)
    if args.probar:
        try:
            audio = motor.sintetizar(args.probar)
        except VozError as ex:
            print(f"No se pudo sintetizar: {ex}")
            return 1
        if not audio.datos:
            print("El motor activo es «silencioso»: no genera voz. Ejecuta: python -m vera --diagnostico")
            return 1
        reproductor.reproducir(audio)
        return 0

    vera = Vera(motor, reproductor, CacheAudio(_carpeta_cache(cfg), cfg.cache_max_mb), cfg.enfriamiento_s)
    token = secrets.token_urlsafe(24)  # nuevo en cada arranque; no se imprime
    servidor = crear_servidor(vera, token, cfg.puerto if args.puerto is None else args.puerto)
    puerto = servidor.server_address[1]
    local.publicar(puerto, token)
    vera.iniciar()
    print(f"V.E.R.A. {__version__} | motor: {motor.nombre} (origen: {info.origenes.get('VERA_MOTOR')}) | escuchando solo en 127.0.0.1:{puerto}")
    if cfg.voice_id:
        print(f"voz: {_enmascarar(cfg.voice_id)} | modelo: {cfg.model_id}")
    for aviso in info.avisos:
        print(f"AVISO: {aviso}")
    if motor.nombre == "silencioso":
        print("AVISO: MOTOR SILENCIOSO: V.E.R.A. NO HABLARÁ. Ejecuta en otra terminal: python -m vera --diagnostico")
    print("Ctrl+C para salir. Cada evento recibido y cada error aparecerán aquí.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        local.retirar()
        servidor.server_close()
        vera.detener()
    return 0


if __name__ == "__main__":
    sys.exit(main())
