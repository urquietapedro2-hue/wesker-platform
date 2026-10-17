"""Piezas comunes de las páginas de gemelos."""
from PyQt5 import QtCore, QtWidgets


def scroll(widget, ancho=None):
    """Envuelve un widget en un área con scroll (para pantallas pequeñas)."""
    area = QtWidgets.QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QtWidgets.QFrame.NoFrame)
    area.setWidget(widget)
    if ancho:
        area.setFixedWidth(ancho)
        area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
    return area


def grupo_valores(titulo, filas):
    """Grupo de pares «nombre: valor». Devuelve (grupo, {clave: QLabel}) para actualizar los valores."""
    caja = QtWidgets.QGroupBox(titulo)
    form = QtWidgets.QFormLayout(caja)
    valores = {}
    for clave, texto in filas:
        lbl = QtWidgets.QLabel("—")
        lbl.setObjectName("valor")
        valores[clave] = lbl
        form.addRow(texto, lbl)
    return caja, valores


def marcas(flags):
    """[1, 0, 1] -> '● ○ ●'"""
    return " ".join("●" if f else "○" for f in flags)
