"""Genera sonidos de ejemplo PROPIOS (tonos sintéticos) para los eventos de la app. Solo usa la biblioteca estándar.
Tus propios archivos, con el mismo nombre en assets/sonidos/ o en %APPDATA%/WESKER/sonidos/, los reemplazan.
Uso:  python scripts/generar_sonidos_base.py [--salida desktop/assets/sonidos/base]"""
import argparse
import math
import os
import struct
import wave

FRECUENCIA = 44100


def tono(hz, ms, amplitud=0.35, forma="seno"):
    n = int(FRECUENCIA * ms / 1000)
    muestras = []
    for i in range(n):
        fase = 2 * math.pi * hz * i / FRECUENCIA
        v = math.sin(fase) if forma == "seno" else (1.0 if math.sin(fase) >= 0 else -1.0) * 0.6
        envolvente = min(1.0, i / (0.008 * FRECUENCIA), (n - i) / (0.02 * FRECUENCIA))  # entrada y salida suaves
        muestras.append(int(32767 * amplitud * v * envolvente))
    return muestras


def silencio(ms):
    return [0] * int(FRECUENCIA * ms / 1000)


SONIDOS = {
    "login_ok": tono(660, 90) + silencio(30) + tono(880, 150),                       # dos notas ascendentes
    "login_fallo": tono(180, 130, forma="cuadrada") + silencio(70) + tono(180, 180, forma="cuadrada"),
    "error_sistema": tono(880, 110) + silencio(50) + tono(660, 110) + silencio(50) + tono(440, 220),  # descendente
}


def guardar(salida):
    os.makedirs(salida, exist_ok=True)
    for nombre, muestras in SONIDOS.items():
        with wave.open(os.path.join(salida, f"{nombre}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(FRECUENCIA)
            w.writeframes(struct.pack(f"<{len(muestras)}h", *muestras))
    return sorted(os.listdir(salida))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--salida", default=os.path.join("desktop", "assets", "sonidos", "base"))
    print(guardar(ap.parse_args().salida))
