# Portado de WESKER 3.0 sin cambiar el dibujo. Añadido en v1.2.0: exportar_estado/importar_estado y modo espejo (final del archivo). Las rutas hacia los clientes TCP reales (albert_client, sellador_client)
# quedan inactivas porque la página no las define; se reconectarán cuando los nodos reales entren a la plataforma.
# -*- coding: utf-8 -*-
"""
====================================================================
PROYECTO: W.E.S.K.E.R. 3.0 - GEMELO DIGITAL A.L.B.E.R.T. (INTEGRACIÓN TOTAL FMS)
SISTEMA: CELDA AUTOMATIZADA DE DOSIFICACIÓN, TAPADO Y SELLADO TÉRMICO
         - CORRECCIÓN Z-INDEX: TAPAS Y PRENSA EN CAPA SUPERIOR (OVERLAY)
         - REPOSICIONAMIENTO ANGULAR DE ESTACIÓN 2.5 (315° EN CÍRCULO EXTERIOR)
         - RENDERIZADO DE TAPA NEGRA INDUSTRIAL CON RELIEVE SOBRE ENVASE
         - CONEXIÓN TCP CON NODOS ESP32 (las direcciones se leerán del registro de nodos, nunca del código)
====================================================================
"""

import math
import random
from PyQt5 import QtWidgets, QtGui, QtCore


class AlbertDigitalTwin(QtWidgets.QWidget):
    alerta_silo_vacio = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_dashboard = parent  # Referencia al Dashboard o Modal
        self.setMinimumSize(500, 620)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        # Variables de control de operación global
        self.modo_operacion = "AUTO"       # "MANUAL" o "AUTO"
        self.angulo_estrella = 0.0        
        self.angulo_objetivo = 0.0        
        self.vasos_en_silo = 4            
        
        self.vasos_en_slots = [None] * 8
        self.vasos_terminados = 0         
        self.estado_estacion1 = "STANDBY" 
        
        # Estado de Sensores FC-51 y KY-032 (Sincronización TCP)
        self.sensor_fc51_e1 = False       
        self.sensor_fc51_e2 = False       
        self.sensor_fc51_e3 = False       
        self.sensor_ky032_tolva = False   

        # Estado del Motor a Pasos
        self.estado_motor_txt = "REPOSO"

        # Secuencias Automáticas y Gestión de Lotes
        self.secuencia_auto_tipo = "PINTO"
        self.es_secuencia_dinamica = False
        self.texto_resumen_secuencia = ""
        
        self.patron_lote_base = []        
        self.cola_lote_vasos = []         
        self.ciclos_lote_completados = 0  
        self.dosificando_activo = False

        # --- ESTACIÓN 2.5 (DISPENSADOR DE TAPAS) Y ESTACIÓN 3 (SELLADO) ---
        self.tapa_dispensando_anim = False
        self.angulo_servo_tapas = 0.0      # 0° Retención, 90° Dispensar
        self.angulo_servo_tapas_obj = 0.0
        self.vasos_con_tapa = [False] * 8  # Rastreo de tapas por alvéolo

        self.sellando_activo = False
        self.pos_piston_sello = 0.0        # Extensión del actuador (0.0 a 1.0)
        self.pos_piston_sello_obj = 0.0
        self.tiempo_prensa_sello = 0.0

        self.indice_rotativo = 0
        self.conteo_lote = 0
        self.silo_doble_actual = 0
        self.bicolor_flag = False

        # Estados Estación 2 (A.L.B.E.R.T.)
        self.servos_silos = [False, False, False]
        self.silos_seleccionados = [1]     
        self.servo_tolva = False
        self.nivel_tolva = 0.0
        self.tipo_frijol_tolva = None

        # Control de compuertas rotativas
        self.angulos_compuertas = [0.0, 0.0, 0.0]        
        self.angulos_objetivo = [0.0, 0.0, 0.0]
        self.silo_en_descarga = -1                       
        self.fase_dosif = "REPOSO"                       
        self.progreso_dosif = 0.0
        self.particulas_frijol = []                      
        
        # Animaciones de caída y movimiento de vasos
        self.dispensando_vaso_anim = False
        self.y_vaso_caida = 0.0
        self.slot_dispensando = None
        
        self.descargando_anim = False
        self.y_vaso_descarga = 0.0
        self.pos_descarga_x = 0.0
        self.pos_descarga_y = 0.0
        self.tipo_vaso_descarga = None

        # Alerta parpadeo
        self.alerta_parpadeo = False
        self.timer_alerta = QtCore.QTimer(self)
        self.timer_alerta.timeout.connect(self._toggle_parpadeo)
        self.timer_alerta.start(450)

        self.vasos_en_slots[4] = "VACIO"

        # Timer de animación continua a 30 FPS (~33 ms)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._animar)
        self.timer.start(33)

    # =========================================================
    # ACTUALIZACIÓN EN TIEMPO REAL DESDE TELEMETRÍA TCP
    # =========================================================
    def actualizar_telemetria_estrella(self, datos_json):
        """Sincroniza el gemelo virtual con la trama JSON recibida de la Estación 1."""
        try:
            if isinstance(datos_json, str):
                import json
                datos = json.loads(datos_json)
            else:
                datos = datos_json

            self.sensor_fc51_e1 = bool(datos.get("s1", 0))
            self.sensor_fc51_e2 = bool(datos.get("s2", 0))
            self.sensor_fc51_e3 = bool(datos.get("s3", 0))

            if "modo" in datos:
                self.modo_operacion = datos["modo"].upper()

            self.estado_motor_txt = datos.get("motor", "REPOSO").upper()

            if datos.get("paso_completado", False) or self.estado_motor_txt == "GIRANDO":
                self.avanzar_un_paso()

            self.update()
        except Exception:
            pass

    def actualizar_telemetria_albert(self, trama_str):
        """Sincroniza la telemetría enviada por la ESP32 de A.L.B.E.R.T."""
        try:
            if "KY032:LLENO" in trama_str:
                self.sensor_ky032_tolva = True
            elif "KY032:VACIO" in trama_str:
                self.sensor_ky032_tolva = False

            if "MODE:MANUAL" in trama_str:
                self.modo_operacion = "MANUAL"
            elif "MODE:AUTO" in trama_str:
                self.modo_operacion = "AUTO"

            self.update()
        except Exception:
            pass

    def _toggle_parpadeo(self):
        if self.estado_estacion1 == "SIN_VASOS":
            self.alerta_parpadeo = not self.alerta_parpadeo
            self.update()

    def set_modo(self, modo: str):
        self.modo_operacion = modo
        self.update()

    def set_sensores_estrella(self, s1: int, s2: int, s3: int):
        self.sensor_fc51_e1 = bool(s1)
        self.sensor_fc51_e2 = bool(s2)
        self.sensor_fc51_e3 = bool(s3)
        self.update()

    def set_secuencia_auto(self, tipo: str):
        self.secuencia_auto_tipo = tipo
        self.es_secuencia_dinamica = False
        self.conteo_lote = 0
        self.texto_resumen_secuencia = ""
        self.cola_lote_vasos.clear()
        self.patron_lote_base.clear()

        mapa_silos = {
            "NEGRO": [0], "PINTO": [1], "PERUANO": [2],
            "ROTATIVO": [0, 1, 2], "DOBLE": [0], "ALEATORIO": [1],
            "3NEGRO_1PINTO": [0, 1], "BICOLOR": [0, 2], "GOURMET": [0, 1, 2]
        }
        self.silos_seleccionados = mapa_silos.get(tipo, [1])
        self.update()

    def set_secuencia_dinamica(self, lista_pasos: list):
        self.es_secuencia_dinamica = True
        self.secuencia_auto_tipo = "LOTE_CONTINUO"
        self.ciclos_lote_completados = 0
        
        mapa_nombres = {1: "NEGRO", 2: "PINTO", 3: "PERUANO"}
        self.patron_lote_base = []
        for p in lista_pasos:
            tipo_grano = mapa_nombres.get(p['silo'], "PINTO")
            cantidad_vasos = p.get('qty', 1)
            for _ in range(cantidad_vasos):
                self.patron_lote_base.append(tipo_grano)

        self.cola_lote_vasos = list(self.patron_lote_base)
        self.silos_seleccionados = [p['silo'] - 1 for p in lista_pasos if 1 <= p['silo'] <= 3]
        
        resumen = " ➔ ".join([f"{p.get('qty', 1)}x S{p['silo']}" for p in lista_pasos])
        self.texto_resumen_secuencia = f"[{resumen}] (Bucle Activo | Vasos rest: {len(self.cola_lote_vasos)})"
        self.update()

    def avanzar_un_paso(self):
        self._verificar_descarga_al_avanzar()
        self.angulo_objetivo += 45.0

    def animar_rotacion(self):
        self.avanzar_un_paso()

    def dispensar_vaso_estacion1(self):
        if self.dispensando_vaso_anim:
            return

        for i in range(8):
            ang_deg = ((i * 45.0) + self.angulo_estrella) % 360.0
            if abs(ang_deg - 180.0) <= 2.0 and self.vasos_en_slots[i] is None:
                if self.vasos_en_silo > 0:
                    self.vasos_en_silo -= 1
                    self.dispensando_vaso_anim = True
                    self.y_vaso_caida = -85.0
                    self.slot_dispensando = i
                    self.estado_estacion1 = "DISPENSING"
                    self.update()
                else:
                    if self.estado_estacion1 != "SIN_VASOS":
                        self.estado_estacion1 = "SIN_VASOS"
                        self.alerta_silo_vacio.emit("ALERTA ESTACIÓN 1: Silo alimentador vacío. Inserte vasos.")
                        self.update()
                break

    def recargar_silo(self, cantidad=4):
        self.vasos_en_silo = min(4, cantidad)
        self.estado_estacion1 = "STANDBY"
        self._evaluar_alimentacion_gravedad()
        self.update()

    def _evaluar_alimentacion_gravedad(self):
        self.dispensar_vaso_estacion1()

    def abrir_silo_manual(self, indice_silo: int):
        """Dispara la animación visual de la apertura del servo en pantalla."""
        if self.fase_dosif != "REPOSO":
            return

        tipos = ["NEGRO", "PINTO", "PERUANO"]
        self.tipo_frijol_tolva = tipos[indice_silo]
        self.silo_en_descarga = indice_silo
        self.fase_dosif = "ABRIENDO"
        self.progreso_dosif = 0.0
        self.angulos_objetivo[indice_silo] = 90.0

        for s in range(3):
            self.servos_silos[s] = (s == indice_silo)
        self.update()

    def cerrar_silos(self):
        self.servos_silos = [False, False, False]
        for s in range(3):
            self.angulos_objetivo[s] = 0.0
        self.update()

    def vaciar_tolva_manual(self):
        if not self.sensor_fc51_e2:
            return

        self.servo_tolva = True
        if self.nivel_tolva > 0.0:
            for i in range(8):
                ang_deg = ((i * 45.0) + self.angulo_estrella) % 360.0
                if abs(ang_deg - 270.0) <= 2.0 and self.vasos_en_slots[i] is not None:
                    self.vasos_en_slots[i] = self.tipo_frijol_tolva or "PINTO"
                    break
            self.nivel_tolva = 0.0

        QtCore.QTimer.singleShot(900, self._cerrar_tolva)
        self.update()

    def _cerrar_tolva(self):
        self.servo_tolva = False
        self.dosificando_activo = False
        self.silo_en_descarga = -1
        self.fase_dosif = "REPOSO"
        if self.es_secuencia_dinamica:
            self.texto_resumen_secuencia = f"(Vuelta #{self.ciclos_lote_completados + 1} | Vasos rest: {len(self.cola_lote_vasos)})"
        self.update()

    # =========================================================
    # LÓGICA ESTACIÓN 2.5 (TAPAS) Y ESTACIÓN 3 (SELLADO TÉRMICO)
    # =========================================================
    def dispensar_tapa_estacion25(self, slot_index: int):
        """Acciona el servo de tapas para colocar una tapa negra sobre el vaso."""
        self.angulo_servo_tapas_obj = 90.0
        self.tapa_dispensando_anim = True
        QtCore.QTimer.singleShot(800, lambda: self._finalizar_dispensado_tapa(slot_index))

    def _finalizar_dispensado_tapa(self, slot_index: int):
        self.angulo_servo_tapas_obj = 0.0
        self.tapa_dispensando_anim = False
        if 0 <= slot_index < 8:
            # Registra explícitamente la tapa negra en el slot correspondiente
            self.vasos_con_tapa[slot_index] = True
        self.update()

    def _evaluar_estacion25_tapas(self):
        """COMPLEMENTO INTEGRADOR: Evalúa si hay un vaso con carga en la Estación 2.5 (315°) y dispara la tapa negra."""
        for i in range(8):
            ang_deg = ((i * 45.0) + self.angulo_estrella) % 360.0
            if abs(ang_deg - 315.0) <= 7.0 or abs(ang_deg - 315.0) >= 353.0:
                if self.vasos_en_slots[i] in ["NEGRO", "PINTO", "PERUANO", "VACIO"] and not self.vasos_con_tapa[i] and not self.tapa_dispensando_anim:
                    self.dispensar_tapa_estacion25(i)
                    sellador_cli = getattr(self.parent_dashboard, 'sellador_client', None)
                    if sellador_cli and getattr(self.parent_dashboard, 'sellador_conectado', False):
                        try:
                            sellador_cli.dispensar_tapa()
                        except Exception:
                            pass
                break

    def ejecutar_sellado_estacion3(self, slot_index: int):
        """Activa el actuador lineal para presionar y sellar térmicamente el vaso durante 3s."""
        self.sellando_activo = True
        self.pos_piston_sello_obj = 1.0  # Totalmente extendido
        self.tiempo_prensa_sello = 3.0
        QtCore.QTimer.singleShot(2000, lambda: self._iniciar_prensa_3s(slot_index))

    def _iniciar_prensa_3s(self, slot_index: int):
        def _retraer_prensa():
            self.pos_piston_sello_obj = 0.0
            QtCore.QTimer.singleShot(2000, self._concluir_sellado_estacion3)

        QtCore.QTimer.singleShot(3000, _retraer_prensa)

    def _concluir_sellado_estacion3(self):
        self.sellando_activo = False
        self.update()

    # =========================================================
    # LÓGICA CONEXIÓN REAL TCP A ESP32 EN ESTACIÓN 2 Y 3
    # =========================================================
    def _evaluar_estacion2_auto(self):
        """Evalúa si hay un vaso listo en la Estación 2 y transmite el comando real a la ESP32."""
        if self.modo_operacion != "AUTO" or self.dosificando_activo:
            return

        for i in range(8):
            ang_deg = ((i * 45.0) + self.angulo_estrella) % 360.0
            if abs(ang_deg - 270.0) <= 2.0 and self.vasos_en_slots[i] == "VACIO" and self.sensor_fc51_e2:
                mapa_idx = {"NEGRO": 0, "PINTO": 1, "PERUANO": 2}

                if self.es_secuencia_dinamica:
                    if not self.cola_lote_vasos:
                        if self.patron_lote_base:
                            self.cola_lote_vasos = list(self.patron_lote_base)
                            self.ciclos_lote_completados += 1
                        else:
                            return
                    tipo_grano = self.cola_lote_vasos.pop(0)
                    silo_idx = mapa_idx[tipo_grano]
                else:
                    if self.secuencia_auto_tipo == "ALEATORIO":
                        silo_idx = random.randint(0, 2)
                    elif self.secuencia_auto_tipo == "DOBLE":
                        silo_idx = self.silo_doble_actual
                        self.conteo_lote += 1
                        if self.conteo_lote >= 2:
                            self.conteo_lote = 0
                            self.silo_doble_actual = (self.silo_doble_actual + 1) % 3
                    elif self.secuencia_auto_tipo == "3NEGRO_1PINTO":
                        silo_idx = 0 if self.conteo_lote < 3 else 1
                        self.conteo_lote = (self.conteo_lote + 1) % 4
                    elif self.secuencia_auto_tipo == "BICOLOR":
                        silo_idx = 0 if not self.bicolor_flag else 2
                        self.bicolor_flag = not self.bicolor_flag
                    elif self.secuencia_auto_tipo == "GOURMET":
                        silo_idx = 1 if self.conteo_lote < 2 else 2
                        self.conteo_lote = (self.conteo_lote + 1) % 3
                    elif self.secuencia_auto_tipo == "ROTATIVO":
                        silo_idx = self.indice_rotativo % 3
                        self.indice_rotativo += 1
                    elif self.secuencia_auto_tipo == "NEGRO":
                        silo_idx = 0
                    elif self.secuencia_auto_tipo == "PINTO":
                        silo_idx = 1
                    else:
                        silo_idx = 2

                self.dosificando_activo = True
                self.abrir_silo_manual(silo_idx)

                client = getattr(self.parent_dashboard, 'albert_client', None)
                if client and getattr(self.parent_dashboard, 'albert_conectado', False):
                    num_silo_real = silo_idx + 1
                    QtCore.QTimer.singleShot(100, lambda: self._disparar_socket_real_esp32(client, num_silo_real, i))
                break

    def _disparar_socket_real_esp32(self, client, silo_num: int, slot_index: int):
        """Ejecuta el envío socket TCP real al firmware de la ESP32."""
        try:
            respuesta = client.dosificar_silo(silo_num)
            if "LLENA" in respuesta or "OK" in respuesta or "TIMEOUT" in respuesta:
                tipos = ["NEGRO", "PINTO", "PERUANO"]
                self.vasos_en_slots[slot_index] = tipos[silo_num - 1]
                self.update()
        except Exception as e:
            if hasattr(self.parent_dashboard, 'log_event'):
                self.parent_dashboard.log_event(f"[ERROR TCP GEMELO]: {e}", "ERROR")

    def _evaluar_estacion3_sellado(self):
        if not self.sensor_fc51_e3:
            return

        for i in range(8):
            ang_deg = ((i * 45.0) + self.angulo_estrella) % 360.0
            if (abs(ang_deg - 0.0) <= 2.0 or abs(ang_deg - 360.0) <= 2.0):
                if self.vasos_en_slots[i] in ["NEGRO", "PINTO", "PERUANO"] and not self.sellando_activo:
                    self.ejecutar_sellado_estacion3(i)
                    sellador_cli = getattr(self.parent_dashboard, 'sellador_client', None)
                    if sellador_cli and getattr(self.parent_dashboard, 'sellador_conectado', False):
                        sellador_cli.ejecutar_sellado()
                break

    def _verificar_descarga_al_avanzar(self):
        r_center = 140.0
        for i in range(8):
            if self.vasos_en_slots[i] is not None:
                ang_deg = ((i * 45.0) + self.angulo_estrella) % 360.0
                if abs(ang_deg - 90.0) <= 2.0:
                    self.descargando_anim = True
                    self.y_vaso_descarga = 0.0
                    rad = math.radians(ang_deg)
                    self.pos_descarga_x = 10.0 + r_center * math.cos(rad)
                    self.pos_descarga_y = 35.0 + r_center * math.sin(rad)
                    self.tipo_vaso_descarga = self.vasos_en_slots[i]
                    self.vasos_en_slots[i] = None
                    self.vasos_con_tapa[i] = False
                    self.vasos_terminados += 1
                    break

    def reset_contador(self):
        self.vasos_terminados = 0
        self.ciclos_lote_completados = 0
        self.update()

    def _animar(self):
        if self.espejo:
            self._animar_espejo()
            return
        needs_update = False

        if abs(self.angulo_estrella - self.angulo_objetivo) > 0.3:
            self.angulo_estrella += (self.angulo_objetivo - self.angulo_estrella) * 0.18
            needs_update = True
        else:
            if self.angulo_estrella != self.angulo_objetivo:
                self.angulo_estrella = self.angulo_objetivo
                self._evaluar_alimentacion_gravedad()
                if self.modo_operacion == "AUTO":
                    self._evaluar_estacion2_auto()
                    self._evaluar_estacion25_tapas()  # <-- COMPLEMENTO EVALUADOR INTEGRADOR
                    self._evaluar_estacion3_sellado()
            needs_update = True

        if abs(self.angulo_servo_tapas_obj - self.angulo_servo_tapas) > 0.5:
            delta_tapa = 10.0 if self.angulo_servo_tapas_obj > self.angulo_servo_tapas else -10.0
            self.angulo_servo_tapas += delta_tapa
            needs_update = True

        if abs(self.pos_piston_sello_obj - self.pos_piston_sello) > 0.02:
            delta_piston = 0.08 if self.pos_piston_sello_obj > self.pos_piston_sello else -0.08
            self.pos_piston_sello += delta_piston
            needs_update = True

        # Detección de vasos en los 3 sensores FC-51
        e1_ok, e2_ok, e3_ok = False, False, False
        for i in range(8):
            ang_deg = ((i * 45.0) + self.angulo_estrella) % 360.0
            if abs(ang_deg - 180.0) <= 7.0 and self.vasos_en_slots[i] is not None:
                e1_ok = True
            if abs(ang_deg - 270.0) <= 7.0 and self.vasos_en_slots[i] is not None:
                e2_ok = True
            if (abs(ang_deg - 0.0) <= 7.0 or abs(ang_deg - 360.0) <= 7.0) and self.vasos_en_slots[i] is not None:
                e3_ok = True

        tolva_ok = (self.nivel_tolva >= 75.0)

        if (self.sensor_fc51_e1 != e1_ok) or (self.sensor_fc51_e2 != e2_ok) or \
           (self.sensor_fc51_e3 != e3_ok) or (self.sensor_ky032_tolva != tolva_ok):
            self.sensor_fc51_e1 = e1_ok
            self.sensor_fc51_e2 = e2_ok
            self.sensor_fc51_e3 = e3_ok
            self.sensor_ky032_tolva = tolva_ok
            needs_update = True

        for s in range(3):
            obj = self.angulos_objetivo[s]
            act = self.angulos_compuertas[s]
            if abs(obj - act) > 0.5:
                delta = 4.5 if obj > act else 5.5
                if act < obj:
                    self.angulos_compuertas[s] = min(obj, act + delta)
                else:
                    self.angulos_compuertas[s] = max(obj, act - delta)
                needs_update = True

        if self.fase_dosif != "REPOSO" and self.silo_en_descarga >= 0:
            needs_update = True
            s_idx = self.silo_en_descarga
            
            if self.fase_dosif == "ABRIENDO":
                if self.angulos_compuertas[s_idx] >= 85.0:
                    self.fase_dosif = "VERTIDO"
                    self.progreso_dosif = 0.0

            elif self.fase_dosif == "VERTIDO":
                self.nivel_tolva = min(100.0, self.nivel_tolva + 2.5) 
                self._generar_particulas_frijol(s_idx)

                if self.nivel_tolva >= 100.0:
                    self.fase_dosif = "BARRIDO_CIERRE"
                    self.cerrar_silos() 

            elif self.fase_dosif == "BARRIDO_CIERRE":
                if self.angulos_compuertas[s_idx] <= 5.0:
                    self.fase_dosif = "REPOSO"
                    QtCore.QTimer.singleShot(400, self.vaciar_tolva_manual)

        if self.particulas_frijol:
            needs_update = True
            nuevas_p = []
            for p in self.particulas_frijol:
                p["x"] += p["vx"]
                p["y"] += p["vy"]
                p["vy"] += 0.35 
                p["vida"] -= 1
                if p["vida"] > 0:
                    nuevas_p.append(p)
            self.particulas_frijol = nuevas_p

        if self.dispensando_vaso_anim:
            self.y_vaso_caida += 10.0
            if self.y_vaso_caida >= 0.0:
                self.y_vaso_caida = 0.0
                self.dispensando_vaso_anim = False
                if self.slot_dispensando is not None:
                    self.vasos_en_slots[self.slot_dispensando] = "VACIO"
                    self.slot_dispensando = None
                self.estado_estacion1 = "STANDBY"
            needs_update = True

        if self.descargando_anim:
            self.y_vaso_descarga += 8.0
            if self.y_vaso_descarga >= 70.0:
                self.descargando_anim = False
                self.y_vaso_descarga = 0.0
            needs_update = True

        if needs_update:
            self.update()

    def _generar_particulas_frijol(self, silo_idx: int):
        pos_silos_rel_x = [-50.0, 0.0, 50.0]
        sx = 10.0 + pos_silos_rel_x[silo_idx]
        sy = 35.0 - 205 - 14.0 

        colores = [QtGui.QColor("#1E293B"), QtGui.QColor("#854D0E"), QtGui.QColor("#EAB308")]
        col = colores[silo_idx]

        for _ in range(2):
            self.particulas_frijol.append({
                "x": sx + random.uniform(-2.5, 2.5),
                "y": sy + random.uniform(0, 4),
                "vx": random.uniform(-0.4, 0.4),
                "vy": random.uniform(1.8, 3.2),
                "color": col,
                "rx": random.uniform(2.2, 3.4),
                "ry": random.uniform(3.5, 5.0),
                "angulo": random.uniform(0, 360),
                "vida": 18
            })

    # =========================================================
    # PIPELINE DE RENDERIZADO CON ORDEN DE CAPAS (Z-INDEX)
    # =========================================================
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QtGui.QColor(8, 13, 26, 190))
        painter.setPen(QtGui.QPen(QtGui.QColor(19, 28, 49, 140), 1, QtCore.Qt.DotLine))
        for gx in range(0, w, 25): painter.drawLine(gx, 0, gx, h)
        for gy in range(0, h, 25): painter.drawLine(0, gy, w, gy)

        painter.save()
        base_w, base_h = 500.0, 600.0
        scale_x = (w - 10) / base_w
        scale_y = (h - 45) / base_h
        scale = min(scale_x, scale_y) * 1.05

        painter.translate(w / 2.0, (h - 20) / 2.0)
        painter.scale(scale, scale)

        cx, cy = 10.0, 35.0

        # --- CAPA 1: BASTIDOR INFERIOR Y ANILLO BASE ---
        self._dibujar_bastidor_comun(painter, cx, cy)
        self._dibujar_anillo_guia(painter, cx, cy)

        # --- CAPA 2: CINEMÁTICA PRINCIPAL (ESTRELLA DE MALTA) ---
        self._dibujar_estrella_malta_real(painter, cx, cy, self.angulo_estrella)

        # --- CAPA 3: VASOS Y CONTENIDO EN ALVÉOLOS ---
        self._dibujar_vasos(painter, cx, cy, self.angulo_estrella)

        # --- CAPA 4: ESTACIONES EXTERIORES Y SILOS DE DOSIFICACIÓN ---
        self._dibujar_silo_cad_estacion1(painter, cx - 140, cy)
        self._dibujar_estacion2_silos_y_tolva_elevados(painter, cx, cy - 205)
        self._dibujar_lluvia_granos(painter)

        # --- CAPA 5: OVERLAY SUPERIOR (ESTACIÓN 2.5 TAPAS Y ESTACIÓN 3 PRENSA) ---
        rad_e25 = math.radians(315.0)
        e25_x = cx + 175.0 * math.cos(rad_e25)
        e25_y = cy + 175.0 * math.sin(rad_e25)
        self._dibujar_estacion25_dispensador_tapas_hd(painter, e25_x, e25_y)

        # Estación 3: Prensa térmica a la derecha (0°)
        self._dibujar_estacion3_prensa_hd(painter, cx + 140, cy)

        # --- CAPA 6: SENSORES INDUSTRIALES ---
        self._dibujar_sensor_fc51_hd(painter, cx - 140, cy - 38, self.sensor_fc51_e1, "FC-51 E1", rotacion=90)
        self._dibujar_sensor_fc51_hd(painter, cx - 36, cy - 142, self.sensor_fc51_e2, "FC-51 E2", rotacion=180)
        self._dibujar_sensor_fc51_hd(painter, cx + 140, cy - 38, self.sensor_fc51_e3, "FC-51 E3", rotacion=90)

        painter.restore()

        # HUD Inferior
        pos_num = (int(round(self.angulo_estrella / 45.0)) % 8) + 1
        color_receta = QtGui.QColor("#38BDF8") if self.es_secuencia_dinamica else QtGui.QColor("#34D399")
        texto_receta = f"{self.secuencia_auto_tipo} {self.texto_resumen_secuencia}".strip()

        painter.setPen(QtGui.QColor("#F8FAFC"))
        painter.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold))
        painter.drawText(15, h - 34, f"A.L.B.E.R.T. [{self.modo_operacion}] | POSICIÓN: {pos_num}/8 ({int(self.angulo_estrella % 360)}°) | MOTOR: {self.estado_motor_txt}")
        
        painter.setPen(color_receta)
        painter.drawText(360, h - 34, f"LOTE: {texto_receta}")
        
        s1_txt = "OK" if self.sensor_fc51_e1 else "NO"
        s2_txt = "OK" if self.sensor_fc51_e2 else "NO"
        s3_txt = "OK" if self.sensor_fc51_e3 else "NO"
        ky_txt = "LLENO" if self.sensor_ky032_tolva else "VACÍO"

        s1_deg = int(self.angulos_compuertas[0])
        s2_deg = int(self.angulos_compuertas[1])
        s3_deg = int(self.angulos_compuertas[2])

        color_hud_e1 = QtGui.QColor("#EF4444") if self.estado_estacion1 == "SIN_VASOS" else QtGui.QColor("#10B981")
        painter.setPen(color_hud_e1)
        texto_e1 = f"SILO: {self.vasos_en_silo}/4 [¡SIN VASOS!]" if self.estado_estacion1 == "SIN_VASOS" else f"SILO: {self.vasos_en_silo}/4"
        painter.drawText(15, h - 14, f"PROD: {self.vasos_terminados} | {texto_e1} | VASO:[E1:{s1_txt} E2:{s2_txt} E3:{s3_txt}] | TOLVA:[{ky_txt}] | SERVOS:[{s1_deg}°, {s2_deg}°, {s3_deg}°]")

    def _dibujar_sensor_fc51_hd(self, painter, x, y, detectando: bool, etiqueta: str, rotacion: float = 0.0):
        painter.save()
        painter.translate(x, y)
        painter.rotate(rotacion)

        color_led_estado = QtGui.QColor("#10B981") if detectando else QtGui.QColor("#EF4444")
        color_borde_pcb = QtGui.QColor("#38BDF8") if detectando else QtGui.QColor("#0369A1")

        w_pcb, h_pcb = 14.0, 32.0
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0284C7")))
        painter.setPen(QtGui.QPen(color_borde_pcb, 1.0))
        painter.drawRoundedRect(QtCore.QRectF(-w_pcb/2, -h_pcb/2, w_pcb, h_pcb), 2, 2)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#080D1A"), 0.8))
        painter.drawEllipse(QtCore.QPointF(0, -2), 1.8, 1.8)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 0.6))
        painter.drawRect(QtCore.QRectF(-4.5, 3, 9, 6))

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1D4ED8")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E40AF"), 0.8))
        painter.drawRect(QtCore.QRectF(-3.5, -10, 7, 7))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F8FAFC")))
        painter.drawEllipse(QtCore.QPointF(0, -6.5), 1.8, 1.8)
        painter.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 0.6))
        painter.drawLine(QtCore.QPointF(-1.2, -6.5), QtCore.QPointF(1.2, -6.5))
        painter.drawLine(QtCore.QPointF(0, -7.7), QtCore.QPointF(0, -5.3))

        painter.setBrush(QtGui.QBrush(color_led_estado))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(-3.5, 0, 2.5, 1.8))

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.drawRect(QtCore.QRectF(-5, -h_pcb/2 - 2, 10, 3))
        painter.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 1.2))
        for px in [-3, 0, 3]:
            painter.drawLine(QtCore.QPointF(px, -h_pcb/2 - 2), QtCore.QPointF(px, -h_pcb/2 - 6))

        painter.setBrush(QtGui.QBrush(QtGui.QColor(226, 232, 240, 210)))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 0.8))
        painter.drawRoundedRect(QtCore.QRectF(-4.5, h_pcb/2 - 1, 4, 7), 2, 2)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#09090B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#27272A"), 0.8))
        painter.drawRoundedRect(QtCore.QRectF(0.5, h_pcb/2 - 1, 4, 7), 2, 2)

        if detectando:
            painter.setPen(QtGui.QPen(QtGui.QColor(16, 185, 129, 210), 1.8, QtCore.Qt.SolidLine))
            painter.drawLine(QtCore.QPointF(-2.5, h_pcb/2 + 6), QtCore.QPointF(-2.5, h_pcb/2 + 22))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(16, 185, 129, 60)))
            painter.drawEllipse(QtCore.QPointF(0, h_pcb/2 + 18), 6, 6)
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor(239, 68, 68, 120), 1.2, QtCore.Qt.DotLine))
            painter.drawLine(QtCore.QPointF(-2.5, h_pcb/2 + 6), QtCore.QPointF(-2.5, h_pcb/2 + 18))

        painter.restore()

    def _dibujar_sensor_ky032_cenital(self, painter, x, y, detectando: bool):
        painter.save()
        painter.translate(x, y)

        color_led_estado = QtGui.QColor("#10B981") if detectando else QtGui.QColor("#EF4444")
        color_borde_pcb = QtGui.QColor("#10B981") if detectando else QtGui.QColor("#475569")

        w_pcb, h_pcb = 16.0, 36.0
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(color_borde_pcb, 1.2))
        painter.drawRoundedRect(QtCore.QRectF(-w_pcb/2, -h_pcb/2, w_pcb, h_pcb), 2.5, 2.5)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#000000")))
        painter.drawRect(QtCore.QRectF(-6, -h_pcb/2 - 2, 12, 3))
        painter.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 1.2))
        for px in [-4.5, -1.5, 1.5, 4.5]:
            painter.drawLine(QtCore.QPointF(px, -h_pcb/2 - 2), QtCore.QPointF(px, -h_pcb/2 - 6))

        for py in [-10, -2]:
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#0284C7")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#0369A1"), 0.6))
            painter.drawRect(QtCore.QRectF(-6, py, 6, 6))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#F8FAFC")))
            painter.drawEllipse(QtCore.QPointF(-3, py + 3), 2.0, 2.0)
            painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 0.5))
            painter.drawLine(QtCore.QPointF(-4.2, py + 3), QtCore.QPointF(-1.8, py + 3))

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#18181B")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(2, -10, 4, 6))

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#18181B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#3F3F46"), 0.6))
        painter.drawRect(QtCore.QRectF(-3.5, 6, 7, 7))

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#EF4444"))) 
        painter.drawRect(QtCore.QRectF(2, 6, 2.5, 2))
        painter.setBrush(QtGui.QBrush(color_led_estado))       
        painter.drawRect(QtCore.QRectF(2, 10, 2.5, 2))

        painter.setBrush(QtGui.QBrush(QtGui.QColor(241, 245, 249, 210)))
        painter.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 0.8))
        painter.drawRoundedRect(QtCore.QRectF(-5.5, h_pcb/2 - 1, 4.5, 7), 2, 2)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#000000")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#27272A"), 0.8))
        painter.drawRoundedRect(QtCore.QRectF(1.0, h_pcb/2 - 1, 4.5, 7), 2, 2)

        if detectando:
            painter.setPen(QtGui.QPen(QtGui.QColor(16, 185, 129, 220), 2.0, QtCore.Qt.SolidLine))
            painter.drawLine(QtCore.QPointF(-3.25, h_pcb/2 + 6), QtCore.QPointF(-3.25, h_pcb/2 + 32))
            painter.setBrush(QtGui.QBrush(QtGui.QColor(16, 185, 129, 65)))
            painter.drawEllipse(QtCore.QPointF(0, h_pcb/2 + 30), 8, 8)
        else:
            painter.setPen(QtGui.QPen(QtGui.QColor(239, 68, 68, 120), 1.2, QtCore.Qt.DotLine))
            painter.drawLine(QtCore.QPointF(-3.25, h_pcb/2 + 6), QtCore.QPointF(-3.25, h_pcb/2 + 24))

        painter.restore()

    def _dibujar_bastidor_comun(self, painter, cx, cy):
        painter.save()

        grad_bastidor = QtGui.QLinearGradient(cx - 210, cy - 250, cx + 210, cy + 200)
        grad_bastidor.setColorAt(0.0, QtGui.QColor("#0F172A"))
        grad_bastidor.setColorAt(0.5, QtGui.QColor("#1E293B"))
        grad_bastidor.setColorAt(1.0, QtGui.QColor("#0F172A"))

        painter.setBrush(QtGui.QBrush(grad_bastidor))
        painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 2.0))

        path_base = QtGui.QPainterPath()
        path_base.addRoundedRect(QtCore.QRectF(cx - 200, cy - 120, 400, 310), 12, 12)
        path_base.addRoundedRect(QtCore.QRectF(cx - 100, cy - 290, 200, 180), 8, 8)
        path_base.addRoundedRect(QtCore.QRectF(cx - 215, cy - 50, 430, 100), 6, 6)
        painter.drawPath(path_base)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#334155")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 1.0))
        painter.drawRect(QtCore.QRectF(cx - 85, cy - 275, 12, 160))
        painter.drawRect(QtCore.QRectF(cx + 73, cy - 275, 12, 160))

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#94A3B8")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 1.0))
        puntos_tornillos = [
            (-195, -105), (195, -105), (-195, 175), (195, 175),
            (-90, -280), (90, -280), (-205, 0), (205, 0)
        ]
        for tx, ty in puntos_tornillos:
            painter.drawEllipse(QtCore.QPointF(cx + tx, cy + ty), 3.0, 3.0)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
            painter.drawEllipse(QtCore.QPointF(cx + tx, cy + ty), 1.2, 1.2)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#94A3B8")))

        painter.restore()

    def _dibujar_silo_cad_estacion1(self, painter, x, y):
        painter.save()

        base_x = x - 62
        base_y = y - 34
        base_w = 40
        base_h = 68

        color_base = QtGui.QColor("#EF4444") if (self.estado_estacion1 == "SIN_VASOS" and self.alerta_parpadeo) else QtGui.QColor("#CBD5E1")
        painter.setBrush(QtGui.QBrush(color_base))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(base_x, base_y, base_w, base_h), 3, 3)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#E2E8F0")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(base_x, base_y, base_w, 14))
        painter.drawRect(QtCore.QRectF(base_x, base_y + base_h - 14, base_w, 14))

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        for px, py in [(base_x + 9, base_y + 7), (base_x + 27, base_y + 7),
                       (base_x + 9, base_y + base_h - 7), (base_x + 27, base_y + base_h - 7)]:
            painter.drawEllipse(QtCore.QPointF(px, py), 2.5, 2.5)

        path_silo = QtGui.QPainterPath()
        path_silo.moveTo(base_x + base_w, base_y)
        path_silo.lineTo(x, base_y)
        path_silo.arcTo(QtCore.QRectF(x - 34, base_y, 68, 68), 90, -180)
        path_silo.lineTo(base_x + base_w, base_y + base_h)
        path_silo.closeSubpath()

        grad_cilindro = QtGui.QLinearGradient(base_x, base_y, x + 34, base_y + base_h)
        grad_cilindro.setColorAt(0.0, QtGui.QColor("#E2E8F0"))
        grad_cilindro.setColorAt(0.6, QtGui.QColor("#CBD5E1"))
        grad_cilindro.setColorAt(1.0, QtGui.QColor("#94A3B8"))
        painter.setBrush(QtGui.QBrush(grad_cilindro))
        painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 2))
        painter.drawPath(path_silo)

        color_borde_orificio = QtGui.QColor("#EF4444") if self.estado_estacion1 == "SIN_VASOS" else QtGui.QColor("#38BDF8")
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#080D1A")))
        painter.setPen(QtGui.QPen(color_borde_orificio, 2))
        painter.drawEllipse(QtCore.QPointF(x, y), 22, 22)

        if self.vasos_en_silo > 0:
            for v in range(self.vasos_en_silo):
                offset = v * 2.2
                painter.setBrush(QtGui.QBrush(QtGui.QColor(241, 245, 249, 180)))
                painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1))
                painter.drawEllipse(QtCore.QPointF(x - offset, y - offset), 20 - (v * 0.8), 20 - (v * 0.8))

        painter.setPen(QtGui.QColor("#F8FAFC"))
        painter.setFont(QtGui.QFont("Segoe UI", 7, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(base_x, base_y - 22, 110, 14), QtCore.Qt.AlignLeft, "ESTACIÓN 1")

        if self.estado_estacion1 == "SIN_VASOS":
            painter.setPen(QtGui.QColor("#EF4444"))
            painter.setFont(QtGui.QFont("Segoe UI", 6, QtGui.QFont.Bold))
            painter.drawText(QtCore.QRectF(base_x, base_y - 11, 110, 12), QtCore.Qt.AlignLeft, "¡SIN VASOS! (0/4)")
        else:
            painter.setPen(QtGui.QColor("#38BDF8"))
            painter.setFont(QtGui.QFont("Segoe UI", 6, QtGui.QFont.Bold))
            painter.drawText(QtCore.QRectF(base_x, base_y - 11, 110, 12), QtCore.Qt.AlignLeft, f"STOCK: {self.vasos_en_silo}/4")

        painter.restore()

    def _dibujar_estacion2_silos_y_tolva_elevados(self, painter, x, y_tolva):
        painter.save()
        y_silos = y_tolva - 56

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#111827")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#374151"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(x - 92, y_silos - 76, 184, 18), 3, 3)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtCore.Qt.NoPen)
        for tx, ty in [(x - 85, y_silos - 68), (x + 85, y_silos - 68)]:
            painter.drawEllipse(QtCore.QPointF(tx, ty), 2.2, 2.2)

        colores_frijol = [QtGui.QColor("#1E293B"), QtGui.QColor("#854D0E"), QtGui.QColor("#EAB308")]
        nombres_silos = ["NEGRO", "PINTO", "PERUANO"]
        pos_silos_x = [x - 50, x, x + 50]

        for s, sx in enumerate(pos_silos_x):
            es_activo = s in self.silos_seleccionados
            color_borde_silo = QtGui.QColor("#38BDF8") if es_activo else QtGui.QColor("#94A3B8")
            ancho_borde = 2.0 if es_activo else 1.5

            painter.setBrush(QtGui.QBrush(QtGui.QColor(241, 245, 249, 130)))
            painter.setPen(QtGui.QPen(color_borde_silo, ancho_borde))
            painter.drawRoundedRect(QtCore.QRectF(sx - 16, y_silos - 68, 32, 38), 3, 3)

            path_cono = QtGui.QPainterPath()
            path_cono.moveTo(sx - 16, y_silos - 30)
            path_cono.lineTo(sx + 16, y_silos - 30)
            path_cono.lineTo(sx + 8, y_silos - 14)
            path_cono.lineTo(sx - 8, y_silos - 14)
            path_cono.closeSubpath()
            painter.setBrush(QtGui.QBrush(QtGui.QColor(241, 245, 249, 150)))
            painter.drawPath(path_cono)

            painter.setBrush(QtGui.QBrush(colores_frijol[s]))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(QtCore.QRectF(sx - 13, y_silos - 64, 26, 30), 2, 2)

            painter.setBrush(QtGui.QBrush(QtGui.QColor("#EA580C")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#9A3412"), 1.0))
            painter.drawRoundedRect(QtCore.QRectF(sx - 18, y_silos - 28, 36, 6), 2, 2)
            painter.drawRect(QtCore.QRectF(sx - 11, y_silos - 22, 3, 14))
            painter.drawRect(QtCore.QRectF(sx + 8, y_silos - 22, 3, 14))

            color_cuerpo_servo = QtGui.QColor("#2563EB") if not self.servos_silos[s] else QtGui.QColor("#38BDF8")
            painter.setBrush(QtGui.QBrush(color_cuerpo_servo))
            painter.setPen(QtGui.QPen(QtGui.QColor("#1D4ED8"), 0.8))
            painter.drawRoundedRect(QtCore.QRectF(sx - 6, y_silos - 18, 12, 18), 1.5, 1.5)

            painter.setBrush(QtGui.QBrush(QtGui.QColor("#E2E8F0")))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(sx - 4.5, y_silos - 14, 9, 7))

            painter.setPen(QtGui.QPen(QtGui.QColor("#F59E0B"), 0.8))
            painter.drawLine(QtCore.QPointF(sx + 6, y_silos - 6), QtCore.QPointF(sx + 10, y_silos - 4))

            ang_rot = self.angulos_compuertas[s]
            cx_disco = sx
            cy_disco = y_silos - 3 

            painter.save()
            painter.translate(cx_disco, cy_disco)
            painter.rotate(ang_rot) 

            color_cuña = QtGui.QColor("#10B981") if self.servos_silos[s] else QtGui.QColor("#84CC16")
            painter.setBrush(QtGui.QBrush(color_cuña))
            painter.setPen(QtGui.QPen(QtGui.QColor("#15803D"), 1.0))
            painter.drawChord(QtCore.QRectF(-8, -8, 16, 16), 0, 180 * 16)

            painter.setBrush(QtGui.QBrush(QtGui.QColor("#F8FAFC")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 0.6))
            painter.drawEllipse(QtCore.QPointF(0, 0), 1.8, 1.8)
            painter.restore()

            color_texto_silo = QtGui.QColor("#38BDF8") if es_activo else QtGui.QColor("#CBD5E1")
            painter.setPen(color_texto_silo)
            painter.setFont(QtGui.QFont("Segoe UI", 4, QtGui.QFont.Bold if es_activo else QtGui.QFont.Normal))
            painter.drawText(QtCore.QRectF(sx - 18, y_silos - 74, 36, 10), QtCore.Qt.AlignCenter, nombres_silos[s])

        path_tolva = QtGui.QPainterPath()
        path_tolva.moveTo(x - 70, y_tolva)
        path_tolva.lineTo(x + 70, y_tolva)
        path_tolva.lineTo(x + 18, y_tolva + 38)
        path_tolva.lineTo(x - 18, y_tolva + 38)
        path_tolva.closeSubpath()

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#C2410C")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#9A3412"), 2))
        painter.drawPath(path_tolva)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#9A3412")))
        painter.drawRect(QtCore.QRectF(x - 74, y_tolva - 2, 8, 8))
        painter.drawRect(QtCore.QRectF(x + 66, y_tolva - 2, 8, 8))

        if self.nivel_tolva > 0.0:
            h_grano = (self.nivel_tolva / 100.0) * 32.0
            color_tolva_grano = QtGui.QColor("#854D0E")
            if self.tipo_frijol_tolva == "NEGRO": color_tolva_grano = QtGui.QColor("#1E293B")
            elif self.tipo_frijol_tolva == "PERUANO": color_tolva_grano = QtGui.QColor("#EAB308")

            path_nivel = QtGui.QPainterPath()
            path_nivel.moveTo(x - 18 - (h_grano * 0.7), y_tolva + 38 - h_grano)
            path_nivel.lineTo(x + 18 + (h_grano * 0.7), y_tolva + 38 - h_grano)
            path_nivel.lineTo(x + 16, y_tolva + 36)
            path_nivel.lineTo(x - 16, y_tolva + 36)
            path_nivel.closeSubpath()

            painter.setBrush(QtGui.QBrush(color_tolva_grano))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPath(path_nivel)

        color_servo4 = QtGui.QColor("#38BDF8") if self.servo_tolva else QtGui.QColor("#1E293B")
        painter.setBrush(QtGui.QBrush(color_servo4))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(x - 14, y_tolva + 38, 28, 8), 2, 2)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
        painter.drawEllipse(QtCore.QPointF(x + 6, y_tolva + 42), 1.5, 1.5)

        if self.servo_tolva:
            color_descarga = QtGui.QColor("#854D0E")
            if self.tipo_frijol_tolva == "NEGRO": color_descarga = QtGui.QColor("#1E293B")
            elif self.tipo_frijol_tolva == "PERUANO": color_descarga = QtGui.QColor("#EAB308")
            painter.setBrush(QtGui.QBrush(color_descarga))
            painter.drawRect(QtCore.QRectF(x - 5, y_tolva + 46, 10, 42))

        self._dibujar_sensor_ky032_cenital(painter, x, y_tolva - 24, self.sensor_ky032_tolva)

        painter.restore()

    def _dibujar_estacion25_dispensador_tapas_hd(self, painter, x, y):
        """Renderiza la Estación 2.5 en Capa Superior HD (Silo Transparente de Tapas Negras)."""
        painter.save()
        painter.translate(x, y)

        # Soporte de Aluminio
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#334155")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0284C7"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(-20, -36, 40, 68), 4, 4)

        # Silo Cilíndrico Transparente
        painter.setBrush(QtGui.QBrush(QtGui.QColor(56, 189, 248, 40)))
        painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(-16, -32, 32, 54), 3, 3)

        # Pila de Tapas Negras dentro del Silo
        for i in range(4):
            py = -24 + (i * 10)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#18181B")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#3F3F46"), 1.0))
            painter.drawRoundedRect(QtCore.QRectF(-14, py, 28, 7), 2, 2)
            # Brillo superior de la tapa
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#27272A")))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(-12, py + 1, 24, 2))

        # Servo Dispensador Azul MG90S
        color_servo = QtGui.QColor("#10B981") if self.tapa_dispensando_anim else QtGui.QColor("#2563EB")
        painter.setBrush(QtGui.QBrush(color_servo))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E40AF"), 1.0))
        painter.drawRoundedRect(QtCore.QRectF(16, -12, 16, 24), 2, 2)

        # Brazo Mecánico Retractor
        painter.save()
        painter.translate(16, 0)
        painter.rotate(self.angulo_servo_tapas)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F8FAFC")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 0.8))
        painter.drawRoundedRect(QtCore.QRectF(-22, -4, 24, 8), 2, 2)
        painter.restore()

        # Etiqueta de Identificación HD
        painter.setPen(QtGui.QColor("#F8FAFC"))
        painter.setFont(QtGui.QFont("Segoe UI", 6, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(-35, -50, 70, 12), QtCore.Qt.AlignCenter, "ESTACIÓN 2.5")
        painter.setPen(QtGui.QColor("#38BDF8"))
        painter.setFont(QtGui.QFont("Segoe UI", 5, QtGui.QFont.Normal))
        painter.drawText(QtCore.QRectF(-35, -40, 70, 10), QtCore.Qt.AlignCenter, "DISP. TAPAS")

        painter.restore()

    def _dibujar_estacion3_prensa_hd(self, painter, cx, cy):
        """Renderiza la Estación 3 (Sellador Térmico) en Capa Superior HD."""
        painter.save()
        
        # Bastidor Estación 3
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#C2410C")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#9A3412"), 2))
        painter.drawRoundedRect(QtCore.QRectF(cx + 140, cy - 65, 46, 130), 4, 4)
        
        # Actuador Lineal y Cabezal de Prensado (Animado)
        offset_sello = self.pos_piston_sello * 22.0
        color_piston = QtGui.QColor("#38BDF8") if self.sellando_activo else QtGui.QColor("#F8FAFC")
        
        painter.setBrush(QtGui.QBrush(color_piston))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1))
        painter.drawRect(QtCore.QRectF(cx + 150 - offset_sello, cy - 110, 16 + offset_sello, 75))

        # Placa Térmica Presionadora
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0284C7")))
        painter.drawRoundedRect(QtCore.QRectF(cx + 144 - offset_sello, cy - 20, 8, 40), 2, 2)

        # Texto Estación 3
        painter.setPen(QtGui.QColor("#F8FAFC"))
        painter.setFont(QtGui.QFont("Segoe UI", 6, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(cx + 130, cy - 80, 66, 12), QtCore.Qt.AlignCenter, "ESTACIÓN 3")

        painter.restore()

    def _dibujar_lluvia_granos(self, painter):
        painter.save()
        for p in self.particulas_frijol:
            painter.save()
            painter.translate(p["x"], p["y"])
            painter.rotate(p["angulo"])
            painter.setBrush(QtGui.QBrush(p["color"]))
            painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 70), 0.6))
            painter.drawEllipse(QtCore.QPointF(0, 0), p["rx"], p["ry"])
            painter.restore()
        painter.restore()

    def _dibujar_anillo_guia(self, painter, cx, cy):
        painter.save()
        r_ext = 190.0
        r_int = 110.0

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#111827")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#374151"), 3))
        painter.drawEllipse(QtCore.QPointF(cx, cy), r_ext, r_ext)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#080D1A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1F2937"), 2))
        painter.drawEllipse(QtCore.QPointF(cx, cy), r_int, r_int)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#080D1A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#10B981"), 2, QtCore.Qt.DashLine))
        painter.drawRoundedRect(QtCore.QRectF(cx - 30, cy + 125, 60, 68), 6, 6)

        if self.descargando_anim:
            self._dibujar_vaso_cilindrico(painter, self.pos_descarga_x, self.pos_descarga_y + self.y_vaso_descarga, tipo=self.tipo_vaso_descarga, alpha=160)

        painter.restore()

    def _dibujar_estrella_malta_real(self, painter, cx, cy, angulo):
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(angulo)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#D1D5DB")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#9CA3AF"), 2))

        path_estrella = QtGui.QPainterPath()
        num_pos = 8
        r_outer_tip = 162.0
        r_concave_pocket = 120.0

        for i in range(num_pos):
            ang_deg = i * 45.0
            ang_prev_tip = ang_deg - 22.5
            ang_next_tip = ang_deg + 22.5

            rad_prev_tip_r = math.radians(ang_prev_tip + 10.0)
            p_prev_tip_r = QtCore.QPointF(r_outer_tip * math.cos(rad_prev_tip_r), r_outer_tip * math.sin(rad_prev_tip_r))

            rad_pocket = math.radians(ang_deg)
            p_pocket_bottom = QtCore.QPointF(r_concave_pocket * math.cos(rad_pocket), r_concave_pocket * math.sin(rad_pocket))

            rad_next_tip_l = math.radians(ang_next_tip - 10.0)
            p_next_tip_l = QtCore.QPointF(r_outer_tip * math.cos(rad_next_tip_l), r_outer_tip * math.sin(rad_next_tip_l))

            rad_next_tip_r = math.radians(ang_next_tip + 10.0)
            p_next_tip_r = QtCore.QPointF(r_outer_tip * math.cos(rad_next_tip_r), r_outer_tip * math.sin(rad_next_tip_r))

            if i == 0:
                path_estrella.moveTo(p_prev_tip_r)

            path_estrella.quadTo(p_pocket_bottom, p_next_tip_l)
            path_estrella.lineTo(p_next_tip_r)

        path_estrella.closeSubpath()
        painter.drawPath(path_estrella)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#080D1A")))
        painter.setPen(QtCore.Qt.NoPen)
        for i in range(num_pos):
            ang_tip = math.radians(i * 45.0 + 22.5)
            ang_a = math.radians(i * 45.0 + 9.0)
            ang_b = math.radians(i * 45.0 + 36.0)

            p_a = QtCore.QPointF(55.0 * math.cos(ang_a), 55.0 * math.sin(ang_a))
            p_top = QtCore.QPointF(112.0 * math.cos(ang_tip), 112.0 * math.sin(ang_tip))
            p_b = QtCore.QPointF(55.0 * math.cos(ang_b), 55.0 * math.sin(ang_b))

            path_cavidad = QtGui.QPainterPath()
            path_cavidad.moveTo(p_a)
            path_cavidad.lineTo(p_top)
            path_cavidad.lineTo(p_b)
            path_cavidad.closeSubpath()
            painter.drawPath(path_cavidad)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1F2937")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#9CA3AF"), 2))
        painter.drawEllipse(QtCore.QPointF(0, 0), 22, 22)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
        painter.drawEllipse(QtCore.QPointF(0, 0), 6, 6)

        painter.restore()

    def _dibujar_vasos(self, painter, cx, cy, angulo_estrella):
        r_pocket_center = 138.0
        
        for i in range(8):
            tipo = self.vasos_en_slots[i]
            if tipo is not None or (self.dispensando_vaso_anim and self.slot_dispensando == i):
                ang_deg = (i * 45.0) + angulo_estrella
                rad = math.radians(ang_deg)
                vx = cx + r_pocket_center * math.cos(rad)
                vy = cy + r_pocket_center * math.sin(rad)

                if self.dispensando_vaso_anim and self.slot_dispensando == i:
                    vy += self.y_vaso_caida

                tiene_tapa = self.vasos_con_tapa[i]
                self._dibujar_vaso_cilindrico(painter, vx, vy, tipo=tipo or "VACIO", con_tapa=tiene_tapa)

    def _dibujar_vaso_cilindrico(self, painter, x, y, tipo="VACIO", con_tapa=False, alpha=240):
        painter.save()

        # Cuerpo del vaso transparente/acrílico
        painter.setBrush(QtGui.QBrush(QtGui.QColor(241, 245, 249, alpha)))
        painter.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(x - 22, y - 24, 44, 48), 7, 7)

        mapa_colores = {
            "NEGRO": QtGui.QColor("#1E293B"),
            "PINTO": QtGui.QColor("#854D0E"),
            "PERUANO": QtGui.QColor("#EAB308"),
        }

        if tipo in mapa_colores:
            color_grano = mapa_colores[tipo]
            painter.setBrush(QtGui.QBrush(color_grano))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(QtCore.QRectF(x - 18, y - 8, 36, 28), 4, 4)
            color_boca = color_grano
        else:
            color_boca = QtGui.QColor("#94A3B8")

        # RENDERIZADO DE TAPA NEGRA INDUSTRIAL CON RELIEVE 3D
        if con_tapa:
            # Cuerpo principal de polímero negro acoplado a la boca
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#18181B")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#3F3F46"), 1.2))
            painter.drawRoundedRect(QtCore.QRectF(x - 23, y - 26, 46, 8), 3, 3)

            # Estriado/Relieve superior de la tapa negra
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#27272A")))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(x - 20, y - 25, 40, 2))
        else:
            # Boca del envase libre/sin tapa
            painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, alpha)))
            painter.setPen(QtGui.QPen(color_boca, 1.5))
            painter.drawEllipse(QtCore.QPointF(x, y - 20), 19, 5)

        # Base del envase
        painter.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 1.5))
        painter.drawEllipse(QtCore.QPointF(x, y + 20), 19, 5)

        painter.restore()

    # ------------------------------------------------------------------
    # Gemelo compartido (añadido en v1.2.0). El publicador exporta su estado; el espejo lo recibe.
    # El espejo NO ejecuta la lógica del proceso: solo suaviza el movimiento hacia lo recibido.
    # ------------------------------------------------------------------
    espejo = False
    _tolva_obj = 0.0

    def exportar_estado(self) -> dict:
        """Estado del proceso en tipos simples (viaja como JSON, ~0.5 KB)."""
        return {
            "modo": self.modo_operacion, "receta": self.secuencia_auto_tipo,
            "dinamica": self.es_secuencia_dinamica, "resumen": self.texto_resumen_secuencia,
            "motor": self.estado_motor_txt, "ang_obj": self.angulo_objetivo, "silo": self.vasos_en_silo,
            "slots": list(self.vasos_en_slots), "tapas": list(self.vasos_con_tapa),
            "terminados": self.vasos_terminados, "est1": self.estado_estacion1,
            "tolva": round(self.nivel_tolva, 1), "tipo_tolva": self.tipo_frijol_tolva,
            "servo_tolva": self.servo_tolva, "servos": list(self.servos_silos), "fase": self.fase_dosif,
            "silo_desc": self.silo_en_descarga, "comp_obj": list(self.angulos_objetivo),
            "silos_sel": list(self.silos_seleccionados), "tapa_obj": self.angulo_servo_tapas_obj,
            "tapa_anim": self.tapa_dispensando_anim, "piston_obj": self.pos_piston_sello_obj,
            "sellando": self.sellando_activo,
        }

    def importar_estado(self, d: dict):
        """Aplica un estado recibido (solo en modo espejo). Los datos incompletos se ignoran campo a campo."""
        self.modo_operacion = d.get("modo", self.modo_operacion)
        self.secuencia_auto_tipo = d.get("receta", self.secuencia_auto_tipo)
        self.es_secuencia_dinamica = bool(d.get("dinamica", self.es_secuencia_dinamica))
        self.texto_resumen_secuencia = d.get("resumen", self.texto_resumen_secuencia)
        self.estado_motor_txt = d.get("motor", self.estado_motor_txt)
        destino = float(d.get("ang_obj", self.angulo_objetivo))
        if abs(destino - self.angulo_estrella) > 200.0:  # quien llega tarde salta, no gira vueltas
            self.angulo_estrella = destino
        self.angulo_objetivo = destino
        self.vasos_en_silo = int(d.get("silo", self.vasos_en_silo))
        for clave, atributo in (("slots", "vasos_en_slots"), ("tapas", "vasos_con_tapa")):
            valor = d.get(clave)
            if isinstance(valor, list) and len(valor) == 8:
                setattr(self, atributo, list(valor))
        self.vasos_terminados = int(d.get("terminados", self.vasos_terminados))
        self.estado_estacion1 = d.get("est1", self.estado_estacion1)
        self._tolva_obj = float(d.get("tolva", self._tolva_obj))
        self.tipo_frijol_tolva = d.get("tipo_tolva", self.tipo_frijol_tolva)
        self.servo_tolva = bool(d.get("servo_tolva", self.servo_tolva))
        self.fase_dosif = d.get("fase", self.fase_dosif)
        self.dosificando_activo = self.fase_dosif != "REPOSO"
        self.silo_en_descarga = int(d.get("silo_desc", self.silo_en_descarga))
        self.angulo_servo_tapas_obj = float(d.get("tapa_obj", self.angulo_servo_tapas_obj))
        self.tapa_dispensando_anim = bool(d.get("tapa_anim", self.tapa_dispensando_anim))
        self.pos_piston_sello_obj = float(d.get("piston_obj", self.pos_piston_sello_obj))
        self.sellando_activo = bool(d.get("sellando", self.sellando_activo))
        for clave, atributo, largo in (("servos", "servos_silos", 3), ("comp_obj", "angulos_objetivo", 3)):
            valor = d.get(clave)
            if isinstance(valor, list) and len(valor) == largo:
                setattr(self, atributo, list(valor))
        sel = d.get("silos_sel")
        if isinstance(sel, list):
            self.silos_seleccionados = list(sel)
        self.update()

    def _animar_espejo(self):
        """Solo lo visual: acerca los valores mostrados a los recibidos. No decide nada del proceso."""
        cambio = False
        if abs(self.angulo_estrella - self.angulo_objetivo) > 0.3:
            self.angulo_estrella += (self.angulo_objetivo - self.angulo_estrella) * 0.18
            cambio = True
        elif self.angulo_estrella != self.angulo_objetivo:
            self.angulo_estrella = self.angulo_objetivo
            cambio = True
        if abs(self.angulo_servo_tapas_obj - self.angulo_servo_tapas) > 0.5:
            self.angulo_servo_tapas += 10.0 if self.angulo_servo_tapas_obj > self.angulo_servo_tapas else -10.0
            cambio = True
        if abs(self.pos_piston_sello_obj - self.pos_piston_sello) > 0.02:
            self.pos_piston_sello += 0.08 if self.pos_piston_sello_obj > self.pos_piston_sello else -0.08
            cambio = True
        if abs(self._tolva_obj - self.nivel_tolva) > 0.5:
            self.nivel_tolva += max(-8.0, min(8.0, self._tolva_obj - self.nivel_tolva))
            cambio = True
        for s in range(3):
            obj, act = self.angulos_objetivo[s], self.angulos_compuertas[s]
            if abs(obj - act) > 0.5:
                paso = 4.5 if obj > act else 5.5
                self.angulos_compuertas[s] = min(obj, act + paso) if act < obj else max(obj, act - paso)
                cambio = True
        e1 = e2 = e3 = False
        for i in range(8):
            ang = ((i * 45.0) + self.angulo_estrella) % 360.0
            if self.vasos_en_slots[i] is None:
                continue
            e1 = e1 or abs(ang - 180.0) <= 7.0
            e2 = e2 or abs(ang - 270.0) <= 7.0
            e3 = e3 or abs(ang - 0.0) <= 7.0 or abs(ang - 360.0) <= 7.0
        tolva_ok = self.nivel_tolva >= 75.0
        if (self.sensor_fc51_e1, self.sensor_fc51_e2, self.sensor_fc51_e3, self.sensor_ky032_tolva) != (e1, e2, e3, tolva_ok):
            self.sensor_fc51_e1, self.sensor_fc51_e2, self.sensor_fc51_e3, self.sensor_ky032_tolva = e1, e2, e3, tolva_ok
            cambio = True
        if self.fase_dosif == "VERTIDO" and self.silo_en_descarga >= 0:
            self._generar_particulas_frijol(self.silo_en_descarga)
        if self.particulas_frijol:
            vivas = []
            for p in self.particulas_frijol:
                p["x"] += p["vx"]
                p["y"] += p["vy"]
                p["vy"] += 0.35
                p["vida"] -= 1
                if p["vida"] > 0:
                    vivas.append(p)
            self.particulas_frijol = vivas
            cambio = True
        if cambio:
            self.update()
