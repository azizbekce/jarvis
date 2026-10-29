from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from audio_visualizer import AUDIO_BAND_COUNT


class ArcCore(QWidget):
    COLORS = {
        "LISTENING": "#55f5e9",
        "THINKING": "#7ce2ff",
        "PROCESSING": "#7ce2ff",
        "SPEAKING": "#aefcff",
        "MUTED": "#6097a4",
        "IDLE": "#64e8f0",
        "CONNECTING": "#9aefff",
        "ERROR": "#ff697a",
    }

    def __init__(self, accent: str, reduced_motion: bool = False, parent=None):
        super().__init__(parent)
        self.setMinimumSize(270, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.state = "IDLE"
        self.accent = accent
        self.current_color = QColor(self.COLORS["IDLE"])
        self.reduced_motion = reduced_motion
        self.phase = 0.0
        self.boot_ticks = 90 if reduced_motion else 0
        self.mouse_offset = QPointF()
        self.last_pointer = QPointF(-9999.0, -9999.0)
        self.mouse_gaze = QPointF(0.0, 0.0)
        self.mouse_weight = 0.0
        self.last_mouse_move = 0.0
        self.pupil_pos = QPointF(0.32, -0.18)
        self.pupil_target = QPointF(0.45, -0.25)
        self.pupil_ticks = 20
        self.audio_levels = [0.0] * AUDIO_BAND_COUNT
        self.target_levels = [0.0] * AUDIO_BAND_COUNT
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.timer.start(16)

    def set_state(self, state: str):
        self.state = state.upper()
        self.update()

    def set_appearance(self, accent: str, reduced_motion: bool):
        self.accent = accent
        self.reduced_motion = reduced_motion
        if reduced_motion:
            self.boot_ticks = 90
        self.update()

    def set_audio_levels(self, levels):
        if len(levels) == len(self.target_levels):
            self.target_levels = [max(0.0, min(1.0, float(value))) for value in levels]

    def set_pointer_pos(self, position: QPointF):
        if math.hypot(position.x() - self.last_pointer.x(), position.y() - self.last_pointer.y()) < 1.0:
            return
        self.last_pointer = QPointF(position)
        dx = (position.x() - self.width() / 2.0) / max(1.0, float(self.width()))
        dy = (position.y() - self.height() / 2.0) / max(1.0, float(self.height()))
        self.mouse_offset = QPointF(
            max(-1.0, min(1.0, dx)) * 7.0,
            max(-1.0, min(1.0, dy)) * 7.0,
        )
        self.mouse_gaze = QPointF(
            max(-0.95, min(0.95, dx * 2.2)),
            max(-0.95, min(0.95, dy * 2.2)),
        )
        self.last_mouse_move = time.monotonic()
        self.update()

    def _advance(self):
        app = QApplication.instance()
        if not self.isVisible() or self.window().isMinimized() or (
            app is not None
            and app.applicationState() != Qt.ApplicationState.ApplicationActive
        ):
            if self.timer.interval() != 350:
                self.timer.setInterval(350)
        else:
            target_interval = 100 if self.reduced_motion else 16
            if self.timer.interval() != target_interval:
                self.timer.setInterval(target_interval)

        if not self.reduced_motion:
            speed = (
                0.056 if self.state in ("THINKING", "PROCESSING")
                else 0.042 if self.state == "SPEAKING"
                else 0.025
            )
            self.phase += speed
            idle_sec = time.monotonic() - self.last_mouse_move
            if idle_sec < 0.70:
                self.mouse_weight = min(1.0, self.mouse_weight + 0.26)
            else:
                self.mouse_weight *= 0.86
                if self.mouse_weight < 0.01:
                    self.mouse_weight = 0.0
                self.mouse_offset = QPointF(
                    self.mouse_offset.x() * 0.92,
                    self.mouse_offset.y() * 0.92,
                )

            self.pupil_ticks -= 1
            if self.pupil_ticks <= 0:
                # Choose a new human-like eye gaze direction (left, right, up, down, diagonal, or center)
                directions = (
                    (-0.85, 0.0),    # Left
                    (0.85, 0.0),     # Right
                    (0.0, -0.82),    # Up
                    (0.0, 0.82),     # Down
                    (-0.66, -0.58),  # Top-left
                    (0.66, -0.58),   # Top-right
                    (-0.66, 0.58),   # Bottom-left
                    (0.66, 0.58),   # Bottom-right
                    (0.0, 0.0),      # Center
                )
                gx, gy = random.choice(directions)
                self.pupil_target = QPointF(
                    gx + random.uniform(-0.14, 0.14),
                    gy + random.uniform(-0.14, 0.14),
                )
                self.pupil_ticks = random.randint(20, 48)
            # Combine autonomous saccade target + subtle micro-orbit when mouse is idle, or mouse gaze when moving
            orbit_x = math.cos(self.phase * 1.45) * 0.18
            orbit_y = math.sin(self.phase * 1.10) * 0.18
            auto_x = max(-0.92, min(0.92, self.pupil_target.x() + orbit_x))
            auto_y = max(-0.92, min(0.92, self.pupil_target.y() + orbit_y))
            tx = auto_x * (1.0 - self.mouse_weight) + self.mouse_gaze.x() * self.mouse_weight
            ty = auto_y * (1.0 - self.mouse_weight) + self.mouse_gaze.y() * self.mouse_weight
            lerp = 0.24 if self.mouse_weight > 0.3 else 0.15
            self.pupil_pos = QPointF(
                self.pupil_pos.x() + (tx - self.pupil_pos.x()) * lerp,
                self.pupil_pos.y() + (ty - self.pupil_pos.y()) * lerp,
            )
        self.boot_ticks = min(90, self.boot_ticks + 1)
        target_color = QColor(self.COLORS.get(self.state, self.accent))
        self.current_color.setRed(round(self.current_color.red()
                                        + (target_color.red() - self.current_color.red()) * 0.12))
        self.current_color.setGreen(round(self.current_color.green()
                                          + (target_color.green() - self.current_color.green()) * 0.12))
        self.current_color.setBlue(round(self.current_color.blue()
                                         + (target_color.blue() - self.current_color.blue()) * 0.12))
        easing = 0.25 if self.state == "SPEAKING" else 0.14
        for index, target in enumerate(self.target_levels):
            self.audio_levels[index] += (target - self.audio_levels[index]) * easing
            self.target_levels[index] *= 0.86
        self.update()

    def mouseMoveEvent(self, event):
        self.set_pointer_pos(event.position())

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        scale = side / 520.0
        base_center = QPointF(self.width() / 2.0, self.height() / 2.0)
        outer_center = QPointF(
            base_center.x() + self.mouse_offset.x() * 0.55,
            base_center.y() + self.mouse_offset.y() * 0.55,
        )
        inner_center = QPointF(
            base_center.x() + self.mouse_offset.x() * 1.15,
            base_center.y() + self.mouse_offset.y() * 1.15,
        )

        color = QColor(self.current_color)
        pulse = 1.0 if self.reduced_motion else 1.0 + 0.026 * math.sin(self.phase * 2.1)
        boost = sum(self.audio_levels) / max(1, len(self.audio_levels))
        peak = max(self.audio_levels, default=0.0)
        boot = self.boot_ticks / 90.0

        is_error = self.state == "ERROR"
        is_thinking = self.state in ("THINKING", "PROCESSING", "CONNECTING")
        is_speaking = self.state == "SPEAKING"

        primary_rgb = (255, 105, 122) if is_error else (color.red(), color.green(), color.blue())
        amber_rgb = (255, 110, 125) if is_error else (255, 184, 74)

        # 1. Deep multi-layered holographic atmosphere glow
        glow_radius = 248.0 * scale
        glow = QRadialGradient(inner_center, glow_radius)
        glow.setColorAt(0.0, QColor(200, 255, 255, int((95 + boost * 85) * boot)))
        glow.setColorAt(0.28, QColor(primary_rgb[0], primary_rgb[1], primary_rgb[2], int((64 + boost * 50) * boot)))
        glow.setColorAt(0.62, QColor(16, 118, 178, int(26 * boot)))
        glow.setColorAt(1.0, QColor(primary_rgb[0], primary_rgb[1], primary_rgb[2], 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(
            inner_center.x() - glow_radius,
            inner_center.y() - glow_radius,
            glow_radius * 2.0,
            glow_radius * 2.0,
        ))

        core_radius = 158.0 * scale * pulse * (1.0 + boost * 0.18) * min(1.0, boot * 1.8)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # 2. Concentric structural HUD rings with varied weight hierarchy
        for radius_mult, alpha, width, dashed in (
            (0.36, 95, 0.9, False),
            (0.52, 130, 1.25, False),
            (0.68, 72, 0.85, True),
            (0.84, 88, 1.0, False),
            (1.02, 155, 1.55, False),
            (1.19, 92, 1.0, False),
            (1.34, 70, 0.85, True),
            (1.46, 58, 0.8, False),
        ):
            pen = QPen(
                QColor(primary_rgb[0], primary_rgb[1], primary_rgb[2], int(alpha * boot)),
                max(0.7, width * scale),
            )
            if dashed:
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([4.0, 5.0])
            painter.setPen(pen)
            c = inner_center if radius_mult < 0.9 else outer_center
            diameter = core_radius * radius_mult * 2.0
            painter.drawEllipse(QRectF(
                c.x() - diameter / 2.0,
                c.y() - diameter / 2.0,
                diameter,
                diameter,
            ))

        # 3. Iconic Stark Arc Reactor 10-segment outer coil ring (1.02x radius)
        coil_radius = core_radius * 1.02
        coil_rect = QRectF(
            outer_center.x() - coil_radius,
            outer_center.y() - coil_radius,
            coil_radius * 2.0,
            coil_radius * 2.0,
        )
        coil_rot = self.phase * 4.5
        # Soft outer glow for the 10 reactor coils
        painter.setPen(QPen(
            QColor(primary_rgb[0], primary_rgb[1], primary_rgb[2], int((78 + boost * 70) * boot)),
            max(2.2, 5.2 * scale),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.FlatCap,
        ))
        for seg in range(10):
            start_deg = coil_rot + seg * 36.0
            painter.drawArc(coil_rect, round(start_deg * 16), round(22.0 * 16))
        # Crisp bright core inside each of the 10 reactor coils
        painter.setPen(QPen(
            QColor(225, 253, 255, int((185 + boost * 55) * boot)),
            max(1.0, 2.0 * scale),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.FlatCap,
        ))
        for seg in range(10):
            start_deg = coil_rot + seg * 36.0 + 2.0
            painter.drawArc(coil_rect, round(start_deg * 16), round(18.0 * 16))

        # 4. Counter-rotating technical telemetry arcs (cyan & ice-white)
        for ring_radius, segments, rotation, sweep, thickness, alpha in (
            (0.58, 4, -self.phase * 18.0, 32, 2.1, 165),
            (0.92, 3, self.phase * 14.0, 44, 1.6, 140),
            (1.14, 4, -self.phase * 11.0, 34, 2.0, 150),
            (1.28, 3, self.phase * 8.5, 52, 1.5, 130),
            (1.46, 6, -self.phase * 5.0, 16, 1.8, 120),
        ):
            c = inner_center if ring_radius < 0.9 else outer_center
            diameter = core_radius * ring_radius * 2.0
            rect = QRectF(c.x() - diameter / 2.0, c.y() - diameter / 2.0, diameter, diameter)
            painter.setPen(QPen(
                QColor(178, 248, 255, int(alpha * boot)),
                max(0.9, thickness * scale),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            ))
            for segment in range(segments):
                start = round((rotation + segment * 360.0 / segments) * 16)
                painter.drawArc(rect, start, round(sweep * 16))

        # 5. High-contrast Amber/Gold tactical scanner arcs
        amber_alpha = int((210 if is_thinking or is_speaking else 165) * boot)
        for ring_radius, segments, rotation, sweep, thickness in (
            (0.64, 2, self.phase * 22.0, 26, 2.0),
            (1.19, 3, -self.phase * 13.0, 24, 2.4),
            (1.34, 2, self.phase * 9.5, 34, 1.8),
        ):
            c = inner_center if ring_radius < 0.9 else outer_center
            diameter = core_radius * ring_radius * 2.0
            rect = QRectF(c.x() - diameter / 2.0, c.y() - diameter / 2.0, diameter, diameter)
            painter.setPen(QPen(
                QColor(amber_rgb[0], amber_rgb[1], amber_rgb[2], amber_alpha),
                max(0.9, thickness * scale),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            ))
            for segment in range(segments):
                start = round((rotation + segment * 360.0 / segments) * 16)
                painter.drawArc(rect, start, round(sweep * 16))

        # 6. Outer compass degree ticks + 4 cardinal HUD reticle crosshairs
        for index in range(120):
            angle = index * math.tau / 120.0 + self.phase * 0.04
            cardinal = index % 30 == 0
            major = index % 10 == 0
            inner = core_radius * (1.35 if cardinal else 1.38 if major else 1.40)
            outer = core_radius * (1.46 if cardinal else 1.44 if major else 1.425)
            if major:
                outer += (2.5 + boost * 12.0) * scale
            tick_col = (
                QColor(amber_rgb[0], amber_rgb[1], amber_rgb[2], int(195 * boot))
                if cardinal
                else QColor(156, 240, 255, int((135 if major else 64) * boot))
            )
            painter.setPen(QPen(
                tick_col,
                max(0.65, (1.6 if cardinal else 1.1 if major else 0.7) * scale),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            ))
            painter.drawLine(
                QPointF(outer_center.x() + math.cos(angle) * inner,
                        outer_center.y() + math.sin(angle) * inner),
                QPointF(outer_center.x() + math.cos(angle) * outer,
                        outer_center.y() + math.sin(angle) * outer),
            )

        # 4 fixed cardinal HUD targeting reticles (0°, 90°, 180°, 270°)
        reticle_pen = QPen(
            QColor(185, 250, 255, int(145 * boot)),
            max(0.9, 1.3 * scale),
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(reticle_pen)
        for deg in (0, 90, 180, 270):
            rad = math.radians(deg)
            r_in = core_radius * 0.86
            r_out = core_radius * 0.96
            painter.drawLine(
                QPointF(outer_center.x() + math.cos(rad) * r_in,
                        outer_center.y() + math.sin(rad) * r_in),
                QPointF(outer_center.x() + math.cos(rad) * r_out,
                        outer_center.y() + math.sin(rad) * r_out),
            )

        # 7. Live 96-bar radial audio spectrum ring (0.74x radius)
        bar_count = 96
        base_bar_r = core_radius * 0.72
        for index in range(bar_count):
            angle = -self.phase * 0.18 + index * math.tau / bar_count
            src_idx = (index * 3) % len(self.audio_levels)
            level = self.audio_levels[src_idx]
            idle_wave = 0.08 + 0.05 * math.sin(index * 0.35 + self.phase * 2.6)
            bar_len = (idle_wave * 7.0 + level * 28.0) * scale
            r1 = base_bar_r - bar_len * 0.25
            r2 = base_bar_r + bar_len * 0.75
            is_accent_bar = level > 0.42 and index % 4 == 0
            bar_color = (
                QColor(amber_rgb[0], amber_rgb[1], amber_rgb[2], int((155 + level * 95) * boot))
                if is_accent_bar
                else QColor(195, 252, 255, int((88 + level * 155) * boot))
            )
            painter.setPen(QPen(
                bar_color,
                max(0.75, 1.35 * scale),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            ))
            painter.drawLine(
                QPointF(inner_center.x() + math.cos(angle) * r1,
                        inner_center.y() + math.sin(angle) * r1),
                QPointF(inner_center.x() + math.cos(angle) * r2,
                        inner_center.y() + math.sin(angle) * r2),
            )

        # 8. Continuous organic plasma harmonic wave around inner core (0.48x radius)
        wave_points = 96
        wave_base = core_radius * 0.47
        wave_path = QPainterPath()
        for i in range(wave_points + 1):
            idx = i % wave_points
            angle = idx * math.tau / wave_points
            lvl = self.audio_levels[(idx * 2) % len(self.audio_levels)]
            harmonic = (
                math.sin(angle * 6.0 + self.phase * 3.2) * (1.8 + boost * 11.0)
                + math.cos(angle * 4.0 - self.phase * 2.4) * (1.2 + lvl * 9.0)
            ) * scale
            r = wave_base + harmonic
            pt = QPointF(
                inner_center.x() + math.cos(angle) * r,
                inner_center.y() + math.sin(angle) * r,
            )
            if i == 0:
                wave_path.moveTo(pt)
            else:
                wave_path.lineTo(pt)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(
            QColor(150, 248, 255, int((130 + peak * 95) * boot)),
            max(0.9, 1.45 * scale),
        ))
        painter.drawPath(wave_path)

        # 9. Counter-rotating inner geometric turbine / reactor lattice (0.37x radius)
        lattice_r = core_radius * 0.37
        for direction, rot_offset, alpha in ((1.0, 0.0, 135), (-1.0, math.pi / 6.0, 95)):
            poly_path = QPainterPath()
            vertices = 6
            for i in range(vertices + 1):
                ang = direction * self.phase * 0.55 + rot_offset + (i % vertices) * math.tau / vertices
                pt = QPointF(
                    inner_center.x() + math.cos(ang) * lattice_r,
                    inner_center.y() + math.sin(ang) * lattice_r,
                )
                if i == 0:
                    poly_path.moveTo(pt)
                else:
                    poly_path.lineTo(pt)
            painter.setPen(QPen(
                QColor(195, 250, 255, int(alpha * boot)),
                max(0.7, 1.05 * scale),
            ))
            painter.drawPath(poly_path)

        # 10. Orbiting quantum HUD particles
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(28):
            angle = self.phase * (0.16 if index % 2 == 0 else -0.11) + index * math.tau / 28.0
            radius = core_radius * (1.42 + 0.04 * math.sin(index * 2.3 + self.phase))
            is_gold = index % 5 == 0
            particle = (
                QColor(amber_rgb[0], amber_rgb[1], amber_rgb[2], int(165 * boot))
                if is_gold
                else QColor(145, 240, 255, int(115 * boot))
            )
            painter.setBrush(particle)
            particle_radius = (1.8 if is_gold else 1.1) * scale
            painter.drawEllipse(
                QPointF(outer_center.x() + math.cos(angle) * radius,
                        outer_center.y() + math.sin(angle) * radius),
                particle_radius,
                particle_radius,
            )

        # 11. Bionic Eye-Pupil Plasma Core (O'rtadagi yumaloq oq ko'z qorachig'idek harakatlanadi)
        sun_radius = core_radius * (0.25 + boost * 0.04)
        sun_glow = QRadialGradient(inner_center, sun_radius * 2.8)
        sun_glow.setColorAt(0.0, QColor(225, 254, 255, int(210 * boot)))
        sun_glow.setColorAt(0.35, QColor(145, 245, 255, int(135 * boot)))
        sun_glow.setColorAt(0.70, QColor(primary_rgb[0], primary_rgb[1], primary_rgb[2], int(52 * boot)))
        sun_glow.setColorAt(1.0, QColor(primary_rgb[0], primary_rgb[1], primary_rgb[2], 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(sun_glow)
        painter.drawEllipse(QRectF(
            inner_center.x() - sun_radius * 2.8,
            inner_center.y() - sun_radius * 2.8,
            sun_radius * 5.6,
            sun_radius * 5.6,
        ))

        # Calculate live eye-pupil position (follows mouse when moving, looks around freely when mouse is idle)
        max_shift = sun_radius * 0.36
        px = self.pupil_pos.x() * max_shift
        py = self.pupil_pos.y() * max_shift
        shift_len = math.hypot(px, py)
        if shift_len > max_shift:
            px = px / shift_len * max_shift
            py = py / shift_len * max_shift
        pupil_center = QPointF(inner_center.x() + px, inner_center.y() + py)

        # Outer 3D Eyeball / Plasma Chamber (deep cyan-blue interior so the white pupil stands out clearly)
        swirl_angle = self.phase * 1.85
        socket_focal = QPointF(
            inner_center.x() - math.cos(swirl_angle) * sun_radius * 0.30,
            inner_center.y() - math.sin(swirl_angle) * sun_radius * 0.30,
        )
        socket_grad = QRadialGradient(inner_center, sun_radius * 1.04, socket_focal)
        socket_grad.setColorAt(0.0, QColor(10, 68, 104, int(245 * boot)))
        socket_grad.setColorAt(0.45, QColor(18, 118, 168, int(242 * boot)))
        socket_grad.setColorAt(0.78, QColor(56, 198, 238, int(240 * boot)))
        socket_grad.setColorAt(0.93, QColor(145, 242, 255, int(245 * boot)))
        socket_grad.setColorAt(1.0, QColor(240, 254, 255, int(252 * boot)))

        sun_rect = QRectF(
            inner_center.x() - sun_radius,
            inner_center.y() - sun_radius,
            sun_radius * 2.0,
            sun_radius * 2.0,
        )
        painter.setBrush(socket_grad)
        painter.setPen(QPen(
            QColor(245, 255, 255, int(248 * boot)),
            max(1.2, 1.8 * scale),
        ))
        painter.drawEllipse(sun_rect)

        # Clip inner iris & moving white pupil cleanly inside the eyeball sphere
        painter.save()
        clip_path = QPainterPath()
        clip_path.addEllipse(sun_rect)
        painter.setClipPath(clip_path)

        # Rotating dark-cyan shadow wave inside the eyeball socket
        shadow_center = QPointF(
            inner_center.x() - math.cos(swirl_angle) * sun_radius * 0.35,
            inner_center.y() - math.sin(swirl_angle) * sun_radius * 0.35,
        )
        shadow_grad = QRadialGradient(shadow_center, sun_radius * 0.95)
        shadow_grad.setColorAt(0.0, QColor(4, 38, 66, int(175 * boot)))
        shadow_grad.setColorAt(0.55, QColor(8, 72, 112, int(95 * boot)))
        shadow_grad.setColorAt(1.0, QColor(18, 130, 178, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shadow_grad)
        painter.drawEllipse(shadow_center, sun_radius * 0.95, sun_radius * 0.95)

        # Soft cyan-white iris aura that moves together with the white pupil
        iris_aura_r = sun_radius * 0.98
        iris_aura = QRadialGradient(pupil_center, iris_aura_r)
        iris_aura.setColorAt(0.0, QColor(255, 255, 255, int(255 * boot)))
        iris_aura.setColorAt(0.58, QColor(200, 252, 255, int(225 * boot)))
        iris_aura.setColorAt(0.85, QColor(64, 210, 245, int(125 * boot)))
        iris_aura.setColorAt(1.0, QColor(18, 138, 185, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(iris_aura)
        painter.drawEllipse(pupil_center, iris_aura_r, iris_aura_r)

        # The Round White Pupil (O'rtadagi yumaloq oq — kattaroq va atrofida hech qanday doira chizig'isiz)
        pupil_r = sun_radius * (0.62 + 0.03 * math.sin(self.phase * 3.4) + boost * 0.05)
        pupil_grad = QRadialGradient(
            pupil_center,
            pupil_r,
            QPointF(pupil_center.x() - pupil_r * 0.16, pupil_center.y() - pupil_r * 0.16),
        )
        pupil_grad.setColorAt(0.0, QColor(255, 255, 255, int(255 * boot)))
        pupil_grad.setColorAt(0.80, QColor(255, 255, 255, int(254 * boot)))
        pupil_grad.setColorAt(0.93, QColor(232, 254, 255, int(240 * boot)))
        pupil_grad.setColorAt(1.0, QColor(175, 246, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pupil_grad)
        painter.drawEllipse(pupil_center, pupil_r, pupil_r)

        painter.restore()
        painter.end()
