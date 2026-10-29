from __future__ import annotations

import datetime
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class SecondsRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(58, 58)
        self.progress = 0
        self.accent_color = QColor("#64d2ff")

    def set_progress(self, progress: int):
        self.progress = max(0, min(59, progress))
        self.update()

    def set_accent(self, color: str):
        self.accent_color = QColor(color)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = max(0, min(self.width(), self.height()) - 10)
        rect = QRectF(5, 5, diameter, diameter)
        painter.setPen(QPen(QColor(160, 226, 242, 40), 2.5))
        painter.drawArc(rect, 0, 360 * 16)
        painter.setPen(
            QPen(self.accent_color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        painter.drawArc(rect, 90 * 16, -int(self.progress / 60 * 360 * 16))
        painter.end()


class WeatherSignals(QObject):
    # requested_city, display_city, temperature, description, is_day
    finished = Signal(str, str, str, str, bool)


def _detect_device_location() -> tuple[str, float | None, float | None]:
    """Automatically detect device city and coordinates via IP or system timezone."""
    for url in ("https://ipwho.is/", "https://ipapi.co/json/"):
        try:
            req = Request(url, headers={"User-Agent": "JARVIS-CE-21/2.1.1"})
            with urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            city = str(data.get("city") or "").strip()
            lat = data.get("latitude")
            lon = data.get("longitude")
            if city and lat is not None and lon is not None:
                return city, float(lat), float(lon)
        except Exception:
            continue

    # Fallback based on device UTC offset
    now = datetime.datetime.now().astimezone()
    offset = now.utcoffset()
    hours = round(offset.total_seconds() / 3600.0) if offset else 0
    tz_Defaults = {
        5: ("Tashkent", 41.2995, 69.2401),
        4: ("Dubai", 25.2048, 55.2708),
        3: ("Istanbul", 41.0082, 28.9784),
        2: ("Berlin", 52.5200, 13.4050),
        1: ("Paris", 48.8566, 2.3522),
        0: ("London", 51.5074, -0.1278),
        -5: ("New York", 40.7128, -74.0060),
        -8: ("Los Angeles", 34.0522, -118.2437),
        8: ("Singapore", 1.3521, 103.8198),
        9: ("Tokyo", 35.6762, 139.6503),
    }
    return tz_Defaults.get(hours, ("Tashkent", 41.2995, 69.2401))


class WeatherTask(QRunnable):
    def __init__(self, city: str = "", lang: str = "en"):
        super().__init__()
        self.city = city.strip()
        self.lang = lang
        self.signals = WeatherSignals()

    def run(self):
        try:
            if not self.city or self.city.lower() == "auto":
                display_city, lat, lon = _detect_device_location()
            else:
                query = urlencode(
                    {"name": self.city, "count": 1, "language": "en", "format": "json"}
                )
                location_request = Request(
                    f"https://geocoding-api.open-meteo.com/v1/search?{query}",
                    headers={"User-Agent": "JARVIS-CE-21/2.1.1"},
                )
                with urlopen(location_request, timeout=8) as response:
                    location_data = json.loads(response.read().decode("utf-8"))
                results = location_data.get("results") or []
                if not results:
                    raise ValueError(f"No weather location found for {self.city}.")
                location = results[0]
                display_city = location.get("name", self.city)
                lat = float(location["latitude"])
                lon = float(location["longitude"])

            weather_query = urlencode(
                {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,weather_code,is_day",
                    "temperature_unit": "celsius",
                }
            )
            weather_request = Request(
                f"https://api.open-meteo.com/v1/forecast?{weather_query}",
                headers={"User-Agent": "JARVIS-CE-21/2.1.1"},
            )
            with urlopen(weather_request, timeout=8) as response:
                weather_data = json.loads(response.read().decode("utf-8"))
            current = weather_data["current"]
            temperature = f"{round(current['temperature_2m'])}°C"
            is_day = bool(current.get("is_day", 1))
            description = _weather_description(int(current["weather_code"]), is_day, self.lang)
            try:
                self.signals.finished.emit(
                    self.city, display_city, temperature, description, is_day
                )
            except RuntimeError:
                pass
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            hour = datetime.datetime.now().hour
            is_day = 6 <= hour < 19
            try:
                self.signals.finished.emit(
                    self.city, self.city or "Auto", "", str(error), is_day
                )
            except RuntimeError:
                pass


def _weather_description(code: int, is_day: bool = True, lang: str = "en") -> str:
    day_tag = {
        "uz": "Kun" if is_day else "Tun",
        "ru": "День" if is_day else "Ночь",
        "en": "Day" if is_day else "Night",
    }.get(lang, "Day" if is_day else "Night")

    table = {
        0: {"en": "Clear sky", "uz": "Ochiq osmon", "ru": "Ясно"},
        1: {"en": "Mostly clear", "uz": "Deyarli ochiq", "ru": "Малооблачно"},
        2: {"en": "Partly cloudy", "uz": "Bulutli", "ru": "Переменная облачность"},
        3: {"en": "Overcast", "uz": "Qalin bulut", "ru": "Пасмурно"},
        45: {"en": "Fog", "uz": "Tuman", "ru": "Туман"},
        48: {"en": "Fog", "uz": "Qirovli tuman", "ru": "Туман"},
        51: {"en": "Drizzle", "uz": "Mayda yomg'ir", "ru": "Морось"},
        53: {"en": "Drizzle", "uz": "Mayda yomg'ir", "ru": "Морось"},
        55: {"en": "Drizzle", "uz": "Mayda yomg'ir", "ru": "Морось"},
        56: {"en": "Freezing drizzle", "uz": "Muzli yomg'ir", "ru": "Ледяная морось"},
        57: {"en": "Freezing drizzle", "uz": "Muzli yomg'ir", "ru": "Ледяная морось"},
        61: {"en": "Rain", "uz": "Yomg'ir", "ru": "Дождь"},
        63: {"en": "Rain", "uz": "Yomg'ir", "ru": "Дождь"},
        65: {"en": "Heavy rain", "uz": "Kuchli yomg'ir", "ru": "Сильный дождь"},
        66: {"en": "Freezing rain", "uz": "Muzli yomg'ir", "ru": "Ледяной дождь"},
        67: {"en": "Freezing rain", "uz": "Muzli yomg'ir", "ru": "Ледяной дождь"},
        71: {"en": "Snow", "uz": "Qor", "ru": "Снег"},
        73: {"en": "Snow", "uz": "Qor", "ru": "Снег"},
        75: {"en": "Heavy snow", "uz": "Kuchli qor", "ru": "Сильный снег"},
        77: {"en": "Snow grains", "uz": "Qor donalari", "ru": "Снежная крупа"},
        80: {"en": "Rain showers", "uz": "Jala", "ru": "Ливень"},
        81: {"en": "Rain showers", "uz": "Jala", "ru": "Ливень"},
        82: {"en": "Heavy showers", "uz": "Kuchli jala", "ru": "Сильный ливень"},
        85: {"en": "Snow showers", "uz": "Qor bo'roni", "ru": "Снегопад"},
        86: {"en": "Snow showers", "uz": "Qor bo'roni", "ru": "Снегопад"},
        95: {"en": "Thunderstorm", "uz": "Momaqaldiroq", "ru": "Гроза"},
        96: {"en": "Thunderstorm", "uz": "Do'lli momaqaldiroq", "ru": "Гроза с градом"},
        99: {"en": "Thunderstorm", "uz": "Kuchli momaqaldiroq", "ru": "Сильная гроза"},
    }
    cond = table.get(code, {}).get(lang) or table.get(code, {}).get("en") or "Clear"
    return f"{day_tag} · {cond}"
