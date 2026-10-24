"""Cliente de prueba para hablar con Zeno desde una PC (el HMI aún no trae su cliente real). Solo biblioteca estándar.
Uso:  python -m zeno.cliente_prueba IP_DE_ZENO            (interactivo: escribe comandos; Ctrl+C sale)
      python -m zeno.cliente_prueba IP_DE_ZENO --token-archivo ruta_del_token
La IP la sabes por tu router o con `hostname -I` en la Raspberry. El token NUNCA se pasa por la línea de comandos."""
import argparse
import os
import socket
import sys
import threading
import time

from zeno import config


def ejecutar(host, puerto, token="", comandos=(), segundos=3.0, salida=print):
    """Conecta, se autentica si hay token, envía `comandos`, mantiene el PING y devuelve las líneas recibidas."""
    recibidas, detener = [], threading.Event()
    s = socket.create_connection((host, puerto), timeout=5)
    s.settimeout(0.3)
    enviar = lambda t: s.sendall((t + "\n").encode("utf-8"))  # noqa: E731
    if token:
        enviar("AUTH," + token)

    def latido():
        while not detener.is_set():
            try:
                enviar("PING")
            except OSError:
                return
            time.sleep(1.0)
    threading.Thread(target=latido, daemon=True).start()
    fin, buf = time.monotonic() + segundos, b""
    try:
        for c in comandos:
            enviar(c)
        while time.monotonic() < fin:
            try:
                d = s.recv(4096)
            except socket.timeout:
                continue
            except OSError:  # Zeno cerró la conexión (p. ej. token incorrecto): es un final normal, no un error
                break
            if not d:
                break
            buf += d
            while b"\n" in buf:
                linea, buf = buf.split(b"\n", 1)
                recibidas.append(linea.decode("utf-8", "replace"))
                salida(recibidas[-1])
    except OSError:
        pass
    finally:
        detener.set()
        s.close()
    return recibidas


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("--puerto", type=int, default=config.PUERTO_CONTROL)
    ap.add_argument("--token-archivo", default=config.ruta_token() if os.path.exists(config.ruta_token()) else "")
    a = ap.parse_args(argv)
    token = ""
    if a.token_archivo:
        with open(a.token_archivo, "r", encoding="utf-8") as f:
            token = f.read().strip()
    pendientes = []

    def leer_teclado():
        for linea in sys.stdin:
            pendientes.append(linea.strip())
    threading.Thread(target=leer_teclado, daemon=True).start()
    print("Conectando a %s:%d ... escribe comandos (MODE,MANUAL / F,30 / S / MODE,AUTO / RESUME) y Enter." % (a.host, a.puerto))
    try:
        while True:
            cmds, pendientes[:] = list(pendientes), []
            ejecutar(a.host, a.puerto, token, cmds, 0.5, salida=lambda t: print(t) if not t.startswith("TELEM") else None)
    except KeyboardInterrupt:
        return 0
    except OSError as ex:
        print("No se pudo conectar: %s" % ex)
        return 1


if __name__ == "__main__":
    sys.exit(main())
