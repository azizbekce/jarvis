from __future__ import annotations

import math
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

AUDIO_BAND_COUNT = 160


class AudioVisualizer:
    """Extract responsive voice-range FFT bands from 16-bit PCM audio streams."""

    BAND_COUNT = AUDIO_BAND_COUNT

    @classmethod
    def analyze_pcm(cls, pcm: bytes) -> tuple[float, ...]:
        if not pcm:
            return (0.0,) * cls.BAND_COUNT
        samples = np.frombuffer(pcm, dtype="<i2")
        if samples.size < 32:
            return (0.0,) * cls.BAND_COUNT

        signal = samples.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(signal))))
        if rms < 0.0015:
            return (0.0,) * cls.BAND_COUNT

        windowed = signal * np.hanning(signal.size)
        spectrum = np.abs(np.fft.rfft(windowed)) / max(1.0, math.sqrt(signal.size))

        # Focus on the human speech frequency bins (first ~55% of Nyquist) so all bars react
        voice_bins = max(16, int(spectrum.size * 0.58))
        spectrum = spectrum[1:voice_bins]
        if spectrum.size < 4:
            return (0.0,) * cls.BAND_COUNT

        # Interpolate smoothly across BAND_COUNT bands and apply perceptual compression
        x_src = np.linspace(0.0, 1.0, spectrum.size)
        x_dst = np.linspace(0.0, 1.0, cls.BAND_COUNT)
        bands = np.interp(x_dst, x_src, spectrum)

        # Boost mid/high speech formants and blend with overall voice RMS envelope
        freq_tilt = np.linspace(1.0, 2.4, cls.BAND_COUNT, dtype=np.float32)
        envelope = min(1.0, rms * 11.5)
        shaped = np.power(np.maximum(0.0, bands * freq_tilt * 2.8), 0.62)
        wave = 0.35 * envelope * (0.55 + 0.45 * np.sin(np.linspace(0.0, math.pi * 3.0, cls.BAND_COUNT)))
        final_bands = np.clip(shaped * 0.78 + wave, 0.0, 1.0)
        return tuple(float(v) for v in final_bands)


class AudioSpectrumWidget(QWidget):
    """Render live frequency bars with smooth attack and decay."""

    def __init__(self, accent: str, parent=None):
        super().__init__(parent)
        self.accent = QColor(accent)
        self.levels = [0.0] * AUDIO_BAND_COUNT
        self.target_levels = [0.0] * AUDIO_BAND_COUNT
        self.active = False
        self._phase = 0.0
        self.setMinimumHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(28)

    def set_levels(self, levels):
        if not levels:
            return
        src_len = len(levels)
        for i in range(AUDIO_BAND_COUNT):
            idx = min(src_len - 1, int(i * src_len / AUDIO_BAND_COUNT))
            val = max(0.0, min(1.0, float(levels[idx])))
            if val > self.target_levels[i]:
                self.target_levels[i] = val
            else:
                self.target_levels[i] = self.target_levels[i] * 0.50 + val * 0.50
            if val > self.levels[i]:
                self.levels[i] = self.levels[i] * 0.20 + val * 0.80
        self.update()

    def _tick(self):
        if not self.isVisible():
            return
        self._phase += 0.24
        changed = False
        for i in range(AUDIO_BAND_COUNT):
            target = self.target_levels[i]
            curr = self.levels[i]
            if target > curr:
                new_val = curr + (target - curr) * 0.65
            else:
                new_val = curr * 0.78
            if abs(new_val - curr) > 0.003:
                changed = True
            self.levels[i] = new_val if new_val > 0.004 else 0.0
            self.target_levels[i] *= 0.76
        if changed or self.active:
            self.update()

    def set_active(self, active: bool):
        if self.active != active:
            self.active = active
            self.update()

    def set_accent(self, accent: str):
        self.accent = QColor(accent)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center_y = self.height() / 2.0
        bar_count = min(40, max(1, self.width() // 5))
        gap = 2
        bar_width = max(1.0, (self.width() - gap * (bar_count - 1)) / bar_count)
        peak = max(self.levels, default=0.0)
        is_live = self.active or peak > 0.02
        base_alpha = 235 if is_live else 85
        painter.setPen(Qt.PenStyle.NoPen)

        for index in range(bar_count):
            source_index = round(index * (AUDIO_BAND_COUNT - 1) / max(1, bar_count - 1))
            level = self.levels[source_index]
            height = max(2.2, level * (self.height() - 3.0))
            color = QColor(self.accent)
            color.setAlpha(min(255, int(base_alpha if level > 0.04 else 90)))
            painter.setBrush(color)
            x = index * (bar_width + gap)
            painter.drawRoundedRect(
                x, center_y - height / 2.0, bar_width, height, 1.5, 1.5
            )
        painter.end()
