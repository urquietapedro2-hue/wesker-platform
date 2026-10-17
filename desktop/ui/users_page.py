from datetime import datetime, timezone

from PyQt5 import QtWidgets

COLUMNAS = ["Nombre", "Rol", "Cliente", "Versión", "Visto"]


def hace(ts: str) -> str:
    try:
        seg = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        return "—"
    return "ahora" if seg < 20 else f"hace {int(seg)} s"


class UsersPage(QtWidgets.QWidget):
    """Lista de sesiones activas (la pantalla de usuarios conectados)."""

    def __init__(self):
        super().__init__()
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Conectados ahora"))
        self.tabla = QtWidgets.QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels(COLUMNAS)
        self.tabla.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.tabla.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.tabla, 1)

    def pintar(self, filas):
        self.tabla.setRowCount(len(filas))
        for i, u in enumerate(filas):
            for j, v in enumerate((u["nombre"], u["role"], u["client"], u["version"], hace(u["last_seen"]))):
                self.tabla.setItem(i, j, QtWidgets.QTableWidgetItem(v or ""))
