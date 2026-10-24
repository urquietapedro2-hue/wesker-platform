import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from zeno import config  # noqa: E402
from zeno.logica import (LOGICAS, Navegador, SIN_CAMBIO, VigilanteEnlace, decidir_nueva, decidir_v2,  # noqa: E402
                         formatear_telemetria, parsear_comando)

# Reglas de SEGUIMIENTO copiadas de ZENO_V2.py (el archivo original del proyecto): el oráculo con el que se compara
REGLAS_V2 = '''
if (s1 == 1 and s2 == 1) or (s1 == 1 and s5 == 0):
    aplicar_traccion("L", 42)
elif (s4 == 1 and s5 == 1) or (s5 == 1 and s1 == 0):
    aplicar_traccion("R", 42)
elif s3 == 1 and s1 == 0 and s5 == 0:
    aplicar_traccion("F", 45)
elif s2 == 1 and s1 == 0 and s5 == 0:
    aplicar_traccion("L", 40)
elif s4 == 1 and s1 == 0 and s5 == 0:
    aplicar_traccion("R", 40)
elif not s1 and not s2 and not s3 and not s4 and not s5:
    aplicar_traccion("S", 0)
'''
COMBINACIONES = list(itertools.product((0, 1), repeat=5))


def oraculo_v2(s):
    llamadas = []
    exec(REGLAS_V2, {"aplicar_traccion": lambda c, v: llamadas.append((c, v)), "s1": s[0], "s2": s[1], "s3": s[2], "s4": s[3], "s5": s[4]})
    return llamadas[0] if llamadas else None


class Reloj:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


class TestDecisiones(unittest.TestCase):
    def test_v2_identico_al_original_en_las_32_combinaciones(self):
        for s in COMBINACIONES:
            self.assertEqual(decidir_v2(s), oraculo_v2(s), s)

    def test_nueva_nunca_deja_una_combinacion_sin_regla(self):
        for s in COMBINACIONES:
            self.assertIsNotNone(decidir_nueva(s), s)
        self.assertEqual(decidir_nueva((0, 0, 0, 0, 0)), ("S", 0))

    def test_donde_v2_no_tiene_regla_la_nueva_si(self):
        sin_regla = [s for s in COMBINACIONES if decidir_v2(s) is None]
        self.assertIn((1, 0, 0, 0, 1), sin_regla)
        self.assertIn((1, 0, 1, 0, 1), sin_regla)

    def test_diferencias_conocidas_entre_v2_y_nueva(self):
        self.assertEqual((decidir_v2((0, 1, 1, 1, 1)), decidir_nueva((0, 1, 1, 1, 1))), (("R", 42), ("F", 45)))
        self.assertEqual((decidir_v2((1, 1, 1, 1, 0)), decidir_nueva((1, 1, 1, 1, 0))), (("L", 42), ("F", 45)))
        self.assertEqual(decidir_nueva((1, 0, 0, 0, 1)), ("L", 42))

    def test_las_dos_coinciden_en_los_casos_basicos(self):
        for s, esperado in (((0, 0, 1, 0, 0), ("F", 45)), ((0, 0, 0, 0, 0), ("S", 0))):
            self.assertEqual((decidir_v2(s), decidir_nueva(s)), (esperado, esperado))


class TestNavegador(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.nav = Navegador("V2", self.reloj)

    def avanzar(self, s, qr="NINGUNO", dt=0.0):
        self.reloj.t += dt
        return self.nav.paso(s, qr)

    def test_logica_desconocida(self):
        with self.assertRaises(ValueError):
            Navegador("INVENTADA")

    def test_sigue_la_linea_con_la_logica_elegida(self):
        self.assertEqual(self.avanzar((0, 0, 1, 0, 0))[:2], ("F", 45))
        self.assertEqual(self.avanzar((1, 1, 0, 0, 0))[:2], ("L", 42))
        self.assertEqual(self.avanzar((1, 0, 0, 0, 1)), SIN_CAMBIO)           # V2: sin regla, mantiene
        self.assertEqual(Navegador("NUEVA", self.reloj).paso((1, 0, 0, 0, 1), "NINGUNO")[:2], ("L", 42))

    def test_base_detiene_enciende_camara_y_recuerda_la_zona(self):
        o = self.avanzar((1, 1, 1, 1, 1))
        self.assertEqual((o.cmd, o.camara, self.nav.sub, self.nav.ultima_estacion), ("S", True, "ESTACION_DESCARGA", "ZONA_DESCARGA"))

    def test_un_qr_nuevo_detiene_y_dice_el_grano(self):
        o = self.avanzar((0, 0, 1, 0, 0), "ESTACION_2")
        self.assertEqual((o.cmd, self.nav.ultima_estacion), ("S", "ESTACION_2"))
        self.assertIn("FRIJOL NEGRO", o.mensaje)

    def test_qr_desconocido_se_ignora(self):
        self.assertEqual(self.avanzar((0, 0, 1, 0, 0), "HOLA")[:2], ("F", 45))

    def test_ciclo_completo_espera_5s_y_sale_1s_a_ciegas(self):
        self.avanzar((1, 1, 1, 1, 1))
        self.assertEqual(self.avanzar((0, 0, 0, 0, 0), dt=4.9).cmd, "S")
        o = self.avanzar((0, 0, 0, 0, 0), dt=0.2)
        self.assertEqual((o.cmd, self.nav.sub), ("S", "SALIENDO_ESTACION"))
        self.assertIn("Ciclo cumplido", o.mensaje)
        for dt in (0.0, 0.5, 0.4):                                              # avance ciego: ignora los sensores
            self.assertEqual(self.avanzar((1, 1, 0, 0, 0), dt=dt)[:2], ("F", 45))
        self.assertEqual(self.avanzar((1, 1, 0, 0, 0), dt=0.2), SIN_CAMBIO)    # pasó 1 s: vuelve a SEGUIMIENTO
        self.assertEqual(self.nav.sub, "SEGUIMIENTO")
        self.assertEqual(self.avanzar((1, 1, 0, 0, 0))[:2], ("L", 42))

    def _salir_de_estacion(self, qr):
        self.avanzar((0, 0, 1, 0, 0), qr)
        self.avanzar((0, 0, 1, 0, 0), qr, dt=5.1)
        self.avanzar((0, 0, 1, 0, 0), qr)
        self.avanzar((0, 0, 1, 0, 0), qr, dt=1.1)
        self.avanzar((0, 0, 1, 0, 0), qr)

    def test_no_se_detiene_otra_vez_en_el_mismo_qr_pero_si_cuando_deja_de_verlo(self):
        self._salir_de_estacion("ESTACION_1")
        self.assertEqual(self.nav.sub, "SEGUIMIENTO")
        self.assertEqual(self.avanzar((0, 0, 1, 0, 0), "ESTACION_1")[:2], ("F", 45))   # sigue visible: no repite
        self.avanzar((0, 0, 1, 0, 0), "NINGUNO")                                         # sale de la vista: se olvida
        self.assertEqual(self.avanzar((0, 0, 1, 0, 0), "ESTACION_1").cmd, "S")           # ahora sí es una parada nueva
        self.assertEqual(self.nav.sub, "ESTACION_DESCARGA")

    def test_reanudar_solo_funciona_en_estacion(self):
        self.assertFalse(self.nav.reanudar())
        self.avanzar((1, 1, 1, 1, 1))
        self.assertTrue(self.nav.reanudar())
        self.assertEqual(self.nav.sub, "SALIENDO_ESTACION")
        self.assertEqual(self.avanzar((0, 0, 0, 0, 0))[:2], ("F", 45))

    def test_modo_manual_no_decide_y_volver_a_auto_reinicia(self):
        self.avanzar((1, 1, 1, 1, 1))
        self.nav.cambiar_modo("MANUAL")
        self.assertEqual(self.avanzar((0, 0, 1, 0, 0)), SIN_CAMBIO)
        self.nav.cambiar_modo("AUTO")
        self.assertEqual(self.nav.sub, "SEGUIMIENTO")
        self.assertEqual(self.avanzar((0, 0, 1, 0, 0))[:2], ("F", 45))

    def test_el_resultado_es_el_mismo_con_cualquier_reloj_inicial(self):
        for inicio in (0.0, 1e6):
            n = Navegador("V2", lambda: inicio)
            self.assertEqual(n.paso((0, 0, 1, 0, 0), "NINGUNO", inicio)[:2], ("F", 45))


class TestProtocolo(unittest.TestCase):
    def test_telemetria_identica_a_la_de_v2(self):
        dir_rep, vel, dist, s, sub, qr = "ESTACION", 0.0, 35.0, (1, 0, 1, 0, 1), "ESTACION_DESCARGA", "ESTACION_2"
        v2 = f"TELEM:{dir_rep},{int(vel)},{dist:.1f},{s[0]},{s[1]},{s[2]},{s[3]},{s[4]},{sub},{qr}\n"  # f-string de ZENO_V2
        self.assertEqual(formatear_telemetria(dir_rep, vel, dist, s, sub, qr), v2)

    def test_comandos_validos(self):
        casos = {"PING": ("PING", None, None), "ping": ("PING", None, None), "HELLO": ("HELLO", None, None),
                 "RESUME": ("RESUME", None, None), "CAM_ON": ("CAM_ON", None, None), "CAM_OFF": ("CAM_OFF", None, None),
                 "MODE,manual": ("MODE", "MANUAL", None), "MODE,AUTO": ("MODE", "AUTO", None),
                 "f,50": ("MOVER", "F", 50), "B": ("MOVER", "B", 45), "S,0": ("MOVER", "S", 0), " L , 100 ": ("MOVER", "L", 100),
                 "DIAG_PULSE,L,40,300": ("DIAG_PULSE", "L", 40), "DIAG_PULSE": ("DIAG_PULSE", "F", 45),
                 "AUTH,AbC_-123": ("AUTH", "AbC_-123", None)}
        for linea, (tipo, a, b) in casos.items():
            c = parsear_comando(linea)
            self.assertEqual((c.tipo, c.a, c.b), (tipo, a, b), linea)

    def test_comandos_invalidos_nunca_lanzan_excepciones(self):
        malos = ["MODE,foo", "MODE", "F,abc", "F,101", "F,-1", "F,1,2", "DIAG_PULSE,X,40,300", "DIAG_PULSE,L,40,999999",
                 "DIAG_PULSE,L,40,10", "DIAG_PULSE,L,101,300", "DIAG_PULSE,L,40,300,9", "PING,1", "AUTH", "AUTH,a,b",
                 "EXPLOTAR", "\x00\xff", "F,5.5", "   ", "," * 50]
        for linea in malos:
            c = parsear_comando(linea)
            self.assertIn(c.tipo, ("INVALIDO", "VACIO"), linea)

    def test_el_token_conserva_mayusculas(self):
        self.assertEqual(parsear_comando("AUTH,TokenConMAYUS").a, "TokenConMAYUS")


class TestVigilante(unittest.TestCase):
    def test_vence_y_se_renueva(self):
        r = Reloj()
        v = VigilanteEnlace(2.0, r)
        r.t += 1.9
        self.assertFalse(v.vencido())
        r.t += 0.2
        self.assertTrue(v.vencido())
        v.latido()
        self.assertFalse(v.vencido())


if __name__ == "__main__":
    unittest.main()
