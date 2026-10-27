# Portado de WESKER 3.0 sin cambios: es una vista pura que se alimenta con set_telemetria().
# -*- coding: utf-8 -*-
"""
========================================================================================
PROYECTO: W.E.S.K.E.R. 3.0 - GEMELO DIGITAL ZENO-01 (ULTRA-ALTA FIDELIDAD CAD 2D)
SISTEMA: RENDERIZADO VECTORIAL INDUSTRIAL EN TIEMPO REAL
AUTOR: PEDRO DAMIAN URQUIETA SALAZAR (DUS)
========================================================================================
DETALLES CINEMÁTICOS Y COMPONENTES MODELADOS:
 - CHASIS BLANCO MECANIZADO CON ALAS ANCHAS Y BISELES INDUSTRIALES
 - DIRECCIÓN ACKERMAN DINÁMICA CON SERVOMOTOR MG995, RÓTULAS DE LATÓN Y C-HUBS
 - REGLETA FRONTAL BFD-1000 DE 5 CANALES TCRT5000 (S1..S5) 100% FUNCIONAL Y CALIBRADA
 - RASPBERRY PI 3 B+ CON BLINDAJE RF, BCM2837B0, PUERTOS Y CABEZAL GPIO REACTIVO (40 PINES)
 - CONVERTIDORES BUCK EN PARALELO VERTICAL: LM2596 (5.0V LÓGICA) + XL4015 (5.1V 5A ALTO TORQUE)
 - PUENTE H INDUSTRIAL BTS7960 (IBT-2) CON BORNERAS DE POTENCIA Y CHIPS DUALES
 - TREN DE TRACCIÓN TRASERO: MOTOR RS-550 METÁLICO, BOBINADO DE COBRE Y CORONA HELICOIDAL
 - RUEDAS INDUSTRIALES OFF-ROAD CON HUELLA EN V Y TACOS ANIMADOS POR CONSUMO PWM
========================================================================================
"""

import math
from PyQt5 import QtWidgets, QtGui, QtCore

class ZenoDigitalTwin(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(460, 580)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # Variables de cinemática y dinámica
        self.direccion = "S"          # "F", "B", "L", "R", "S", "ESTACION", "FL", "FR", "BL", "BR"
        self.velocidad_pwm = 0        # 0 - 100 %
        self.angulo_direccion = 0.0   # Ángulo Ackerman (-22.0° a +22.0°)
        self.angulo_rodadura = 0.0    # Grados de rotación de banda de rodadura
        self.angulo_engrane = 0.0     # Grados de rotación de la transmisión
        self.distancia_frontal = 85.0 # Sensor ultrasónico en cm
        self.subestado = "SEGUIMIENTO"
        self.modo = "AUTO"
        self.estacion_qr = "NINGUNO"
        self.logistica = None

        # Barra BFD-1000: S1, S2, S3, S4, S5 (Todos activos e independientes)
        self.sensores_linea = [False, False, False, False, False]

        # Parpadeo de seguridad en estación de descarga / detección QR
        self._parpadeo = False
        self._timer_parpadeo = QtCore.QTimer(self)
        self._timer_parpadeo.timeout.connect(self._tick_parpadeo)
        self._timer_parpadeo.start(450)

        # Bucle de renderizado vectorial continuo a 30 FPS (33 ms)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._animar)
        self.timer.start(33)

    def _tick_parpadeo(self):
        self._parpadeo = not self._parpadeo
        if self.subestado == "ESTACION_DESCARGA" or self.estacion_qr != "NINGUNO":
            self.update()

    def set_logistica(self, d):
        """Estado de la ruta real (o None): d["fase"], d["estacion"], d["carga_r1"], d["carga_r2"] (bool), d["alarma"],
        d["restante_s"], d["servos"] = {direccion, camara, rampa1, rampa2: grados o None}.
        Solo se guarda: la capa superior dinámica del gemelo (rampas cargadas/abiertas) puede leer self.logistica al dibujar."""
        self.logistica = d if isinstance(d, dict) else None
        self.update()

    def set_modo(self, modo: str):
        self.modo = modo
        self.update()

    def set_telemetria(self, direccion: str, velocidad: int, distancia: float = 85.0, sensores: list = None, subestado: str = "SEGUIMIENTO", qr: str = "NINGUNO"):
        """
        Actualiza el estado cinemático del gemelo digital con validación de tramas.
        Soporta los 5 canales de la BFD-1000 y el descriptor de estación QR.
        """
        self.direccion = direccion
        self.velocidad_pwm = max(0, min(100, int(velocidad)))
        self.distancia_frontal = float(distancia)
        self.subestado = subestado
        self.estacion_qr = str(qr)

        # Mapeo angular de dirección Ackerman
        if "L" in direccion:
            self.angulo_direccion = -22.0
        elif "R" in direccion:
            self.angulo_direccion = 22.0
        else:
            self.angulo_direccion = 0.0

        # Actualización de los 5 canales con tolerancia a listas variables
        if sensores is not None and isinstance(sensores, (list, tuple)):
            num_sensores = len(sensores)
            self.sensores_linea = [
                bool(sensores[0]) if num_sensores > 0 else False,
                bool(sensores[1]) if num_sensores > 1 else False,
                bool(sensores[2]) if num_sensores > 2 else False,
                bool(sensores[3]) if num_sensores > 3 else False,
                bool(sensores[4]) if num_sensores > 4 else False
            ]

        self.update()

    def _animar(self):
        """Calcula el desfase cinemático de engranes y neumáticos según el PWM activo."""
        if self.subestado != "ESTACION_DESCARGA" and self.direccion in ["F", "B", "L", "R", "FL", "FR", "BL", "BR"] and self.velocidad_pwm > 0:
            paso = (self.velocidad_pwm / 100.0) * 14.0
            if "F" in self.direccion or self.direccion in ["L", "R"]:
                self.angulo_rodadura = (self.angulo_rodadura + paso) % 360
                self.angulo_engrane = (self.angulo_engrane + paso * 1.5) % 360
            elif "B" in self.direccion:
                self.angulo_rodadura = (self.angulo_rodadura - paso) % 360
                self.angulo_engrane = (self.angulo_engrane - paso * 1.5) % 360
            self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing)

        w, h = self.width(), self.height()

        # Fondo CAD Blueprint Oscuro
        painter.fillRect(0, 0, w, h, QtGui.QColor("#080D1A"))

        # Cuadrícula métrica industrial
        painter.setPen(QtGui.QPen(QtGui.QColor("#131C31"), 1, QtCore.Qt.DotLine))
        for gx in range(0, w, 25):
            painter.drawLine(gx, 0, gx, h)
        for gy in range(0, h, 25):
            painter.drawLine(0, gy, w, gy)

        # Escalado dinámico uniforme para mantener proporciones en cualquier pantalla
        painter.save()
        base_w, base_h = 470.0, 560.0
        scale_x = (w - 10) / base_w
        scale_y = (h - 55) / base_h
        scale = min(scale_x, scale_y) * 1.15

        painter.translate(w / 2.0, (h - 35) / 2.0)
        painter.scale(scale, scale)

        cx, cy = 0.0, 0.0
        y_direccion = cy - 155
        y_rpi = cy - 90
        y_eje_trasero = cy + 105

        # -------------------------------------------------------------
        # 1. PISTA INDUSTRIAL Y ZONA DE ARRIBO / ESTACIÓN DE DESCARGA
        # -------------------------------------------------------------
        if self.subestado == "ESTACION_DESCARGA":
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#020617")))
            color_borde = QtGui.QColor("#EF4444") if self._parpadeo else QtGui.QColor("#7F1D1D")
            painter.setPen(QtGui.QPen(color_borde, 3))
            painter.drawRoundedRect(QtCore.QRectF(cx - 180, y_direccion - 85, 360, 48), 4, 4)
            painter.setPen(QtGui.QPen(color_borde, 1))
            painter.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Bold))
            texto_estacion = f"PARADA EN ESTACIÓN [{self.estacion_qr}]" if self.estacion_qr != "NINGUNO" else "ESTACIÓN DE DESCARGA"
            painter.drawText(QtCore.QRectF(cx - 180, y_direccion - 85, 360, 48), QtCore.Qt.AlignCenter, texto_estacion)
        else:
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#020617")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 1))
            painter.drawRect(QtCore.QRectF(cx - 44, y_direccion - 120, 20, 400))

        # -------------------------------------------------------------
        # 2. CONO DE RADIACIÓN DEL SENSOR ULTRASÓNICO FRONTAL
        # -------------------------------------------------------------
        color_cono = QtGui.QColor(34, 197, 94, 55) if self.distancia_frontal > 35 else QtGui.QColor(239, 68, 68, 110)
        painter.setBrush(QtGui.QBrush(color_cono))
        painter.setPen(QtCore.Qt.NoPen)
        path_sensor = QtGui.QPainterPath()
        path_sensor.moveTo(cx, y_direccion - 85)
        path_sensor.lineTo(cx - 105, y_direccion - 140)
        path_sensor.arcTo(cx - 105, y_direccion - 160, 210, 45, 45, 90)
        path_sensor.closeSubpath()
        painter.drawPath(path_sensor)

        # -------------------------------------------------------------
        # 3. CHASIS BLANCO INDUSTRIAL MECANIZADO (3 ALAS ANCHAS)[cite: 3]
        # -------------------------------------------------------------
        grad_chasis = QtGui.QLinearGradient(cx - 150, 0, cx + 150, 0)
        grad_chasis.setColorAt(0.0, QtGui.QColor("#F1F5F9"))
        grad_chasis.setColorAt(0.5, QtGui.QColor("#FFFFFF"))
        grad_chasis.setColorAt(1.0, QtGui.QColor("#E2E8F0"))

        painter.setBrush(QtGui.QBrush(grad_chasis))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 2))
        
        path_chasis = QtGui.QPainterPath()
        path_chasis.addRect(QtCore.QRectF(cx - 36, y_direccion - 80, 72, 380))
        path_chasis.addRoundedRect(QtCore.QRectF(cx - 150, y_direccion - 85, 300, 42), 6, 6) # Delantero[cite: 3]
        path_chasis.addRoundedRect(QtCore.QRectF(cx - 155, y_rpi - 10, 310, 110), 6, 6)      # Bahía Central[cite: 3]
        path_chasis.addRoundedRect(QtCore.QRectF(cx - 150, y_eje_trasero + 65, 300, 42), 6, 6) # Trasero[cite: 3]
        painter.drawPath(path_chasis)

        # Tornillería de ensamble de chasis
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#64748B")))
        painter.setPen(QtCore.Qt.NoPen)
        for tx, ty in [(-140, y_direccion - 75), (140, y_direccion - 75), 
                       (-145, y_rpi), (145, y_rpi), (-145, y_rpi + 90), (145, y_rpi + 90),
                       (-140, y_eje_trasero + 95), (140, y_eje_trasero + 95)]:
            painter.drawEllipse(QtCore.QPointF(cx + tx, ty), 2.2, 2.2)

        # Sub-base de montaje electrónica aislante
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(cx - 72, y_rpi - 4, 142, 98), 4, 4)

        # -------------------------------------------------------------
        # 4. REGLETA BFD-1000 FRONTAL DE 5 CANALES TCRT5000[cite: 2]
        # -------------------------------------------------------------
        self._dibujar_sensor_bfd1000(painter, cx, y_direccion - 65)

        # -------------------------------------------------------------
        # 5. DIRECCIÓN ACKERMAN CON SERVOMOTOR MG995 Y RÓTULAS
        # -------------------------------------------------------------
        self._dibujar_direccion_delantera(painter, cx, y_direccion)

        # -------------------------------------------------------------
        # 6. RASPBERRY PI 3 B+ CON CABEZAL GPIO DE 40 PINES
        # -------------------------------------------------------------
        self._dibujar_raspberry_pi(painter, cx - 4, y_rpi + 1, 68, 88)

        # -------------------------------------------------------------
        # 7. REGULADORES STEP-DOWN: LM2596 (IZQ) Y XL4015 (DER)[cite: 1, 2, 4]
        # -------------------------------------------------------------
        self._dibujar_lm2596_hd(painter, cx - 67, y_rpi + 14, 28, 56)
        self._dibujar_xl4015_hd(painter, cx - 36, y_rpi + 14, 29, 56)

        # Cableado de potencia técnica (XL4015 a Pines 2 y 6 de la RPi)
        painter.setPen(QtGui.QPen(QtGui.QColor("#EF4444"), 2.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.drawLine(int(cx - 24), int(y_rpi + 14), int(cx - 24), int(y_rpi - 7))
        painter.drawLine(int(cx - 24), int(y_rpi - 7), int(cx + 58), int(y_rpi - 7))
        painter.drawLine(int(cx + 58), int(y_rpi - 7), int(cx + 58), int(y_rpi + 12))

        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 2.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        painter.drawLine(int(cx - 18), int(y_rpi + 14), int(cx - 18), int(y_rpi - 3))
        painter.drawLine(int(cx - 18), int(y_rpi - 3), int(cx + 61), int(y_rpi - 3))
        painter.drawLine(int(cx + 61), int(y_rpi - 3), int(cx + 61), int(y_rpi + 18))

        # -------------------------------------------------------------
        # 8. TREN DE POTENCIA TRASERO (MOTOR DC RS-550 + ENGRANAJES)
        # -------------------------------------------------------------
        self._dibujar_tren_potencia(painter, cx, y_eje_trasero)

        # -------------------------------------------------------------
        # 9. CONTROLADOR PUENTE H BTS7960 (IBT-2)
        # -------------------------------------------------------------
        self._dibujar_bts7960(painter, cx - 35, y_eje_trasero + 20, 70, 72)

        # -------------------------------------------------------------
        # 10. RUEDAS TRASERAS TRACTORAS
        # -------------------------------------------------------------
        color_llanta = QtGui.QColor("#1E293B")
        self._dibujar_rueda(painter, cx - 156, y_eje_trasero - 44, 42, 88, 0.0, self.angulo_rodadura, color_llanta)
        self._dibujar_rueda(painter, cx + 114, y_eje_trasero - 44, 42, 88, 0.0, self.angulo_rodadura, color_llanta)

        painter.restore()

        # -------------------------------------------------------------
        # 11. HUD INFERIOR TÁCTICO DE TELEMETRÍA INTEGRADA
        # -------------------------------------------------------------
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A")))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0B1329")))
        painter.drawRoundedRect(QtCore.QRectF(10, h - 55, w - 20, 48), 6, 6)

        color_estado = QtGui.QColor("#EF4444") if self.subestado == "ESTACION_DESCARGA" else QtGui.QColor("#10B981")
        painter.setPen(color_estado)
        painter.setFont(QtGui.QFont("Segoe UI", 9, QtGui.QFont.Bold))
        info_qr = f" | ESTACIÓN: {self.estacion_qr}" if self.estacion_qr != "NINGUNO" else ""
        painter.drawText(20, h - 35, f"ESTADO: {self.subestado}{info_qr} | MODO: {self.modo} | DIR: {self.direccion} ({self.angulo_direccion:+.1f}°)")

        str_sensores = f"[S1:{int(self.sensores_linea[0])} S2:{int(self.sensores_linea[1])} S3:{int(self.sensores_linea[2])} S4:{int(self.sensores_linea[3])} S5:{int(self.sensores_linea[4])}]"
        painter.setPen(QtGui.QColor("#94A3B8"))
        painter.setFont(QtGui.QFont("Segoe UI", 8))
        painter.drawText(20, h - 18, f"BFD-1000 (5CH): {str_sensores} | PWM: {self.velocidad_pwm}% | BUCKS: LM2596(5V) + XL4015(5.1V 5A)")

    # =========================================================================
    # RENDERIZADO CALIBRADO: REGLETA BFD-1000 DE 5 CANALES TCRT5000[cite: 2]
    # =========================================================================
    def _dibujar_sensor_bfd1000(self, painter, cx, cy):
        painter.save()

        pcb_w, pcb_h = 168.0, 28.0
        pcb_x = cx - pcb_w / 2.0
        pcb_y = cy - pcb_h / 2.0

        # Contorno característico con alas angulares y conector central de la BFD-1000[cite: 2]
        path_bfd = QtGui.QPainterPath()
        path_bfd.moveTo(pcb_x + 6, pcb_y)
        path_bfd.lineTo(cx - 22, pcb_y)
        path_bfd.lineTo(cx, pcb_y - 6)          # Punta angular del switch/sensor de choque central[cite: 2]
        path_bfd.lineTo(cx + 22, pcb_y)
        path_bfd.lineTo(pcb_x + pcb_w - 6, pcb_y)
        path_bfd.lineTo(pcb_x + pcb_w, pcb_y + 8)
        path_bfd.lineTo(pcb_x + pcb_w, pcb_y + pcb_h - 4)
        path_bfd.lineTo(pcb_x + pcb_w - 4, pcb_y + pcb_h)
        path_bfd.lineTo(pcb_x + 4, pcb_y + pcb_h)
        path_bfd.lineTo(pcb_x, pcb_y + pcb_h - 4)
        path_bfd.lineTo(pcb_x, pcb_y + 8)
        path_bfd.closeSubpath()

        # PCB Azul de fibra de vidrio[cite: 2]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0284C7")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0369A1"), 1.4))
        painter.drawPath(path_bfd)

        # Barrenos de fijación mecánica metalizados
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 0.8))
        painter.drawEllipse(QtCore.QPointF(pcb_x + 8, cy), 2.2, 2.2)
        painter.drawEllipse(QtCore.QPointF(pcb_x + pcb_w - 8, cy), 2.2, 2.2)

        # Serigrafía "BFD-1000"[cite: 2]
        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.setFont(QtGui.QFont("Segoe UI", 3, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(pcb_x + 12, pcb_y + 3, 30, 7), QtCore.Qt.AlignLeft, "BFD-1000")

        # Conector Macho de 7 Pines hacia la electrónica[cite: 2]
        conn_w, conn_h = 38.0, 7.0
        conn_x = cx - conn_w / 2.0
        conn_y = pcb_y + pcb_h - 3
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 0.8))
        painter.drawRect(QtCore.QRectF(conn_x, conn_y, conn_w, conn_h))

        colores_cables = ["#1E293B", "#EF4444", "#38BDF8", "#38BDF8", "#38BDF8", "#38BDF8", "#38BDF8"]
        paso_pin = conn_w / 7.0
        for p in range(7):
            px = conn_x + (p * paso_pin) + 2.0
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(px, conn_y + 1, 2.0, 3.5))
            painter.setPen(QtGui.QPen(QtGui.QColor(colores_cables[p]), 1.2))
            painter.drawLine(int(px + 1), int(conn_y + conn_h), int(px + 1), int(conn_y + conn_h + 8))

        # Posicionamiento calibrado de los 5 canales TCRT5000[cite: 2]
        offset_sensores = [-60, -30, 0, 30, 60]
        for idx, offset_x in enumerate(offset_sensores):
            sx = cx + offset_x
            sy = pcb_y + 3.0
            activo = self.sensores_linea[idx]

            # Encapsulado negro del sensor IR[cite: 2]
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
            borde_sensor = QtGui.QColor("#38BDF8") if activo else QtGui.QColor("#334155")
            painter.setPen(QtGui.QPen(borde_sensor, 1))
            painter.drawRoundedRect(QtCore.QRectF(sx - 7, sy, 14, 15), 1.5, 1.5)

            # Emisor Infrarrojo (Cian brillante si activo)[cite: 2]
            color_emisor = QtGui.QColor("#38BDF8") if activo else QtGui.QColor(14, 116, 144, 180)
            painter.setBrush(QtGui.QBrush(color_emisor))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(QtCore.QPointF(sx - 3.0, sy + 4.5), 2.5, 2.5)

            # Fototransistor Receptor (Negro)[cite: 2]
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#18181B")))
            painter.drawEllipse(QtCore.QPointF(sx + 3.0, sy + 4.5), 2.5, 2.5)

            # Proyección del haz infrarrojo activo sobre la pista
            if activo:
                painter.setPen(QtGui.QPen(QtGui.QColor(56, 189, 248, 140), 1.2))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawEllipse(QtCore.QPointF(sx, sy + 7.0), 5.5, 5.5)

            # LED Testigo SMD de la placa (Rojo/Verde según estado de detección)[cite: 2]
            led_color = QtGui.QColor("#EF4444") if activo else QtGui.QColor("#1E3A5F")
            painter.setBrush(QtGui.QBrush(led_color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(sx - 2, sy + 11.5, 4, 2.5))

            # Serigrafía S1 a S5
            painter.setPen(QtGui.QColor("#FFFFFF") if activo else QtGui.QColor("#CBD5E1"))
            painter.setFont(QtGui.QFont("Segoe UI", 3, QtGui.QFont.Bold))
            painter.drawText(QtCore.QRectF(sx - 8, sy + 15, 16, 7), QtCore.Qt.AlignCenter, f"S{idx+1}")

        painter.restore()

    # =========================================================================
    # CONVERTIDOR STEP-DOWN LM2596 HD (LADO IZQUIERDO)[cite: 1, 4]
    # =========================================================================
    def _dibujar_lm2596_hd(self, painter, x, y, w, h):
        painter.save()

        # PCB Azul Royal[cite: 1]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#00508F")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#002848"), 1.2))
        painter.drawRoundedRect(QtCore.QRectF(x, y, w, h), 2.5, 2.5)

        # Barrenos
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(QtCore.QPointF(x + 3, y + 3), 1.3, 1.3)
        painter.drawEllipse(QtCore.QPointF(x + w - 3, y + h - 3), 1.3, 1.3)

        # Capacitores electrolíticos cilíndricos (Entrada y Salida)[cite: 1]
        for cy_cap in [y + 7, y + h - 7]:
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#94A3B8")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 0.8))
            painter.drawEllipse(QtCore.QPointF(x + w / 2.0, cy_cap), 4.2, 4.2)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
            painter.drawPie(QtCore.QRectF(x + w / 2.0 - 4.2, cy_cap - 4.2, 8.4, 8.4), 90 * 16, 180 * 16)

        # Trimmer azul multivuelta con tornillo de latón[cite: 1]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0284C7")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0369A1"), 0.7))
        painter.drawRect(QtCore.QRectF(x + 2.5, y + 14, 6.5, 10))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
        painter.drawEllipse(QtCore.QPointF(x + 5.7, y + 16.5), 1.3, 1.3)
        painter.setPen(QtGui.QPen(QtGui.QColor("#78350F"), 0.6))
        painter.drawLine(int(x + 4.7), int(y + 16.5), int(x + 6.7), int(y + 16.5))

        # Chip Regulador LM2596S-ADJ en TO-263[cite: 1]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 0.7))
        painter.drawRect(QtCore.QRectF(x + 11, y + 13, 13, 11))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.drawRect(QtCore.QRectF(x + 11, y + 13, 13, 2.5))
        painter.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 0.8))
        for px_pin in range(5):
            x_pin = x + 12 + px_pin * 2.5
            painter.drawLine(int(x_pin), int(y + 24), int(x_pin), int(y + 26))

        # Bobina blindada cuadrada "470"[cite: 1]
        bx = x + (w - 15) / 2.0
        by = y + 29
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#18181B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#27272A"), 0.9))
        painter.drawRoundedRect(QtCore.QRectF(bx, by, 15, 13), 2, 2)
        painter.setPen(QtGui.QColor("#D4D4D8"))
        painter.setFont(QtGui.QFont("Segoe UI", 3, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(bx, by, 15, 13), QtCore.Qt.AlignCenter, "470")

        # Diodo Schottky SS34[cite: 1]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(x + 3, y + 27, 4, 7))
        painter.setPen(QtGui.QPen(QtGui.QColor("#CBD5E1"), 0.8))
        painter.drawLine(int(x + 3), int(y + 28), int(x + 7), int(y + 28))

        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.setFont(QtGui.QFont("Segoe UI", 3, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(x, y + h - 6, w, 5), QtCore.Qt.AlignCenter, "LM2596")

        painter.restore()

    # =========================================================================
    # CONVERTIDOR STEP-DOWN XL4015 HD (LADO DERECHO)[cite: 2, 4]
    # =========================================================================
    def _dibujar_xl4015_hd(self, painter, x, y, w, h):
        painter.save()

        # PCB Azul Marino[cite: 2]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#004075")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#00203D"), 1.2))
        painter.drawRoundedRect(QtCore.QRectF(x, y, w, h), 2.5, 2.5)

        # Barrenos
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(QtCore.QPointF(x + 3, y + 3), 1.3, 1.3)
        painter.drawEllipse(QtCore.QPointF(x + w - 3, y + h - 3), 1.3, 1.3)

        # Capacitores electrolíticos de 220uF[cite: 2]
        for cy_cap in [y + 7, y + h - 7]:
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#94A3B8")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 0.8))
            painter.drawEllipse(QtCore.QPointF(x + w / 2.0, cy_cap), 4.4, 4.4)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
            painter.drawPie(QtCore.QRectF(x + w / 2.0 - 4.4, cy_cap - 4.4, 8.8, 8.8), 90 * 16, 180 * 16)

        # Trimmer azul horizontal[cite: 2]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0284C7")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0369A1"), 0.7))
        painter.drawRect(QtCore.QRectF(x + 2.5, y + 14, 6.5, 10))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
        painter.drawEllipse(QtCore.QPointF(x + 5.7, y + 16.5), 1.3, 1.3)

        # Disipador de Aluminio Acanalado[cite: 2]
        grad_heatsink = QtGui.QLinearGradient(x + 11, y + 13, x + 25, y + 13)
        grad_heatsink.setColorAt(0.0, QtGui.QColor("#E2E8F0"))
        grad_heatsink.setColorAt(0.5, QtGui.QColor("#94A3B8"))
        grad_heatsink.setColorAt(1.0, QtGui.QColor("#CBD5E1"))
        painter.setBrush(QtGui.QBrush(grad_heatsink))
        painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 0.8))
        painter.drawRoundedRect(QtCore.QRectF(x + 11, y + 13, 14, 11), 1.5, 1.5)
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 0.8))
        for fy in range(int(y + 15), int(y + 23), 2):
            painter.drawLine(int(x + 12), fy, int(x + 24), fy)

        # Bobina Toroidal de Ferrita con Espiras de Cobre Expuestas[cite: 2]
        cx_tor = x + w / 2.0
        cy_tor = y + 35
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#B45309")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(QtCore.QPointF(cx_tor, cy_tor), 6.0, 6.0)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#004075")))
        painter.drawEllipse(QtCore.QPointF(cx_tor, cy_tor), 2.2, 2.2)

        for a in range(0, 360, 36):
            rad = math.radians(a)
            x1 = cx_tor + 2.2 * math.cos(rad)
            y1 = cy_tor + 2.2 * math.sin(rad)
            x2 = cx_tor + 6.2 * math.cos(rad)
            y2 = cy_tor + 6.2 * math.sin(rad)
            painter.setPen(QtGui.QPen(QtGui.QColor("#F59E0B"), 1.3))
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Diodo auxiliar SMD[cite: 2]
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(QtCore.QRectF(x + 3, y + 27, 4, 6))

        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.setFont(QtGui.QFont("Segoe UI", 3, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(x, y + h - 6, w, 5), QtCore.Qt.AlignCenter, "XL4015")

        painter.restore()

    # =========================================================================
    # MECANISMO DE DIRECCIÓN ACKERMAN RC
    # =========================================================================
    def _dibujar_direccion_delantera(self, painter, cx, cy):
        painter.save()

        # Soporte central mecanizado
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(cx - 30, cy - 24, 60, 48), 3, 3)

        # Servomotor central MG995 / MG996R
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#000000"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(cx - 24, cy - 16, 48, 32), 2, 2)

        # Tornillería
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtCore.Qt.NoPen)
        for sx, sy in [(cx - 20, cy - 12), (cx + 20, cy - 12), (cx - 20, cy + 12), (cx + 20, cy + 12)]:
            painter.drawEllipse(QtCore.QPointF(sx, sy), 1.8, 1.8)

        # Horn circular y perno central
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 1))
        painter.drawEllipse(QtCore.QPointF(cx, cy), 6, 6)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
        painter.drawEllipse(QtCore.QPointF(cx, cy), 2.5, 2.5)

        # Trapecios en A con nervios de refuerzo
        for signo in [-1, 1]:
            path_arm = QtGui.QPainterPath()
            path_arm.moveTo(cx + signo * 26, cy - 18)
            path_arm.lineTo(cx + signo * 105, cy - 6)
            path_arm.lineTo(cx + signo * 105, cy + 6)
            path_arm.lineTo(cx + signo * 26, cy + 18)
            path_arm.closeSubpath()
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 1.5))
            painter.drawPath(path_arm)

            path_hole = QtGui.QPainterPath()
            path_hole.moveTo(cx + signo * 34, cy - 10)
            path_hole.lineTo(cx + signo * 95, cy)
            path_hole.lineTo(cx + signo * 34, cy + 10)
            path_hole.closeSubpath()
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#080D1A")))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawPath(path_hole)

        # Rótulas uniball de latón dorado
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#EAB308")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#713F12"), 1))
        for px, py in [(cx - 26, cy - 14), (cx - 26, cy + 14), (cx + 26, cy - 14), (cx + 26, cy + 14), (cx - 105, cy), (cx + 105, cy)]:
            painter.drawEllipse(QtCore.QPointF(px, py), 2.5, 2.5)

        # Tirantes de dirección
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 2.5))
        painter.drawLine(int(cx), int(cy - 6), int(cx - 100), int(cy - 12))
        painter.drawLine(int(cx), int(cy - 6), int(cx + 100), int(cy - 12))

        # Ruedas delanteras posicionadas en las manguetas exteriores
        color_llanta = QtGui.QColor("#1E293B")
        self._dibujar_mangueta_y_rueda(painter, cx - 114, cy, self.angulo_direccion, self.angulo_rodadura, color_llanta, True)
        self._dibujar_mangueta_y_rueda(painter, cx + 114, cy, self.angulo_direccion, self.angulo_rodadura, color_llanta, False)

        painter.restore()

    def _dibujar_mangueta_y_rueda(self, painter, kx, ky, angulo_giro, angulo_rodadura, color, es_izquierda):
        painter.save()
        painter.translate(kx, ky)
        painter.rotate(angulo_giro)

        # Portamangueta C-Hub mecanizado
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(-8, -12, 16, 24), 2, 2)

        # Hexágono de latón para acople de rin
        offset_hex = -16 if es_izquierda else 8
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#78350F"), 1))
        painter.drawRoundedRect(QtCore.QRectF(offset_hex, -5, 8, 10), 1, 1)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.drawEllipse(QtCore.QPointF(offset_hex + 4, 0), 1.5, 1.5)

        offset_rueda = -42 if es_izquierda else 0
        self._dibujar_rueda(painter, offset_rueda, -44, 42, 88, 0.0, angulo_rodadura, color)

        painter.restore()

    # =========================================================================
    # RASPBERRY PI 3 B+ DETALLADA
    # =========================================================================
    def _dibujar_raspberry_pi(self, painter, x, y, w, h):
        painter.save()

        # PCB FR-4 Verde Soldermask
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#007A3D")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#004D25"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(x, y, w, h), 4, 4)

        # 4 Barrenos plateados de montaje
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#080D1A"), 1))
        for px, py in [(x + 4, y + 4), (x + w - 4, y + 4), (x + 4, y + h - 4), (x + w - 4, y + h - 4)]:
            painter.drawEllipse(QtCore.QPointF(px, py), 2.5, 2.5)

        # Puertos USB dobles metálicos
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 1))
        painter.drawRoundedRect(QtCore.QRectF(x + 5, y + h - 12, 16, 16), 1, 1)
        painter.drawRoundedRect(QtCore.QRectF(x + 24, y + h - 12, 16, 16), 1, 1)

        # Puerto Ethernet RJ45 metálico
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#94A3B8")))
        painter.drawRoundedRect(QtCore.QRectF(x + 44, y + h - 14, 18, 18), 1, 1)

        # MicroUSB y salida HDMI
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#E2E8F0")))
        painter.drawRoundedRect(QtCore.QRectF(x - 3, y + 14, 5, 12), 1, 1)
        painter.drawRoundedRect(QtCore.QRectF(x - 4, y + 36, 6, 18), 1, 1)

        # Conectores FPC (Cámara CSI y Pantalla DSI)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#78350F"), 1))
        painter.drawRect(QtCore.QRectF(x + 26, y + 6, 16, 4))
        painter.drawRect(QtCore.QRectF(x + 4, y + 38, 4, 16))

        # SoC Broadcom BCM2837B0 con tapa metálica disipadora
        soc_x, soc_y = x + 16, y + 26
        grad_soc = QtGui.QLinearGradient(soc_x, soc_y, soc_x + 22, soc_y + 22)
        grad_soc.setColorAt(0.0, QtGui.QColor("#F8FAFC"))
        grad_soc.setColorAt(0.5, QtGui.QColor("#94A3B8"))
        grad_soc.setColorAt(1.0, QtGui.QColor("#CBD5E1"))
        painter.setBrush(QtGui.QBrush(grad_soc))
        painter.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 1))
        painter.drawRoundedRect(QtCore.QRectF(soc_x, soc_y, 22, 22), 2, 2)
        painter.setPen(QtGui.QColor("#334155"))
        painter.setFont(QtGui.QFont("Segoe UI", 3, QtGui.QFont.Bold))
        painter.drawText(QtCore.QRectF(soc_x, soc_y + 4, 22, 14), QtCore.Qt.AlignCenter, "BROADCOM")

        # Chip LAN7515
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))
        painter.drawRect(QtCore.QRectF(x + 24, y + 54, 14, 14))

        # Blindaje WiFi / Bluetooth plateado
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#E2E8F0")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1))
        painter.drawRoundedRect(QtCore.QRectF(x + 6, y + 8, 14, 14), 1, 1)

        # LEDs indicadores PWR y ACT
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#EF4444")))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(QtCore.QPointF(x + 6, y + h - 6), 1.5, 1.5)
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#10B981")))
        painter.drawEllipse(QtCore.QPointF(x + 10, y + h - 6), 1.5, 1.5)

        # Cabezal GPIO de 40 pines
        gpio_x = x + w - 9
        gpio_y = y + 10
        gpio_w = 7
        gpio_h = 60
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))
        painter.drawRect(QtCore.QRectF(gpio_x, gpio_y, gpio_w, gpio_h))

        paso_pin = gpio_h / 20.0
        for fila in range(20):
            pin_impar = (fila * 2) + 1
            pin_par = (fila * 2) + 2
            py = gpio_y + (fila * paso_pin) + 1.2
            
            painter.setBrush(QtGui.QBrush(self._obtener_color_pin(pin_impar)))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(gpio_x + 1.2, py, 1.8, 1.8))

            painter.setBrush(QtGui.QBrush(self._obtener_color_pin(pin_par)))
            painter.drawRect(QtCore.QRectF(gpio_x + 4.0, py, 1.8, 1.8))

        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.setFont(QtGui.QFont("Segoe UI", 4, QtGui.QFont.Bold))
        painter.drawText(int(x + 6), int(y + h - 18), "Raspberry Pi 3B+")

        painter.restore()

    def _obtener_color_pin(self, num_pin: int) -> QtGui.QColor:
        # VCC 5V / 3.3V
        if num_pin in [1, 2, 4, 17]:
            return QtGui.QColor("#EF4444")
        # GND
        if num_pin in [6, 9, 14, 20, 25, 30, 34, 39]:
            return QtGui.QColor("#1E293B")

        # Sensores BFD-1000 asignados a Pines Físicos:
        if num_pin == 29: # GPIO 5  (S1 - Extremo Izquierdo)
            return QtGui.QColor("#38BDF8") if self.sensores_linea[0] else QtGui.QColor("#0284C7")
        if num_pin == 31: # GPIO 6  (S2 - Medio Izquierdo)
            return QtGui.QColor("#38BDF8") if self.sensores_linea[1] else QtGui.QColor("#0284C7")
        if num_pin == 35: # GPIO 19 (S3 - CENTRO GUÍA)
            return QtGui.QColor("#38BDF8") if self.sensores_linea[2] else QtGui.QColor("#0284C7")
        if num_pin == 38: # GPIO 20 (S4 - Medio Derecho)
            return QtGui.QColor("#38BDF8") if self.sensores_linea[3] else QtGui.QColor("#0284C7")
        if num_pin == 37: # GPIO 26 (S5 - Extremo Derecho)
            return QtGui.QColor("#38BDF8") if self.sensores_linea[4] else QtGui.QColor("#0284C7")

        # Tracción BTS7960
        if num_pin == 12: # GPIO 18 (RPWM FWD)
            return QtGui.QColor("#38BDF8") if (self.velocidad_pwm > 0 and ("F" in self.direccion or self.direccion in ["L", "R"])) else QtGui.QColor("#F59E0B")
        if num_pin == 33: # GPIO 13 (LPWM REV)
            return QtGui.QColor("#38BDF8") if (self.velocidad_pwm > 0 and "B" in self.direccion) else QtGui.QColor("#F59E0B")

        # Dirección MG995 (Pin Físico 40 / GPIO 21)
        if num_pin == 40:
            return QtGui.QColor("#10B981") if self.direccion in ["L", "R", "FL", "FR", "BL", "BR"] else QtGui.QColor("#F59E0B")

        return QtGui.QColor("#F59E0B")

    # =========================================================================
    # TREN DE POTENCIA Y TRANSMISIÓN TRASERA (RS-550)
    # =========================================================================
    def _dibujar_tren_potencia(self, painter, cx, y_eje):
        painter.save()
        y_motor = y_eje - 40

        # Eje pasante rectificado
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F8FAFC")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1))
        painter.drawRect(QtCore.QRectF(cx - 130, y_eje - 4, 260, 8))

        # Coples hexagonales
        for sx in [cx - 128, cx + 104]:
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 1.5))
            painter.drawRoundedRect(QtCore.QRectF(sx, y_eje - 8.5, 24, 17), 3, 3)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#94A3B8")))
            painter.drawEllipse(QtCore.QPointF(sx + 12, y_eje), 2.5, 2.5)

        # Soporte de fijación 3D
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(cx - 48, y_motor - 4, 86, 48), 4, 4)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F1F5F9")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1))
        painter.drawRect(QtCore.QRectF(cx - 48, y_motor + 8, 10, 32))
        painter.drawRect(QtCore.QRectF(cx + 22, y_motor - 2, 16, 42))

        # Motor RS-550 metálico
        grad_motor = QtGui.QLinearGradient(cx - 38, y_motor, cx - 38, y_motor + 26)
        grad_motor.setColorAt(0.0, QtGui.QColor("#FFFFFF"))
        grad_motor.setColorAt(0.5, QtGui.QColor("#94A3B8"))
        grad_motor.setColorAt(1.0, QtGui.QColor("#475569"))
        painter.setBrush(QtGui.QBrush(grad_motor))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(cx - 38, y_motor, 58, 26), 4, 4)

        # Ventilación interna con cobre visible
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#B45309")))
        painter.setPen(QtCore.Qt.NoPen)
        for vx in [-30, -22, -14]:
            painter.drawRoundedRect(QtCore.QRectF(cx + vx, y_motor + 4, 4, 18), 1, 1)

        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.drawRoundedRect(QtCore.QRectF(cx - 42, y_motor + 3, 5, 20), 1, 1)

        # Cables siliconados Rojo y Negro
        painter.setPen(QtGui.QPen(QtGui.QColor("#EF4444"), 2.2))
        painter.drawLine(int(cx - 40), int(y_motor + 6), int(cx - 14), int(y_eje + 28))
        painter.setPen(QtGui.QPen(QtGui.QColor("#1E293B"), 2.2))
        painter.drawLine(int(cx - 40), int(y_motor + 16), int(cx - 4), int(y_eje + 28))

        # Piñón helicoidal del motor
        pinon_x, pinon_y = cx + 36, y_motor + 3
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#FFFFFF")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#94A3B8"), 1))
        painter.drawRoundedRect(QtCore.QRectF(pinon_x, pinon_y, 14, 18), 2, 2)

        # Corona dentada principal de la transmisión
        corona_x, corona_y = cx + 34, y_eje - 13
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(corona_x, corona_y, 18, 26), 3, 3)

        painter.setPen(QtGui.QPen(QtGui.QColor("#64748B"), 1.5))
        desfase_corona = (self.angulo_engrane % 6) - 3
        for cd in range(int(corona_y + 3 + desfase_corona), int(corona_y + 23), 4):
            if corona_y < cd < corona_y + 26:
                painter.drawLine(int(corona_x), cd, int(corona_x + 18), cd + 3)

        painter.restore()

    # =========================================================================
    # CONTROLADOR PUENTE H BTS7960 (IBT-2)
    # =========================================================================
    def _dibujar_bts7960(self, painter, x, y, w, h):
        painter.save()

        # PCB Azul IBT-2
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#004B87")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#002B54"), 1.5))
        painter.drawRoundedRect(QtCore.QRectF(x, y, w, h), 4, 4)

        # Barrenos de fijación
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#CBD5E1")))
        painter.setPen(QtCore.Qt.NoPen)
        for px, py in [(x + 4, y + 4), (x + w - 4, y + 4), (x + 4, y + h - 4), (x + w - 4, y + h - 4)]:
            painter.drawEllipse(QtCore.QPointF(px, py), 2.5, 2.5)

        # Bornera de tornillos de alta potencia verde
        b_w, b_h = w - 22, 13
        bx, by = x + 4, y + 4
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#15803D")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#166534"), 1))
        painter.drawRoundedRect(QtCore.QRectF(bx, by, b_w, b_h), 2, 2)

        paso_borne = b_w / 4
        for i in range(4):
            tx = bx + (i * paso_borne) + (paso_borne / 2)
            ty = by + (b_h / 2)
            if i == 0:
                color_borne = QtGui.QColor("#2563EB")
            elif i == 1:
                color_borne = QtGui.QColor("#EF4444")
            else:
                color_borne = QtGui.QColor("#38BDF8") if self.velocidad_pwm > 0 else QtGui.QColor("#94A3B8")
            painter.setBrush(QtGui.QBrush(color_borne))
            painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 1))
            painter.drawEllipse(QtCore.QPointF(tx, ty), 2.2, 2.2)

        # Capacitor masivo de filtrado
        cap_x, cap_y = x + w - 9, y + 10
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E293B")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#475569"), 1))
        painter.drawEllipse(QtCore.QPointF(cap_x, cap_y), 4.5, 4.5)

        # Chips duales BTN7960
        chip_w = (w - 22) / 2
        chip_h = 16
        cy_pos = y + 21
        for idx, cx_pos in enumerate([x + 7, x + 7 + chip_w + 3]):
            activo = (self.velocidad_pwm > 0)
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#1E3A8A") if activo else QtGui.QColor("#1E293B")))
            painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8") if activo else QtGui.QColor("#0F172A"), 1))
            painter.drawRoundedRect(QtCore.QRectF(cx_pos, cy_pos + 2.5, chip_w, chip_h - 2.5), 1, 1)

        # Buffer lógico 74HC244
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.setPen(QtGui.QPen(QtGui.QColor("#334155"), 1))
        painter.drawRect(QtCore.QRectF(x + w - 20, y + 41, 14, 7.5))

        # Pines lógicos de control
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#0F172A")))
        painter.drawRect(QtCore.QRectF(x + 9, y + h - 13, 30, 8))
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#F59E0B")))
        painter.setPen(QtCore.Qt.NoPen)
        for col in range(4):
            for row in range(2):
                painter.drawRect(QtCore.QRectF(x + 12 + col * 7, y + h - 11.5 + row * 3.5, 1.8, 1.8))

        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.setFont(QtGui.QFont("Segoe UI", 5, QtGui.QFont.Bold))
        painter.drawText(int(x + w - 22), int(y + h - 5), "IBT_2")

        painter.restore()

    # =========================================================================
    # RUEDAS OFF-ROAD INDUSTRIALES
    # =========================================================================
    def _dibujar_rueda(self, painter, x, y, w, h, angulo_giro, angulo_rodadura, color):
        painter.save()
        rcx, rcy = x + w / 2, y + h / 2
        painter.translate(rcx, rcy)
        painter.rotate(angulo_giro)
        painter.translate(-rcx, -rcy)

        # Neumático de caucho
        painter.setBrush(QtGui.QBrush(color))
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 2))
        painter.drawRoundedRect(QtCore.QRectF(x, y, w, h), 7, 7)

        # Rin blanco
        painter.setBrush(QtGui.QBrush(QtGui.QColor("#FFFFFF")))
        painter.drawRoundedRect(QtCore.QRectF(x + 6, y + 15, w - 12, h - 30), 3, 3)

        # Tacos y huella animada en V
        painter.setPen(QtGui.QPen(QtGui.QColor("#0F172A"), 2))
        desfase = (angulo_rodadura % 18) - 9
        for dy in range(int(y + 10 + desfase), int(y + h - 10), 14):
            if y + 6 < dy < y + h - 6:
                painter.drawLine(int(x + 2), int(dy), int(x + w / 2), int(dy + 4))
                painter.drawLine(int(x + w / 2), int(dy + 4), int(x + w - 2), int(dy))

        painter.restore()