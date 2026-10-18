"""Estado compartido de los gemelos: una PC publica y las demás ven. Sin Qt (se prueba solo)."""
from core.auth import AuthError


class Ocupado(AuthError):
    """Otra persona ya publica ese nodo. El mensaje es 'OCUPADO:nombre'."""


class EstadoCompartido:
    def __init__(self, client):
        self.c = client
        self.conocidas = {}  # nodo -> última versión recibida (el servidor solo reenvía lo que cambió)

    def _llamar(self, nombre, args, timeout=None):
        r = self.c._request("POST", f"/rest/v1/rpc/{nombre}", timeout=timeout, json=args)
        if r.status_code >= 300:
            try:
                data = r.json()
                msg = data.get("message", "") if isinstance(data, dict) else ""
            except ValueError:
                msg = ""
            if msg.startswith("OCUPADO:"):
                raise Ocupado(msg)
            if msg == "SIN_PERMISO":
                raise AuthError("Tu rol no permite publicar.")
            raise AuthError(f"Error del servidor ({nombre}): {r.status_code}")
        return r

    def publicar(self, nodo: str, estado: dict, forzar: bool = False) -> int:
        return self._llamar("publish_state", {"p_node": nodo, "p_state": estado, "p_force": forzar}).json()

    def liberar(self, nodo: str, timeout=None):
        self._llamar("release_node", {"p_node": nodo}, timeout)

    def leer(self) -> dict:
        """{nodo: {version, publicador ('' si nadie), cambio, estado (None si no cambió o aún no hay datos)}}"""
        filas = self._llamar("get_states", {"p_known": self.conocidas}).json()
        salida = {}
        for f in filas:
            nodo = f["node_id"]
            estado = f.get("state") if f.get("changed") else None
            if estado:
                self.conocidas[nodo] = f["version"]
            salida[nodo] = {"version": f["version"], "publicador": f.get("publisher_name") or "",
                            "cambio": bool(estado), "estado": estado or None}
        return salida
