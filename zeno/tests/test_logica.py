import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from zeno.logica import (LOGICAS, VigilanteEnlace, decidir_nueva, decidir_v2,  # noqa: E402
                         formatear_ruta, formatear_telemetria, parsear_comando)

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


class TestProtocolo(unittest.TestCase):
    def test_telemetria_identica_a_la_de_v2(self):
        dir_rep, vel, dist, s, sub, qr = "ESTACION", 0.0, 35.0, (1, 0, 1, 0, 1), "ESTACION_DESCARGA", "ESTACION_2"
        v2 = f"TELEM:{dir_rep},{int(vel)},{dist:.1f},{s[0]},{s[1]},{s[2]},{s[3]},{s[4]},{sub},{qr}\n"  # f-string de ZENO_V2
        self.assertEqual(formatear_telemetria(dir_rep, vel, dist, s, sub, qr), v2)

    def test_comandos_validos(self):
        casos = {"PING": ("PING", None, None), "ping": ("PING", None, None), "HELLO": ("HELLO", None, None),
                 "ABORTAR": ("ABORTAR", None, None), "carga_rampa,1": ("CARGA_RAMPA", 1, None), "CARGA_RAMPA,2": ("CARGA_RAMPA", 2, None),
                 "CAL_GET": ("CAL_GET", None, None), "CAL_ESQUEMA": ("CAL_ESQUEMA", None, None),
                 "CAL_GUARDAR": ("CAL_GUARDAR", None, None), "CAL_RESTAURAR": ("CAL_RESTAURAR", None, None),
                 "CAL_DEFECTO": ("CAL_DEFECTO", None, None), "CAL_SET,vel_auto_max,40": ("CAL_SET", "vel_auto_max", "40"),
                 "CAL_PROBAR,Rampa1,120": ("CAL_PROBAR", "rampa1", 120), "PAN,AUTO": ("PAN", "AUTO", None),
                 "PAN,120": ("PAN", 120, None), "CAM_ON": ("CAM_ON", None, None), "CAM_OFF": ("CAM_OFF", None, None),
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
                 "EXPLOTAR", "\x00\xff", "RESUME", "CONFIRMAR", "CARGA_COMPLETA", "DESCARGAR,1", "CARGA_RAMPA", "CARGA_RAMPA,3",
                 "CARGA_RAMPA,0", "CAL_SET", "CAL_SET,a", "CAL_SET,a,b,c", "CAL_SET,,5", "CAL_PROBAR,motor,50", "CAL_PROBAR,rampa1",
                 "CAL_PROBAR,rampa1,181", "CAL_PROBAR,camara,-1", "PAN,999", "PAN,x", "ABORTAR,1", "CAL_GET,1", "F,5.5", "   ", "," * 50]
        for linea in malos:
            c = parsear_comando(linea)
            self.assertIn(c.tipo, ("INVALIDO", "VACIO"), linea)

    def test_linea_ruta_tiene_13_campos_en_orden(self):
        r = {"fase": "DESCARGANDO", "estacion": "ESTACION_2", "carga_r1": True, "carga_r2": False, "alarma": "NINGUNA", "restante_s": 12.4}
        sv = {"backend": "PCA9685", "i2c": True, "servos": {n: {"angulo": a} for n, a in
                                                              (("direccion", 90.0), ("camara", 95.0), ("rampa1", 130.0), ("rampa2", None))}}
        self.assertEqual(formatear_ruta(r, sv, 7), "RUTA:DESCARGANDO,ESTACION_2,1,0,NINGUNA,12,PCA9685,1,90,95,130,-,7\n")

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
