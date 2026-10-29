from __future__ import annotations

import math
import random

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import QMenu, QWidget


_MENU_STYLE = """
QMenu {
    background-color: rgba(4, 15, 26, 244);
    color: #e8fbff;
    border: 1px solid rgba(86, 230, 220, 145);
    border-radius: 10px;
    padding: 6px;
    font-family: "Syne", "Segoe UI";
    font-size: 9.5pt;
}
QMenu::item {
    padding: 7px 16px;
    border-radius: 6px;
}
QMenu::item:selected {
    background-color: rgba(42, 210, 235, 55);
    color: #79f7ff;
}
QMenu::separator {
    height: 1px;
    background: rgba(86, 230, 220, 45);
    margin: 4px 8px;
}
"""


class FloatingOrb(QWidget):
    activated = Signal()
    mute_requested = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setFixedSize(148, 148)
        self.setToolTip(
            "J.A.R.V.I.S. CE-21\n"
            "• 1x bosish: Boshqaruv tugmalari\n"
            "• 2x bosish (yoki markaz): Asosiy oynaga qaytish\n"
            "• O'ng tugma: Tezkor menyu"
        )
        self.phase = 0.0
        self.pupil_pos = QPointF(0.0, 0.0)
        self.pupil_target = QPointF(0.0, 0.0)
        self.pupil_ticks = 0
        self.state = "IDLE"
        self.muted = False
        self.level = 0.0
        self.spectrum = [0.0] * 64
        self.hovered = False
        self.controls_open = False
        self.hovered_button: str | None = None
        self._drag_offset: QPoint | None = None
        self._dragged = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(28)

    def set_state(self, state: str):
        self.state = state.upper()
        self.muted = self.state == "MUTED"
        self.update()

    def set_audio_levels(self, levels):
        if not levels:
            return
        mean_lvl = sum(levels) / len(levels)
        peak_lvl = max(levels)
        target = min(1.0, (mean_lvl * 0.65 + peak_lvl * 0.45) * 1.45)
        self.level = max(self.level, target)
        count = len(self.spectrum)
        src_len = len(levels)
        for i in range(count):
            idx = min(src_len - 1, int(i * src_len / count))
            self.spectrum[i] = max(float(levels[idx]), self.spectrum[i] * 0.65)
        self.update()

    def _advance(self):
        if not self.isVisible():
            if self._timer.interval() != 350:
                self._timer.setInterval(350)
            return
        if self._timer.interval() != 28:
            self._timer.setInterval(28)
        speed = (
            0.068
            if self.state == "SPEAKING"
            else 0.052
            if self.state in {"THINKING", "PROCESSING"}
            else 0.028
        )
        self.phase += speed
        self.pupil_ticks -= 1
        if self.pupil_ticks <= 0:
            directions = (
                (-0.68, 0.0),
                (0.68, 0.0),
                (0.0, -0.65),
                (0.0, 0.65),
                (-0.52, -0.45),
                (0.52, -0.45),
                (-0.52, 0.45),
                (0.52, 0.45),
                (0.0, 0.0),
            )
            gx, gy = random.choice(directions)
            self.pupil_target = QPointF(
                gx + random.uniform(-0.12, 0.12),
                gy + random.uniform(-0.12, 0.12),
            )
            self.pupil_ticks = random.randint(20, 46)
        orbit_x = math.cos(self.phase * 1.75) * 0.28
        orbit_y = math.sin(self.phase * 1.25) * 0.28
        tx = max(-0.82, min(0.82, self.pupil_target.x() * 0.72 + orbit_x))
        ty = max(-0.82, min(0.82, self.pupil_target.y() * 0.72 + orbit_y))
        self.pupil_pos = QPointF(
            self.pupil_pos.x() + (tx - self.pupil_pos.x()) * 0.14,
            self.pupil_pos.y() + (ty - self.pupil_pos.y()) * 0.14,
        )
        self.level *= 0.88
        for i in range(len(self.spectrum)):
            self.spectrum[i] *= 0.84
        self.update()

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _open_center(self) -> QPointF:
        return self._center()

    def _mic_center(self) -> QPointF:
        c = self._center()
        angle = -math.pi * 0.75  # Top-left 45° on outer ring
        return QPointF(c.x() + math.cos(angle) * 53.0, c.y() + math.sin(angle) * 53.0)

    def _close_center(self) -> QPointF:
        c = self._center()
        angle = -math.pi * 0.25  # Top-right 45° on outer ring
        return QPointF(c.x() + math.cos(angle) * 53.0, c.y() + math.sin(angle) * 53.0)

    def _hit_button(self, pos: QPointF) -> str | None:
        if not (self.controls_open or self.hovered):
            return None
        mc = self._mic_center()
        if math.hypot(pos.x() - mc.x(), pos.y() - mc.y()) <= 14.5:
            return "mic"
        cc = self._close_center()
        if math.hypot(pos.x() - cc.x(), pos.y() - cc.y()) <= 14.5:
            return "close"
        oc = self._open_center()
        if math.hypot(pos.x() - oc.x(), pos.y() - oc.y()) <= 23.0:
            return "open"
        return None

    def enterEvent(self, event):
        super().enterEvent(event)
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.hovered = False
        self.hovered_button = None
        self.update()

    def _show_context_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_STYLE)
        open_action = menu.addAction("⤢   Asosiy oynaga qaytish (Open J.A.R.V.I.S.)")
        mic_label = (
            "◉   Mikrofonni yoqish (Unmute · F4)"
            if self.muted
            else "◉   Mikrofonni o'chirish (Mute · F4)"
        )
        mic_action = menu.addAction(mic_label)
        menu.addSeparator()
        quit_action = menu.addAction("✕   Ilovadan butunlay chiqish (Quit)")
        selected = menu.exec(global_pos)
        if selected is open_action:
            self.controls_open = False
            self.activated.emit()
        elif selected is mic_action:
            self.mute_requested.emit()
        elif selected is quit_action:
            self.quit_requested.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragged = False
            event.accept()

    def mouseMoveEvent(self, event):
        pos = event.position()
        btn = self._hit_button(pos)
        if btn != self.hovered_button:
            self.hovered_button = btn
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if btn is not None
                else Qt.CursorShape.ArrowCursor
            )
            self.update()

        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            global_position = event.globalPosition().toPoint()
            self._dragged = self._dragged or (
                global_position - self._drag_offset - self.frameGeometry().topLeft()
            ).manhattanLength() > 5
            if self._dragged:
                self.move(global_position - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_offset is not None:
            self._drag_offset = None
            if not self._dragged:
                hit = self._hit_button(event.position())
                if hit == "open":
                    self.controls_open = False
                    self.activated.emit()
                elif hit == "mic":
                    self.mute_requested.emit()
                elif hit == "close":
                    self.quit_requested.emit()
                else:
                    self.controls_open = not self.controls_open
                    self.update()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit_button(event.position())
            if hit not in {"mic", "close"}:
                self.controls_open = False
                self.activated.emit()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        center = self._center()
        pulse = 1.0 + 0.042 * math.sin(self.phase * 1.9) + self.level * 0.22
        outer_r = 62.0

        is_error = self.state == "ERROR"
        is_speaking = self.state == "SPEAKING"
        is_thinking = self.state in {"THINKING", "PROCESSING", "CONNECTING"}

        if is_error:
            c_main = QColor("#ff6464")
            c_bright = QColor("#ffd2d2")
            c_sec = QColor("#ff9b50")
            c_deep = QColor("#2a0b10")
        elif self.muted:
            c_main = QColor("#f0a854")
            c_bright = QColor("#ffeed2")
            c_sec = QColor("#64b8d8")
            c_deep = QColor("#24170a")
        elif is_speaking:
            c_main = QColor("#58f6ff")
            c_bright = QColor("#ffffff")
            c_sec = QColor("#ffb85c")
            c_deep = QColor("#062638")
        else:
            c_main = QColor("#4ce8e0")
            c_bright = QColor("#e8feff")
            c_sec = QColor("#f0b45a")
            c_deep = QColor("#062030")

        def col_alpha(col: QColor, a: int) -> QColor:
            c = QColor(col)
            c.setAlpha(max(0, min(255, int(a))))
            return c

        # 1. Atmospheric holographic radial field (identical to main ArcCore, pure translucent)
        field = QRadialGradient(center, outer_r * 1.18)
        field.setColorAt(0.0, col_alpha(c_main, 86 + int(self.level * 55)))
        field.setColorAt(0.38, col_alpha(c_main, 46))
        field.setColorAt(0.75, col_alpha(c_deep, 95))
        field.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(field)
        painter.drawEllipse(center, outer_r * 1.18, outer_r * 1.18)

        # 2. Outer precision 72-tick degree gauge + 4 cardinal reticles
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(col_alpha(c_main, 52), 1.0))
        painter.drawEllipse(center, outer_r, outer_r)

        for i in range(72):
            angle = math.tau * i / 72.0 + self.phase * 0.08
            is_cardinal = i % 18 == 0
            is_major = i % 6 == 0
            inner_k = 0.91 if is_cardinal else (0.94 if is_major else 0.968)
            outer_k = 1.03 if is_cardinal else 1.0
            alpha = 205 if is_cardinal else (120 if is_major else 52)
            pen_col = c_sec if is_cardinal else c_main
            painter.setPen(
                QPen(
                    col_alpha(pen_col, alpha),
                    1.6 if is_cardinal else (1.1 if is_major else 0.8),
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            p1 = QPointF(
                center.x() + math.cos(angle) * outer_r * inner_k,
                center.y() + math.sin(angle) * outer_r * inner_k,
            )
            p2 = QPointF(
                center.x() + math.cos(angle) * outer_r * outer_k,
                center.y() + math.sin(angle) * outer_r * outer_k,
            )
            painter.drawLine(p1, p2)

        # 3. Classic Stark 10-segment Arc Reactor outer coils
        coil_r = outer_r * 0.86
        coil_rect = QRectF(center.x() - coil_r, center.y() - coil_r, coil_r * 2.0, coil_r * 2.0)
        painter.setPen(
            QPen(col_alpha(c_main, 155), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
        )
        for seg in range(10):
            start_deg = seg * 36.0 + 4.0 - self.phase * 6.0
            painter.drawArc(coil_rect, round(start_deg * 16), round(26.0 * 16))

        # 4. Counter-rotating Cyan & Amber tactical scanner arcs
        for r_factor, width, segs, rot_deg, sweep_deg, color in (
            (0.76, 2.2, 3, self.phase * 36.0, 62.0, col_alpha(c_bright, 210)),
            (0.70, 1.4, 4, -self.phase * 28.0, 34.0, col_alpha(c_sec, 190)),
            (0.63, 1.8, 2, self.phase * 48.0 + 30.0, 88.0, col_alpha(c_main, 165)),
        ):
            r = outer_r * r_factor
            rect = QRectF(center.x() - r, center.y() - r, r * 2.0, r * 2.0)
            painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            step = 360.0 / segs
            for s in range(segs):
                painter.drawArc(rect, round((rot_deg + s * step) * 16), round(sweep_deg * 16))

        # 5. 64-bar Radial Audio Spectrum Equalizer
        eq_base_r = outer_r * 0.48
        eq_max_len = outer_r * 0.13
        for i, val in enumerate(self.spectrum):
            angle = math.tau * i / len(self.spectrum) - self.phase * 0.35
            anim_wave = 0.14 + 0.10 * math.sin(angle * 4.0 + self.phase * 2.6)
            bar_val = max(val * 1.15, anim_wave if (is_speaking or is_thinking) else 0.08)
            bar_len = max(1.5, eq_max_len * min(1.0, bar_val))
            p1 = QPointF(
                center.x() + math.cos(angle) * eq_base_r,
                center.y() + math.sin(angle) * eq_base_r,
            )
            p2 = QPointF(
                center.x() + math.cos(angle) * (eq_base_r + bar_len),
                center.y() + math.sin(angle) * (eq_base_r + bar_len),
            )
            bar_col = c_sec if (i % 8 == 0 and bar_val > 0.30) else c_main
            painter.setPen(
                QPen(
                    col_alpha(bar_col, 90 + int(150 * min(1.0, bar_val))),
                    1.35,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                )
            )
            painter.drawLine(p1, p2)

        # 6. Continuous Harmonic Plasma Wave
        for w_idx in range(2):
            wave_r = outer_r * (0.41 - w_idx * 0.04) * pulse
            path = QPainterPath()
            steps = 72
            for idx in range(steps + 1):
                ang = math.tau * idx / steps
                wobble = (
                    math.sin(ang * (4 + w_idx * 2) + self.phase * (2.2 + w_idx * 0.7))
                    * (1.0 + self.level * 4.8)
                )
                rr = wave_r + wobble
                px = center.x() + math.cos(ang) * rr
                py = center.y() + math.sin(ang) * rr
                if idx == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            w_col = c_bright if w_idx == 0 else c_sec
            painter.setPen(QPen(col_alpha(w_col, 130 - w_idx * 40), 1.1 - w_idx * 0.2))
            painter.drawPath(path)

        # 7. Inner Hexagonal Geometric Lattice + 3D Toroidal Plasma Core
        core_r = outer_r * 0.26 * pulse
        for h_mult, h_rot, h_alpha in (
            (1.36, self.phase * 0.7, 115),
            (1.16, -self.phase * 0.9, 88),
        ):
            poly = QPolygonF()
            hr = core_r * h_mult
            for k in range(6):
                ang = h_rot + k * (math.tau / 6.0)
                poly.append(
                    QPointF(center.x() + math.cos(ang) * hr, center.y() + math.sin(ang) * hr)
                )
            painter.setPen(QPen(col_alpha(c_bright, h_alpha), 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolygon(poly)

        bloom = QRadialGradient(center, core_r * 2.1)
        bloom.setColorAt(0.0, col_alpha(c_bright, 220))
        bloom.setColorAt(0.45, col_alpha(c_main, 125))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bloom)
        painter.drawEllipse(center, core_r * 2.1, core_r * 2.1)

        swirl_ang = self.phase * 1.85
        socket_focal = QPointF(
            center.x() - math.cos(swirl_ang) * core_r * 0.30,
            center.y() - math.sin(swirl_ang) * core_r * 0.30,
        )
        sphere = QRadialGradient(center, core_r * 1.04, socket_focal)
        sphere.setColorAt(0.0, QColor(10, 68, 104, 245))
        sphere.setColorAt(0.45, QColor(18, 118, 168, 242))
        sphere.setColorAt(0.78, col_alpha(c_main, 240))
        sphere.setColorAt(0.93, col_alpha(c_bright, 245))
        sphere.setColorAt(1.0, QColor("#ffffff"))
        core_rect = QRectF(center.x() - core_r, center.y() - core_r, core_r * 2.0, core_r * 2.0)
        painter.setPen(QPen(col_alpha(c_bright, 248), 1.4))
        painter.setBrush(sphere)
        painter.drawEllipse(core_rect)

        max_shift = core_r * 0.36
        px = self.pupil_pos.x() * max_shift
        py = self.pupil_pos.y() * max_shift
        pupil_center = QPointF(center.x() + px, center.y() + py)

        painter.save()
        clip_path = QPainterPath()
        clip_path.addEllipse(core_rect)
        painter.setClipPath(clip_path)

        iris_aura = QRadialGradient(pupil_center, core_r * 0.98)
        iris_aura.setColorAt(0.0, QColor(255, 255, 255, 255))
        iris_aura.setColorAt(0.58, col_alpha(c_bright, 225))
        iris_aura.setColorAt(0.85, col_alpha(c_main, 125))
        iris_aura.setColorAt(1.0, QColor(18, 138, 185, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(iris_aura)
        painter.drawEllipse(pupil_center, core_r * 0.98, core_r * 0.98)

        pupil_r = core_r * (0.62 + 0.03 * math.sin(self.phase * 3.4))
        pupil_grad = QRadialGradient(pupil_center, pupil_r)
        pupil_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        pupil_grad.setColorAt(0.80, QColor(255, 255, 255, 254))
        pupil_grad.setColorAt(0.93, QColor(232, 254, 255, 240))
        pupil_grad.setColorAt(1.0, QColor(175, 246, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pupil_grad)
        painter.drawEllipse(pupil_center, pupil_r, pupil_r)
        painter.restore()

        # 8. Sleek Holographic YouTube-PiP Controls (only when hovered or clicked)
        if self.controls_open or self.hovered:
            # Center core turns into a glowing holographic "⤢" expand portal
            open_hover = self.hovered_button == "open"
            portal_r = core_r * 1.18
            portal_grad = QRadialGradient(center, portal_r)
            if open_hover:
                portal_grad.setColorAt(0.0, QColor(4, 24, 38, 225))
                portal_grad.setColorAt(0.8, QColor(12, 68, 92, 235))
                portal_grad.setColorAt(1.0, col_alpha(c_bright, 255))
            else:
                portal_grad.setColorAt(0.0, QColor(4, 18, 30, 210))
                portal_grad.setColorAt(0.85, QColor(8, 38, 56, 220))
                portal_grad.setColorAt(1.0, col_alpha(c_main, 220))
            painter.setPen(
                QPen(QColor("#ffffff") if open_hover else col_alpha(c_bright, 230), 1.5)
            )
            painter.setBrush(portal_grad)
            painter.drawEllipse(center, portal_r, portal_r)

            # Crisp vector expand arrows ("⤢") inside center core
            arr_col = QColor("#79f7ff") if open_hover else QColor("#effdff")
            painter.setPen(
                QPen(arr_col, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            )
            d = 5.8
            # Top-right arrow
            painter.drawLine(QPointF(center.x() + 1.2, center.y() - 1.2), QPointF(center.x() + d, center.y() - d))
            painter.drawLine(QPointF(center.x() + d, center.y() - d), QPointF(center.x() + d - 3.6, center.y() - d))
            painter.drawLine(QPointF(center.x() + d, center.y() - d), QPointF(center.x() + d, center.y() - d + 3.6))
            # Bottom-left arrow
            painter.drawLine(QPointF(center.x() - 1.2, center.y() + 1.2), QPointF(center.x() - d, center.y() + d))
            painter.drawLine(QPointF(center.x() - d, center.y() + d), QPointF(center.x() - d + 3.6, center.y() + d))
            painter.drawLine(QPointF(center.x() - d, center.y() + d), QPointF(center.x() - d, center.y() + d - 3.6))

            # Top-left holographic satellite node: Microphone
            mc = self._mic_center()
            mic_hover = self.hovered_button == "mic"
            node_r = 12.5
            painter.setPen(
                QPen(
                    QColor("#ffcc7a")
                    if self.muted
                    else (QColor("#ffffff") if mic_hover else col_alpha(c_main, 210)),
                    1.3,
                )
            )
            painter.setBrush(
                QColor(46, 28, 12, 235)
                if self.muted
                else (QColor(16, 64, 88, 240) if mic_hover else QColor(5, 20, 34, 228))
            )
            painter.drawEllipse(mc, node_r, node_r)
            mic_col = QColor("#ffcc7a") if self.muted else QColor("#effdff")
            painter.setPen(QPen(mic_col, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.setBrush(mic_col if not self.muted else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(mc.x() - 2.2, mc.y() - 5.5, 4.4, 6.8), 2.1, 2.1)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawArc(QRectF(mc.x() - 4.4, mc.y() - 3.8, 8.8, 7.4), 180 * 16, 180 * 16)
            painter.drawLine(QPointF(mc.x(), mc.y() + 3.6), QPointF(mc.x(), mc.y() + 5.6))
            if self.muted:
                painter.setPen(QPen(QColor("#ff7864"), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(mc.x() - 5.0, mc.y() - 4.5), QPointF(mc.x() + 5.0, mc.y() + 4.5))

            # Top-right holographic satellite node: Quit ("✕")
            cc = self._close_center()
            close_hover = self.hovered_button == "close"
            painter.setPen(
                QPen(QColor("#ff9494") if close_hover else QColor(255, 120, 120, 195), 1.3)
            )
            painter.setBrush(
                QColor(150, 28, 38, 240) if close_hover else QColor(28, 10, 16, 228)
            )
            painter.drawEllipse(cc, node_r, node_r)
            x_col = QColor("#ffffff") if close_hover else QColor("#ffd0d0")
            painter.setPen(QPen(x_col, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            xr = 3.8
            painter.drawLine(QPointF(cc.x() - xr, cc.y() - xr), QPointF(cc.x() + xr, cc.y() + xr))
            painter.drawLine(QPointF(cc.x() + xr, cc.y() - xr), QPointF(cc.x() - xr, cc.y() + xr))

        painter.end()
