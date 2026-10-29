from __future__ import annotations

import math
import random
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QWidget


_GLYPHS = "01010101010101010123456789ABCDEFアイウエオカキクケコサシスセソタチツテト"


class MatrixRain(QWidget):
    def __init__(self, parent=None, *, enabled: bool = True, intensity: int = 35,
                 reduced_motion: bool = False):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.enabled = enabled
        self.reduced_motion = reduced_motion
        self.intensity = max(0, min(100, intensity))
        self.font = QFont("Yu Gothic UI", 10)
        self.font.setStyleHint(QFont.StyleHint.Monospace)
        self.mouse = QPointF(-1000.0, -1000.0)
        self.previous_mouse = self.mouse
        self.velocity = QPointF()
        self.cursor_inside = False
        self.spotlight_alpha = 0.0
        self.audio_strength = 0.0
        self.frame = 0
        self.last_input = time.monotonic()
        self.ripples: list[tuple[QPointF, float, float]] = []
        self.columns: list[tuple[float, float, int]] = []
        self._column_width = 14
        self._row_height = 15
        self._spotlight_radius = 195.0
        self._reset_columns()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.timer.start(40)

    def _reset_columns(self):
        count = max(1, self.width() // self._column_width + 2)
        self.columns = [
            (
                random.uniform(0.0, 320.0),
                random.uniform(0.85, 1.85),
                random.randint(10, 15),
            )
            for _ in range(count)
        ]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reset_columns()

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.update()

    def set_intensity(self, intensity: int):
        self.intensity = max(0, min(100, intensity))
        self.update()

    def set_reduced_motion(self, reduced_motion: bool):
        self.reduced_motion = reduced_motion

    def set_audio_levels(self, levels):
        self.audio_strength = max(levels, default=0.0)

    def set_mouse_position(self, position: QPointF):
        now = time.monotonic()
        elapsed = max(0.008, now - self.last_input)
        new_pos = QPointF(position)
        dx = new_pos.x() - self.mouse.x()
        dy = new_pos.y() - self.mouse.y()
        if math.hypot(dx, dy) > 0.5:
            self.previous_mouse = self.mouse
            self.mouse = new_pos
            self.velocity = QPointF(dx / elapsed, dy / elapsed)
            self.last_input = now
        self.cursor_inside = self.rect().contains(new_pos.toPoint())

    def add_ripple(self, position: QPointF):
        self.ripples.append((QPointF(position), 0.0, time.monotonic()))
        self.ripples = self.ripples[-4:]

    def _poll_cursor(self):
        if not self.isVisible():
            return
        mapped = QPointF(self.mapFromGlobal(QCursor.pos()))
        inside = self.rect().contains(mapped.toPoint())
        self.cursor_inside = inside
        if inside:
            self.set_mouse_position(mapped)

    def _advance(self):
        app = QApplication.instance()
        active = (
            self.isVisible()
            and self.enabled
            and (app is None or app.applicationState() == Qt.ApplicationState.ApplicationActive)
        )
        target_interval = 120 if active and self.reduced_motion else 40 if active else 350
        if self.timer.interval() != target_interval:
            self.timer.setInterval(target_interval)
        if not active:
            return

        self._poll_cursor()
        self.frame += 1
        target_spot = 1.0 if self.cursor_inside else 0.0
        self.spotlight_alpha += (target_spot - self.spotlight_alpha) * 0.22
        speed = math.hypot(self.velocity.x(), self.velocity.y())
        self.velocity = QPointF(self.velocity.x() * 0.78, self.velocity.y() * 0.78)
        for index, (head_y, velocity, trail_len) in enumerate(self.columns):
            x = index * self._column_width
            dx = abs(x - self.mouse.x())
            near = math.exp(-dx / 140.0) * self.spotlight_alpha
            wake = min(2.2, speed / 1800.0) * near
            self.columns[index] = (head_y + velocity * (1.0 + wake) * 3.1, velocity, trail_len)
        now = time.monotonic()
        self.ripples = [r for r in self.ripples if now - r[2] < 0.9]
        self.update()

    def paintEvent(self, event):
        del event
        if not self.enabled or self.intensity <= 0 or self.spotlight_alpha <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self.font)

        intensity_scale = 0.60 + (self.intensity / 100.0) * 0.40
        spot_radius = self._spotlight_radius * (1.0 + 0.08 * self.audio_strength)
        spot_strength = self.spotlight_alpha
        mx = self.mouse.x()
        my = self.mouse.y()

        min_col = max(0, int((mx - spot_radius) // self._column_width) - 1)
        max_col = min(len(self.columns) - 1, int((mx + spot_radius) // self._column_width) + 1)
        min_row = max(0, int((my - spot_radius) // self._row_height) - 1)
        max_row = min(
            int(self.height() // self._row_height) + 1,
            int((my + spot_radius) // self._row_height) + 1,
        )

        stream_period = 17 * self._row_height
        now = time.monotonic()

        for col_idx in range(min_col, max_col + 1):
            head_y, _, trail_length = self.columns[col_idx]
            x = col_idx * self._column_width
            dx_col = x - mx
            if abs(dx_col) > spot_radius:
                continue
            bend_factor = max(-10.0, min(10.0, self.velocity.x() * 0.004))

            for row_idx in range(min_row, max_row + 1):
                y = row_idx * self._row_height
                dist_behind = (head_y - y) % stream_period
                trail_index = int(dist_behind // self._row_height)
                if trail_index >= trail_length:
                    continue

                radial_distance = math.hypot(dx_col, y - my)
                if radial_distance >= spot_radius:
                    continue

                # Smooth circular fade from cursor center (1.0) to circle edge (0.0)
                norm_d = radial_distance / spot_radius
                circle_fade = ((1.0 - norm_d * norm_d) ** 2) * spot_strength

                draw_x = x + bend_factor * (1.0 - norm_d)
                draw_y = y
                for ripple_origin, _, started in self.ripples:
                    age = now - started
                    radius = age * 280.0
                    delta_x = draw_x - ripple_origin.x()
                    delta_y = draw_y - ripple_origin.y()
                    ripple_distance = math.hypot(delta_x, delta_y)
                    wave = math.exp(-abs(ripple_distance - radius) / 20.0) * max(0.0, 1.0 - age / 0.9)
                    if ripple_distance > 0.1:
                        displacement = 10.0 * wave
                        draw_x += delta_x / ripple_distance * displacement
                        draw_y += delta_y / ripple_distance * displacement

                trail_fade = max(0.12, (1.0 - trail_index / trail_length) ** 1.15)
                alpha = min(255, int(255 * intensity_scale * trail_fade * circle_fade * 1.65))
                if alpha <= 6:
                    continue

                character_index = (col_idx * 19 + row_idx * 31 + self.frame // 4) % len(_GLYPHS)
                character = _GLYPHS[character_index]
                color = (
                    QColor(235, 255, 242, alpha)
                    if trail_index == 0
                    else QColor(36, 255, 115, alpha)
                )
                painter.setPen(color)
                painter.drawText(QPointF(draw_x, draw_y), character)

        painter.end()
