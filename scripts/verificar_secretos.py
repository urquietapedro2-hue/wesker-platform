"""Bloquea commits que contengan secretos. Nunca imprime el secreto: solo el archivo y la regla que saltó.
Uso:  python scripts/verificar_secretos.py                 revisa lo que está en el área de preparación (staged)
      python scripts/verificar_secretos.py --todo          revisa todos los archivos que git rastrea
      python scripts/verificar_secretos.py --instalar-hook instala el hook pre-commit para que corra solo"""
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

MARCA_HOOK = "# WESKER-verificar-secretos"
EXTENSIONES_PROHIBIDAS = {".pem", ".key", ".pfx", ".p12"}
LIMITE = 1_000_000  # bytes: no se revisa el contenido de archivos mayores
REGLAS = {
    "token de Telegram": re.compile(rb"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    "clave de ElevenLabs (sk_...)": re.compile(rb"\bsk_[0-9a-f]{24,}\b"),
    "llave privada": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "clave secreta de Supabase": re.compile(rb"\bsb_secret_[A-Za-z0-9_-]{10,}"),
}
JWT = re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


def nombre_prohibido(ruta: str):
    """Motivo si el NOMBRE del archivo ya es sospechoso, o None."""
    base = ruta.replace("\\", "/").rsplit("/", 1)[-1]
    if base == ".env.example":
        return None
    if base == ".env" or base.startswith(".env."):
        return "archivo .env (guarda secretos en texto plano)"
    if base.startswith("vera_secretos"):
        return "almacén de secretos de V.E.R.A."
    if Path(base).suffix.lower() in EXTENSIONES_PROHIBIDAS:
        return "archivo de llave o certificado"
    return None


def _rol_jwt(token: bytes):
    carga = token.split(b".")[1] + b"=" * (-len(token.split(b".")[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(carga)).get("role")
    except (ValueError, json.JSONDecodeError):
        return None


def revisar(archivos: dict) -> list:
    """archivos: {ruta: bytes}. Devuelve una lista de 'ruta: motivo' (vacía si todo está bien)."""
    hallazgos = []
    for ruta, contenido in archivos.items():
        motivo = nombre_prohibido(ruta)
        if motivo:
            hallazgos.append(f"{ruta}: {motivo}")
        if contenido is None or len(contenido) > LIMITE or b"\x00" in contenido[:8000]:
            continue
        for nombre, patron in REGLAS.items():
            if patron.search(contenido):
                hallazgos.append(f"{ruta}: contiene un {nombre}")
        if any(_rol_jwt(t) == "service_role" for t in JWT.findall(contenido)):
            hallazgos.append(f"{ruta}: contiene una clave service_role de Supabase")
    return hallazgos


def _git(*args, entrada=None):
    return subprocess.run(["git", *args], capture_output=True, input=entrada)


def archivos_staged():
    nombres = [n for n in _git("diff", "--cached", "--name-only", "--diff-filter=ACM", "-z").stdout.decode("utf-8", "replace").split("\0") if n]
    return {n: _git("show", f":{n}").stdout for n in nombres}


def archivos_rastreados():
    nombres = [n for n in _git("ls-files", "-z").stdout.decode("utf-8", "replace").split("\0") if n]
    salida = {}
    for n in nombres:
        try:
            salida[n] = Path(n).read_bytes()
        except OSError:
            salida[n] = None
    return salida


def instalar_hook() -> int:
    r = _git("rev-parse", "--git-path", "hooks")
    if r.returncode != 0:
        print("Esta carpeta no es un repositorio git.")
        return 1
    hook = Path(r.stdout.decode().strip()) / "pre-commit"
    cuerpo = (f"#!/bin/sh\n{MARCA_HOOK}\nPY=$(command -v python || command -v python3 || command -v py)\n"
              '[ -z "$PY" ] && { echo "No se encontro Python: no se pueden verificar secretos."; exit 1; }\n'
              '"$PY" scripts/verificar_secretos.py || exit 1\n')
    if hook.exists() and MARCA_HOOK not in hook.read_text(encoding="utf-8", errors="ignore"):
        print(f"Ya existe un hook distinto en {hook}. Añade manualmente esta línea al final:\n  python scripts/verificar_secretos.py || exit 1")
        return 1
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(cuerpo, encoding="utf-8", newline="\n")
    try:
        hook.chmod(0o755)
    except OSError:
        pass
    print(f"Hook instalado en {hook}. Desde ahora git bloquea los commits con secretos.")
    return 0


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--instalar-hook" in args:
        return instalar_hook()
    hallazgos = revisar(archivos_rastreados() if "--todo" in args else archivos_staged())
    if hallazgos:
        print("COMMIT BLOQUEADO: se encontraron secretos. Quítalos del commit (git rm --cached <archivo>) y rota esas claves:")
        for h in hallazgos:
            print(f"  - {h}")
        return 1
    print("Sin secretos en lo revisado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
