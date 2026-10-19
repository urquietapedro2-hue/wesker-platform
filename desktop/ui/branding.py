"""Identidad visual: logos y fondos desde assets/. Si un archivo falta, la aplicación sigue funcionando sin él."""
from PyQt5 import QtCore, QtGui

from core.paths import resource_path


def ruta(relativa: str):
    p = resource_path(f"assets/{relativa}")
    return str(p) if p.exists() else None


def pixmap(relativa: str, alto: int = None):
    r = ruta(relativa)
    if not r:
        return None
    pm = QtGui.QPixmap(r)
    if pm.isNull():
        return None
    return pm.scaledToHeight(alto, QtCore.Qt.SmoothTransformation) if alto else pm


def icono(relativa: str = "wesker_logo.png"):
    r = ruta(relativa)
    return QtGui.QIcon(r) if r else QtGui.QIcon()


def fondo_cubriendo(relativa: str, tamano):
    """Fondo escalado para cubrir `tamano` (QSize), recortando lo que sobre. None si no está el archivo."""
    pm = pixmap(relativa)
    if pm is None:
        return None
    esc = pm.scaled(tamano, QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
    x, y = (esc.width() - tamano.width()) // 2, (esc.height() - tamano.height()) // 2
    return esc.copy(x, y, tamano.width(), tamano.height())
