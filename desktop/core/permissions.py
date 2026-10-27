"""Qué puede hacer cada rol. Hoy rige las pantallas; la nube lo impone también con RLS."""

ROLES_CONTROL = frozenset({"ADMIN", "OPERATOR", "MAINTENANCE"})


ROLES_CALIBRACION = frozenset({"ADMIN", "MAINTENANCE"})   # cambiar ángulos, velocidades y tiempos de Zeno


def puede_calibrar(role: str) -> bool:
    return role in ROLES_CALIBRACION


def puede_controlar(role: str) -> bool:
    return role in ROLES_CONTROL


def nota_rol(role: str) -> str:
    return "" if puede_controlar(role) else f"Tu rol ({role}) solo permite observar."
