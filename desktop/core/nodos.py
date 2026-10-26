"""Registro de nodos: las IPs viven en Supabase (una dirección por red y por nodo), nunca en el código ni en un archivo local.
Solo un Admin las edita; los roles de control las leen. Sin Qt (se prueba solo)."""
import ipaddress
from collections import namedtuple

from core.auth import AuthError

Endpoint = namedtuple("Endpoint", "nodo red ip puerto")
NODOS = ("ZENO-01", "ALBERT-01")
PUERTOS_POR_DEFECTO = {"ZENO-01": 65432, "ALBERT-01": 5000}


def validar_endpoint(nodo, red, ip, puerto):
    """Devuelve Endpoint limpio o lanza AuthError con un mensaje claro."""
    red = (red or "").strip()
    if nodo not in NODOS:
        raise AuthError("Nodo desconocido.")
    if not 1 <= len(red) <= 30 or any(ord(c) < 32 for c in red):
        raise AuthError("El nombre de la red debe tener de 1 a 30 caracteres (por ejemplo: Casa, Equipo, Universidad).")
    try:
        direccion = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        raise AuthError("La dirección IP no es válida.") from None
    if direccion.version != 4 or direccion.is_loopback or direccion.is_multicast or direccion.is_unspecified:
        raise AuthError("Usa la dirección IPv4 del nodo en esa red (no 127.x, 0.0.0.0 ni multicast).")
    try:
        p = int(puerto)
    except (TypeError, ValueError):
        raise AuthError("El puerto debe ser un número.") from None
    if not 1 <= p <= 65535:
        raise AuthError("El puerto debe estar entre 1 y 65535.")
    return Endpoint(nodo, red, str(direccion), p)


class RegistroNodos:
    def __init__(self, client):
        self.c = client

    def _llamar(self, nombre, args):
        r = self.c._request("POST", f"/rest/v1/rpc/{nombre}", json=args)
        if r.status_code >= 300:
            try:
                datos = r.json()
                msg = datos.get("message", "") if isinstance(datos, dict) else ""
            except ValueError:
                msg = ""
            if "SIN_PERMISO" in msg:
                raise AuthError("Tu rol no permite esta acción (solo un Admin edita las IPs).")
            raise AuthError(f"Error del servidor ({nombre}): {r.status_code}")
        return r

    def listar(self):
        filas = self._llamar("list_endpoints", {}).json()
        salida = []
        for f in filas if isinstance(filas, list) else []:
            try:
                salida.append(Endpoint(f["node_id"], f["red"], str(f["ip"]).split("/")[0], int(f["puerto"])))
            except (KeyError, TypeError, ValueError):
                continue  # una fila rara no debe romper la pantalla
        return sorted(salida)

    def guardar(self, nodo, red, ip, puerto):
        e = validar_endpoint(nodo, red, ip, puerto)
        self._llamar("set_endpoint", {"p_node": e.nodo, "p_red": e.red, "p_ip": e.ip, "p_puerto": e.puerto})
        return e

    def borrar(self, nodo, red):
        self._llamar("delete_endpoint", {"p_node": nodo, "p_red": red})
