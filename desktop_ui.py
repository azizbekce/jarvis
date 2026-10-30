from __future__ import annotations

import hashlib
import json
import locale
import logging
import os
import platform
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QEvent,
    QLocale,
    QLockFile,
    QObject,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import psutil

from arc_core import ArcCore
from audio_visualizer import AUDIO_BAND_COUNT, AudioSpectrumWidget
from config import APP_DATA_DIR, get_config, update_config
from dashboard_widgets import SecondsRing, WeatherTask
from floating_orb import FloatingOrb
from matrix_rain import MatrixRain
from native_backdrop import apply_acrylic_backdrop
from theme import build_stylesheet


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _app_data_dir() -> Path:
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "JARVIS"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "JARVIS"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "jarvis"


def _load_ui_fonts() -> tuple[list[int], set[str]]:
    font_dir = Path(getattr(sys, "_MEIPASS", BASE_DIR)) / "assets" / "fonts"
    loaded_ids = []
    families = set()
    for filename in (
        "Syne-Regular.ttf",
        "Syne-Medium.ttf",
        "Syne-SemiBold.ttf",
        "Syne-Bold.ttf",
        "Syne-ExtraBold.ttf",
        "TS Block Bold.ttf",
    ):
        font_path = font_dir / filename
        if not font_path.is_file():
            logging.getLogger(__name__).warning("Bundled UI font is missing: %s", font_path)
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            logging.getLogger(__name__).warning("Could not load UI font: %s", font_path)
            continue
        loaded_ids.append(font_id)
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    return loaded_ids, families


def _detect_system_language() -> str:
    """Detect system language code ('uz', 'ru', or 'en')."""
    try:
        sys_loc = QLocale.system().name().lower()
    except Exception:
        sys_loc = (locale.getdefaultlocale()[0] or "en").lower()
    if sys_loc.startswith("uz"):
        return "uz"
    if sys_loc.startswith("ru"):
        return "ru"
    return "en"


BASE_DIR = _base_dir()
CONFIG_FILE = BASE_DIR / "config" / "api_keys.json"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"
ACCENTS = {
    "Cyan": "#56e6dc",
    "Ice": "#8ac9ff",
    "Amber": "#efb86b",
}
UI_LANGUAGES = ("Auto (System)", "O'zbekcha", "English", "Русский")
VOICE_PRESETS = ("Charon", "Aoede", "Fenrir", "Kore", "Puck")

_SELF_CLOSE_TRIGGERS = (
    "o'zingni yop",
    "ozingni yop",
    "dasturdan chiq",
    "ilovadan chiq",
    "jarvis yopil",
    "jarvis o'ch",
    "close yourself",
    "shut down jarvis",
    "quit jarvis",
    "exit jarvis",
    "закрой себя",
    "выключись джарвис",
)


class _UiSignals(QObject):
    log = Signal(str)
    stream = Signal(str, str, bool)
    state = Signal(str)
    audio_levels = Signal(object, str)
    quit = Signal()


class _CommandInput(QPlainTextEdit):
    sendRequested = Signal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.sendRequested.emit()
                return
        super().keyPressEvent(event)


class _MainWindow(QMainWindow):
    def __init__(self, tray_available: bool):
        super().__init__()
        self.tray_available = tray_available
        self.on_close = None
        self.on_minimize = None

    def changeEvent(self, event):
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self.on_minimize
        ):
            QTimer.singleShot(0, self.on_minimize)

    def closeEvent(self, event):
        if self.on_close:
            event.ignore()
            self.on_close()
        else:
            event.accept()
            QApplication.quit()


class _DesktopInputFilter(QObject):
    def __init__(self, owner: "JarvisUI"):
        super().__init__(owner.app)
        self.owner = owner

    def eventFilter(self, watched, event):
        if event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
            QEvent.Type.MouseButtonPress,
        ):
            if hasattr(event, "globalPosition"):
                point = event.globalPosition().toPoint()
            else:
                from PySide6.QtGui import QCursor

                point = QCursor.pos()
            matrix_point = self.owner.matrix.mapFromGlobal(point)
            core_point = self.owner.orb.mapFromGlobal(point)
            self.owner.matrix.set_mouse_position(matrix_point)
            self.owner.orb.set_pointer_pos(core_point)
            if event.type() == QEvent.Type.MouseButtonPress:
                self.owner.matrix.add_ripple(matrix_point)
        elif watched is self.owner.central and event.type() == QEvent.Type.Resize:
            self.owner.matrix.setGeometry(self.owner.central.rect())
        return False


class _SettingsDialog(QDialog):
    def __init__(self, owner: "JarvisUI"):
        super().__init__(owner.window)
        self.owner = owner
        lang = owner._active_lang()
        titles = {
            "uz": "J.A.R.V.I.S. CE-21 — Sozlamalar va Ruxsatlar",
            "ru": "J.A.R.V.I.S. CE-21 — Настройки и Разрешения",
            "en": "J.A.R.V.I.S. CE-21 — Settings & Permissions",
        }
        self.setWindowTitle(titles.get(lang, titles["en"]))
        self.setMinimumWidth(540)
        self.setModal(True)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # 1. Appearance & Device Sync Tab
        appearance = QWidget()
        appearance_form = QFormLayout(appearance)
        self.language_box = QComboBox()
        self.language_box.addItems(UI_LANGUAGES)
        self.language_box.setCurrentText(owner.ui_language)
        self.accent_box = QComboBox()
        self.accent_box.addItems(ACCENTS)
        self.accent_box.setCurrentText(owner.accent_name)
        self.motion_check = QCheckBox(
            "Animatsiyani kamaytirish" if lang == "uz"
            else "Уменьшить анимацию" if lang == "ru"
            else "Reduce animation"
        )
        self.motion_check.setChecked(owner.reduced_motion)
        self.matrix_check = QCheckBox(
            "Sichqoncha atrofida Matrix yomg'iri" if lang == "uz"
            else "Матричный дождь вокруг курсора" if lang == "ru"
            else "Enable circular cursor Matrix Rain"
        )
        self.matrix_check.setChecked(owner.matrix_enabled)
        self.matrix_intensity = QSlider(Qt.Orientation.Horizontal)
        self.matrix_intensity.setRange(0, 100)
        self.matrix_intensity.setValue(owner.matrix_intensity)
        self.sound_check = QCheckBox(
            "Interfeys tovushlarini yoqish" if lang == "uz"
            else "Звуки интерфейса" if lang == "ru"
            else "Enable interface sounds"
        )
        self.sound_check.setChecked(owner.ui_sounds)
        self.name_input = QLineEdit(owner.display_name)
        self.name_input.setPlaceholderText(
            "Ismingiz (ixtiyoriy)" if lang == "uz"
            else "Ваше имя (необязательно)" if lang == "ru"
            else "Your display name (optional)"
        )
        self.city_input = QLineEdit(owner.weather_city)
        self.city_input.setPlaceholderText(
            "Avto-joylashuv (yoki shahar kiriting)" if lang == "uz"
            else "Авто-локация (или введите город)" if lang == "ru"
            else "Auto-detect device location (or type city)"
        )
        appearance_form.addRow(
            "Til / Language" if lang == "uz" else "Язык" if lang == "ru" else "Language",
            self.language_box,
        )
        appearance_form.addRow(
            "Rang / Accent" if lang == "uz" else "Акцент" if lang == "ru" else "Accent",
            self.accent_box,
        )
        appearance_form.addRow(
            "Harakat" if lang == "uz" else "Движение" if lang == "ru" else "Motion",
            self.motion_check,
        )
        appearance_form.addRow("Matrix", self.matrix_check)
        appearance_form.addRow(
            "Yorqinlik" if lang == "uz" else "Яркость Matrix" if lang == "ru" else "Intensity",
            self.matrix_intensity,
        )
        appearance_form.addRow(
            "Ovozlar" if lang == "uz" else "Звуки" if lang == "ru" else "UI sounds",
            self.sound_check,
        )
        appearance_form.addRow(
            "Foydalanuvchi ismi" if lang == "uz" else "Имя пользователя" if lang == "ru" else "Display name",
            self.name_input,
        )
        appearance_form.addRow(
            "Ob-havo shahri" if lang == "uz" else "Город погоды" if lang == "ru" else "Weather city",
            self.city_input,
        )
        tabs.addTab(
            appearance,
            "Ko'rinish va Sinxron" if lang == "uz" else "Вид и Синхрон." if lang == "ru" else "Appearance & Sync",
        )

        # 2. Audio & Voice Tab
        audio = QWidget()
        audio_form = QFormLayout(audio)
        self.microphone_box = QComboBox()
        self.microphone_box.addItem(
            "Tizim standarti (Avto-sinxron)" if lang == "uz"
            else "По умолчанию системы (Авто)" if lang == "ru"
            else "System default (Auto-sync)",
            None,
        )
        self._load_microphones()
        if owner.audio_device is not None:
            index = self.microphone_box.findData(owner.audio_device)
            if index >= 0:
                self.microphone_box.setCurrentIndex(index)
        self.voice_box = QComboBox()
        self.voice_box.addItems(VOICE_PRESETS)
        self.voice_box.setCurrentText(owner.voice_name)
        voice_note = QLabel(
            "Ovoz tembri. Mikrofon va karnaylarga avtomatik moslashadi." if lang == "uz"
            else "Голосовой пресет. Автоматически адаптируется к микрофону и динамикам." if lang == "ru"
            else "Provider voice preset. Automatically adapts to your microphone and speakers."
        )
        voice_note.setWordWrap(True)
        voice_note.setObjectName("mutedNote")
        audio_form.addRow(
            "Mikrofon" if lang == "uz" else "Микрофон" if lang == "ru" else "Microphone",
            self.microphone_box,
        )
        audio_form.addRow(
            "Ovoz turi" if lang == "uz" else "Голос" if lang == "ru" else "Voice preset",
            self.voice_box,
        )
        audio_form.addRow("", voice_note)
        tabs.addTab(
            audio,
            "Audio va Ovoz" if lang == "uz" else "Аудио и Голос" if lang == "ru" else "Audio & Voice",
        )

        # 3. Permissions & System Control Tab
        perms = QWidget()
        perms_layout = QVBoxLayout(perms)
        perms_note = QLabel(
            "J.A.R.V.I.S. CE-21 qurilmangiz bilan to'liq ishlashi uchun ruxsatlar:" if lang == "uz"
            else "Разрешения для полноценной работы J.A.R.V.I.S. CE-21 с устройством:" if lang == "ru"
            else "Grant J.A.R.V.I.S. CE-21 permissions to interact with your device, control applications, and sync weather:"
        )
        perms_note.setWordWrap(True)
        perms_note.setObjectName("mutedNote")
        perms_layout.addWidget(perms_note)

        self.perm_mic_check = QCheckBox(
            "Mikrofon va Jonli Ovozli Muloqot" if lang == "uz"
            else "Микрофон и голосовое распознавание" if lang == "ru"
            else "Microphone & Real-time Voice Recognition"
        )
        self.perm_mic_check.setChecked(owner.perm_microphone)
        self.perm_screen_check = QCheckBox(
            "Ekranni ko'rish va Kamera tahlili (Vision)" if lang == "uz"
            else "Анализ экрана и камеры (Vision)" if lang == "ru"
            else "Screen Vision & Camera Analysis"
        )
        self.perm_screen_check.setChecked(owner.perm_screen)
        self.perm_sys_check = QCheckBox(
            "Tizim, Fayllar va Dasturlarni boshqarish" if lang == "uz"
            else "Управление системой, файлами и программами" if lang == "ru"
            else "System Control, File & App Automation"
        )
        self.perm_sys_check.setChecked(owner.perm_system)
        self.perm_loc_check = QCheckBox(
            "Avto-joylashuv, Kun/Tun ob-havo va Sinxronizatsiya" if lang == "uz"
            else "Авто-локация, погода день/ночь и синхронизация" if lang == "ru"
            else "Auto Location, Day/Night Weather & Device Sync"
        )
        self.perm_loc_check.setChecked(owner.perm_location)
        self.perm_close_check = QCheckBox(
            "Ovoz/Yozuv orqali o'zini yopish ('O'zingni yop')" if lang == "uz"
            else "Самозакрытие голосом/текстом ('Закрой себя')" if lang == "ru"
            else "Self-Shutdown by Voice/Text ('O'zingni yop' / 'Shut down')"
        )
        self.perm_close_check.setChecked(owner.perm_self_close)

        for chk in (
            self.perm_mic_check,
            self.perm_screen_check,
            self.perm_sys_check,
            self.perm_loc_check,
            self.perm_close_check,
        ):
            perms_layout.addWidget(chk)

        perm_btn_row = QHBoxLayout()
        grant_all_btn = QPushButton(
            "✓  Barcha ruxsatlarni yoqish" if lang == "uz"
            else "✓  Включить все разрешения" if lang == "ru"
            else "✓  Grant All Permissions"
        )
        grant_all_btn.clicked.connect(self._grant_all_permissions)
        os_privacy_btn = QPushButton(
            "⚙  Windows Maxfiylik Sozlamalari" if lang == "uz"
            else "⚙  Конфиденциальность Windows" if lang == "ru"
            else "⚙  Windows Privacy Settings"
        )
        os_privacy_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("ms-settings:privacy-microphone"))
        )
        perm_btn_row.addWidget(grant_all_btn)
        perm_btn_row.addWidget(os_privacy_btn)
        perms_layout.addLayout(perm_btn_row)
        perms_layout.addStretch(1)
        tabs.addTab(
            perms,
            "Ruxsatlar" if lang == "uz" else "Разрешения" if lang == "ru" else "Permissions",
        )

        # 4. AI & Startup Tab
        ai = QWidget()
        ai_form = QFormLayout(ai)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText(
            (
                "Gemini API kalitingizni kiriting (majburiy)" if lang == "uz"
                else "Введите ваш ключ Gemini API (обязательно)" if lang == "ru"
                else "Enter your Gemini API key (required)"
            )
            if not owner._api_key_exists()
            else (
                "Saqlangan; yangilash uchun yangi kalit kiriting" if lang == "uz"
                else "Сохранено; введите новый ключ для замены" if lang == "ru"
                else "Stored; enter a new key to replace"
            )
        )
        self.startup_check = QCheckBox(
            "Windows yonganda J.A.R.V.I.S. avtomatik ishga tushsin" if lang == "uz"
            else "Запускать J.A.R.V.I.S. при входе в Windows" if lang == "ru"
            else "Launch JARVIS when I sign in to Windows"
        )
        self.startup_check.setChecked(owner.launch_at_startup)
        ai_note = QLabel(
            "Birinchi o'rnatish: J.A.R.V.I.S. CE-21 ishlashi uchun shaxsiy Gemini API kalitingizni kiriting." if lang == "uz"
            else "Первая настройка: введите ваш личный ключ Gemini API для активации J.A.R.V.I.S. CE-21." if lang == "ru"
            else "First-time setup: enter your personal Gemini API key to activate J.A.R.V.I.S. CE-21 on this computer."
        )
        ai_note.setWordWrap(True)
        ai_note.setObjectName("mutedNote")
        ai_form.addRow("Gemini API Key", self.key_input)
        ai_form.addRow(
            "Avto-ishga tushish" if lang == "uz" else "Автозапуск" if lang == "ru" else "Startup",
            self.startup_check,
        )
        ai_form.addRow("", ai_note)
        tabs.addTab(
            ai,
            "AI va Ishga tushish" if lang == "uz" else "ИИ и Запуск" if lang == "ru" else "AI & Startup",
        )

        if not owner._api_key_exists():
            tabs.setCurrentWidget(ai)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_btn is not None:
            save_btn.setText("Saqlash" if lang == "uz" else "Сохранить" if lang == "ru" else "Save")
        if cancel_btn is not None:
            cancel_btn.setText("Bekor qilish" if lang == "uz" else "Отмена" if lang == "ru" else "Cancel")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _grant_all_permissions(self):
        self.perm_mic_check.setChecked(True)
        self.perm_screen_check.setChecked(True)
        self.perm_sys_check.setChecked(True)
        self.perm_loc_check.setChecked(True)
        self.perm_close_check.setChecked(True)

    def _load_microphones(self):
        try:
            import sounddevice as sd

            for index, device in enumerate(sd.query_devices()):
                if device.get("max_input_channels", 0) > 0:
                    self.microphone_box.addItem(device["name"], index)
        except Exception:
            self.microphone_box.addItem("Audio devices unavailable", None)

    def _save(self):
        api_key = self.key_input.text().strip()
        if not api_key and not self.owner._api_key_exists():
            QMessageBox.warning(
                self,
                "API key required",
                "Please enter your Gemini API key in the 'AI & Startup' tab to connect JARVIS.",
            )
            return
        self.owner._save_settings(
            ui_language=self.language_box.currentText(),
            accent_name=self.accent_box.currentText(),
            reduced_motion=self.motion_check.isChecked(),
            audio_device=self.microphone_box.currentData(),
            voice_name=self.voice_box.currentText(),
            api_key=api_key,
            launch_at_startup=self.startup_check.isChecked(),
            matrix_enabled=self.matrix_check.isChecked(),
            matrix_intensity=self.matrix_intensity.value(),
            ui_sounds=self.sound_check.isChecked(),
            display_name=self.name_input.text().strip(),
            weather_city=self.city_input.text().strip(),
            perm_microphone=self.perm_mic_check.isChecked(),
            perm_screen=self.perm_screen_check.isChecked(),
            perm_system=self.perm_sys_check.isChecked(),
            perm_location=self.perm_loc_check.isChecked(),
            perm_self_close=self.perm_close_check.isChecked(),
        )
        self.accept()


class JarvisUI:
    def __init__(self, face_path=None, size=None):
        del face_path, size
        if platform.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "Mehnatkash.JARVIS.CE21.v211"
                )
            except Exception:
                pass
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setApplicationName("JARVIS")
        self.app.setOrganizationName("JARVIS")
        self._ui_font_ids, self._ui_font_families = _load_ui_fonts()
        self.app.setFont(QFont("Syne" if "Syne" in self._ui_font_families else "Segoe UI"))
        self.is_primary_instance = self._claim_single_instance()
        if not self.is_primary_instance:
            return

        self._settings = self._load_settings()
        self.ui_language = self._settings.get("ui_language", "Auto (System)")
        if self.ui_language not in UI_LANGUAGES:
            self.ui_language = "Auto (System)"
        self.accent_name = self._settings.get("accent", "Cyan")
        if self.accent_name not in ACCENTS:
            self.accent_name = "Cyan"
        self.reduced_motion = bool(self._settings.get("reduced_motion", False))
        self.audio_device = self._settings.get("audio_device")
        self.voice_name = self._settings.get("voice", "Charon")
        if self.voice_name not in VOICE_PRESETS:
            self.voice_name = "Charon"
        self.launch_at_startup = bool(self._settings.get("launch_at_startup", False))
        self.matrix_enabled = bool(self._settings.get("matrix_enabled", True))
        self.matrix_intensity = max(0, min(100, int(self._settings.get("matrix_intensity", 55))))
        self.ui_sounds = bool(self._settings.get("ui_sounds", False))
        self.display_name = str(self._settings.get("display_name", "")).strip()
        self.weather_city = str(self._settings.get("weather_city", "")).strip()
        self.perm_microphone = bool(self._settings.get("perm_microphone", True))
        self.perm_screen = bool(self._settings.get("perm_screen", True))
        self.perm_system = bool(self._settings.get("perm_system", True))
        self.perm_location = bool(self._settings.get("perm_location", True))
        self.perm_self_close = bool(self._settings.get("perm_self_close", True))
        self._last_weather_summary = ""
        self._live_stream_role: str | None = None

        self.on_text_command = None
        self.on_settings_changed = None
        self._voice_state = "IDLE"
        self._muted = False
        self._mute_lock = threading.Lock()
        self._api_ready = threading.Event()
        if self._api_key_exists():
            self._api_ready.set()

        self._signals = _UiSignals()
        self._signals.log.connect(self._append_log)
        self._signals.stream.connect(self._apply_stream_log)
        self._signals.state.connect(self._apply_state)
        self._signals.audio_levels.connect(self._apply_audio_levels)
        self._signals.quit.connect(self._quit_app)

        app_icon = self._make_icon()
        self.app.setWindowIcon(app_icon)
        self.window = _MainWindow(QSystemTrayIcon.isSystemTrayAvailable())
        self.window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.window.setAutoFillBackground(False)
        self.window.setWindowTitle("J.A.R.V.I.S. CE-21 v2.1.1")
        self.window.setWindowIcon(app_icon)
        self.window.setMinimumSize(900, 660)
        self.window.resize(1180, 800)
        self._build_window()
        self.floating_orb = FloatingOrb()
        self._apply_state("IDLE")
        self.floating_orb.activated.connect(self._show_window)
        self.floating_orb.mute_requested.connect(self._toggle_mute)
        self.floating_orb.quit_requested.connect(self._quit_app)
        self.window.on_close = self._quit_app
        self.window.on_minimize = self._hide_to_orb
        self._input_filter = _DesktopInputFilter(self)
        self.app.installEventFilter(self._input_filter)
        self._install_tray()
        self._apply_theme()
        self._apply_language_labels()
        QTimer.singleShot(150, self._apply_native_backdrop)
        QShortcut(QKeySequence("F4"), self.window, activated=self._toggle_mute)
        QShortcut(QKeySequence("Ctrl+K"), self.window, activated=self.open_command_palette)
        if not self._api_key_exists():
            QTimer.singleShot(400, self.open_settings)

    def _active_lang(self) -> str:
        if self.ui_language == "O'zbekcha":
            return "uz"
        if self.ui_language == "Русский":
            return "ru"
        if self.ui_language == "English":
            return "en"
        return _detect_system_language()

    def _claim_single_instance(self) -> bool:
        app_key = hashlib.sha256(
            str(APP_DATA_DIR.resolve()).casefold().encode("utf-8")
        ).hexdigest()[:16]
        self._server_name = f"JARVIS_CE21_{app_key}"
        self._single_instance_lock = QLockFile(str(APP_DATA_DIR / "JARVIS.lock"))
        self._single_instance_server = QLocalServer(self.app)
        self._single_instance_server.setSocketOptions(
            QLocalServer.SocketOption.UserAccessOption
        )
        self._single_instance_server.newConnection.connect(
            self._handle_single_instance_connection
        )

        try:
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            if not self._single_instance_lock.tryLock(0):
                if self._activate_running_instance():
                    return False
                QMessageBox.critical(
                    None,
                    "JARVIS is already running",
                    "Another JARVIS process holds the single-instance lock, "
                    "but its window did not respond. Try again shortly.",
                )
                return False

            QLocalServer.removeServer(self._server_name)
        except OSError as error:
            QMessageBox.critical(
                None,
                "JARVIS could not start",
                f"Could not secure a single running JARVIS instance.\n\n{error}",
            )
            return False

        if self._single_instance_server.listen(self._server_name):
            return True

        error = self._single_instance_server.errorString()
        self._single_instance_lock.unlock()
        QMessageBox.critical(
            None,
            "JARVIS could not start",
            f"Could not secure a single running JARVIS instance.\n\n{error}",
        )
        return False

    def _activate_running_instance(self) -> bool:
        deadline = time.monotonic() + 1.5
        while True:
            socket = QLocalSocket()
            socket.connectToServer(self._server_name)
            if socket.waitForConnected(100):
                break
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

        message = b"activate"
        if socket.write(message) != len(message):
            raise OSError(
                f"Could not activate the running JARVIS window: {socket.errorString()}"
            )
        socket.flush()
        if socket.bytesToWrite() and not socket.waitForBytesWritten(1000):
            if socket.bytesToWrite():
                raise OSError(
                    f"Could not activate the running JARVIS window: {socket.errorString()}"
                )
        socket.disconnectFromServer()
        return True

    def _handle_single_instance_connection(self):
        while self._single_instance_server.hasPendingConnections():
            socket = self._single_instance_server.nextPendingConnection()
            socket.readyRead.connect(
                lambda current=socket: self._handle_single_instance_message(current)
            )
            socket.disconnected.connect(socket.deleteLater)
            if socket.bytesAvailable():
                self._handle_single_instance_message(socket)

    def _handle_single_instance_message(self, socket: QLocalSocket):
        if b"activate" in bytes(socket.readAll()):
            self._show_window()

    @property
    def muted(self) -> bool:
        with self._mute_lock:
            return self._muted

    @muted.setter
    def muted(self, value: bool):
        with self._mute_lock:
            self._muted = bool(value)
        if hasattr(self, "_signals"):
            self._signals.state.emit("MUTED" if value else self._voice_state)

    def _build_window(self):
        central = QWidget()
        self.central = central
        central.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.window.setCentralWidget(central)
        self.matrix = MatrixRain(
            central,
            enabled=self.matrix_enabled,
            intensity=self.matrix_intensity,
            reduced_motion=self.reduced_motion,
        )
        self.matrix.setGeometry(central.rect())
        self.matrix.lower()

        rail = QWidget()
        rail.setObjectName("rail")
        rail.setFixedWidth(204)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(16, 22, 14, 18)
        rail_layout.setSpacing(8)
        brand_box = QVBoxLayout()
        brand_box.setSpacing(3)
        brand = QLabel("J.A.R.V.I.S.")
        brand.setObjectName("brand")
        self.brand_subtitle = QLabel("CE-21  ·  v2.1.1")
        self.brand_subtitle.setObjectName("brandSubtitle")
        brand_divider = QFrame()
        brand_divider.setObjectName("brandDivider")
        brand_box.addWidget(brand)
        brand_box.addWidget(self.brand_subtitle)
        brand_box.addSpacing(5)
        brand_box.addWidget(brand_divider)
        rail_layout.addLayout(brand_box)
        rail_layout.addSpacing(18)
        self.assistant_button = QPushButton("⌂   Assistant")
        self.assistant_button.setObjectName("railButton")
        self.assistant_button.setProperty("active", True)
        self.assistant_button.setToolTip("Assistant")
        self.assistant_button.setMinimumHeight(38)
        rail_layout.addWidget(self.assistant_button)
        self.settings_button = QPushButton("⚙   Settings")
        self.settings_button.setObjectName("railButton")
        self.settings_button.setMinimumHeight(38)
        self.settings_button.clicked.connect(self.open_settings)
        self.settings_button.pressed.connect(self._play_ui_sound)
        rail_layout.addWidget(self.settings_button)
        rail_layout.addStretch(1)
        self.online_status = QLabel("●  READY\n   SYSTEM ONLINE")
        self.online_status.setObjectName("onlineStatus")
        rail_layout.addWidget(self.online_status)
        credit = QLabel("azizbekce\nPOWERED BY MEHNATKASH")
        credit.setObjectName("credit")
        credit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        rail_layout.addWidget(credit)
        root.addWidget(rail)

        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(12)
        heading = QVBoxLayout()
        heading.setSpacing(2)
        self.page_title = QLabel("Personal intelligence")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("VOICE INTERFACE")
        self.page_subtitle.setObjectName("pageSubtitle")
        heading.addWidget(self.page_title)
        heading.addWidget(self.page_subtitle)
        header.addLayout(heading)
        header.addStretch(1)

        telemetry = QFrame()
        telemetry.setObjectName("telemetryPanel")
        telemetry_layout = QVBoxLayout(telemetry)
        telemetry_layout.setContentsMargins(10, 7, 10, 7)
        telemetry_layout.setSpacing(4)
        self._telemetry_values = {}
        self._telemetry_bars = {}
        for metric in ("CPU", "RAM", "NET"):
            metric_row = QHBoxLayout()
            metric_row.setSpacing(6)
            label = QLabel(metric)
            label.setObjectName("telemetryLabel")
            value = QLabel("—")
            value.setObjectName("telemetryValue")
            value.setMinimumWidth(64)
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            metric_row.addWidget(label)
            if metric != "NET":
                bar = QProgressBar()
                bar.setObjectName("telemetryBar")
                bar.setRange(0, 100)
                bar.setTextVisible(False)
                bar.setFixedWidth(76)
                bar.setFixedHeight(7)
                metric_row.addWidget(bar, 1)
                self._telemetry_bars[metric] = bar
            else:
                metric_row.addStretch(1)
            metric_row.addWidget(value)
            telemetry_layout.addLayout(metric_row)
            self._telemetry_values[metric] = value
        header.addWidget(telemetry)

        clock_card = QFrame()
        clock_card.setObjectName("clockCard")
        clock_layout = QVBoxLayout(clock_card)
        clock_layout.setContentsMargins(12, 6, 12, 6)
        clock_layout.setSpacing(1)
        self.clock_greeting = QLabel()
        self.clock_greeting.setObjectName("clockGreeting")
        self.clock_greeting.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_layout.addWidget(self.clock_greeting)
        self.clock = QLabel()
        self.clock.setObjectName("clock")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.clock_date = QLabel()
        self.clock_date.setObjectName("clockDate")
        self.clock_date.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_text = QVBoxLayout()
        clock_text.addWidget(self.clock)
        clock_text.addWidget(self.clock_date)
        clock_row = QHBoxLayout()
        clock_row.addLayout(clock_text)
        self.seconds_ring = SecondsRing()
        self.seconds_ring.setFixedSize(38, 38)
        clock_row.addWidget(self.seconds_ring, 0, Qt.AlignmentFlag.AlignVCenter)
        clock_layout.addLayout(clock_row)
        header.addWidget(clock_card)
        layout.addLayout(header)

        hud = QWidget()
        hud.setObjectName("hudRegion")
        hud_layout = QHBoxLayout(hud)
        hud_layout.setContentsMargins(0, 0, 0, 0)
        hud_layout.setSpacing(8)

        left_hud_widget = QWidget()
        left_hud_widget.setFixedWidth(180)
        left_hud = QVBoxLayout()
        left_hud_widget.setLayout(left_hud)
        left_hud.setSpacing(8)
        self.voice_card = QFrame()
        self.voice_card.setObjectName("widgetCard")
        voice_layout = QVBoxLayout(self.voice_card)
        voice_layout.setContentsMargins(11, 10, 11, 10)
        voice_layout.setSpacing(4)
        self.voice_title = QLabel("NEURAL LINK")
        self.voice_title.setObjectName("widgetEyebrow")
        self.voice_status = QLabel("READY")
        self.voice_status.setObjectName("widgetPrimary")
        self.voice_detail = QLabel("System online")
        self.voice_detail.setObjectName("widgetSecondary")
        voice_layout.addWidget(self.voice_title)
        voice_layout.addWidget(self.voice_status)
        voice_layout.addWidget(self.voice_detail)
        left_hud.addWidget(self.voice_card)

        input_card = QFrame()
        input_card.setObjectName("widgetCard")
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(10, 8, 10, 8)
        input_layout.setSpacing(4)
        self.input_title = QLabel("AUDIO INPUT")
        self.input_title.setObjectName("widgetEyebrow")
        self.input_spectrum = AudioSpectrumWidget(
            ACCENTS.get(self.accent_name, ACCENTS["Cyan"])
        )
        input_layout.addWidget(self.input_title)
        input_layout.addWidget(self.input_spectrum)
        left_hud.addWidget(input_card)
        left_hud.addStretch(1)
        hud_layout.addWidget(left_hud_widget)

        self.orb = ArcCore(
            ACCENTS.get(self.accent_name, ACCENTS["Cyan"]),
            self.reduced_motion,
        )
        hud_layout.addWidget(self.orb, 1)

        right_hud_widget = QWidget()
        right_hud_widget.setFixedWidth(180)
        right_hud = QVBoxLayout()
        right_hud_widget.setLayout(right_hud)
        right_hud.setSpacing(8)
        self.weather_card = QFrame()
        self.weather_card.setObjectName("widgetCard")
        weather_layout = QVBoxLayout(self.weather_card)
        weather_layout.setContentsMargins(11, 10, 11, 10)
        weather_layout.setSpacing(3)
        self.weather_title = QLabel("WEATHER")
        self.weather_title.setObjectName("widgetEyebrow")
        weather_row = QHBoxLayout()
        self.weather_icon = QLabel("☀")
        self.weather_icon.setObjectName("weatherIcon")
        self.weather_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.weather_icon.setFont(QFont("Segoe UI Symbol", 19))
        self.weather_temperature = QLabel("—")
        self.weather_temperature.setObjectName("weatherTemperature")
        self.weather_description = QLabel("Syncing location…")
        self.weather_description.setObjectName("widgetSecondary")
        self.weather_description.setWordWrap(True)
        weather_row.addWidget(self.weather_icon)
        weather_row.addWidget(self.weather_temperature)
        weather_row.addWidget(self.weather_description, 1)
        weather_layout.addWidget(self.weather_title)
        weather_layout.addLayout(weather_row)
        right_hud.addWidget(self.weather_card)

        output_card = QFrame()
        output_card.setObjectName("widgetCard")
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(10, 8, 10, 8)
        output_layout.setSpacing(4)
        self.output_title = QLabel("AUDIO OUTPUT")
        self.output_title.setObjectName("widgetEyebrowAmber")
        self.output_spectrum = AudioSpectrumWidget("#FFB547")
        output_layout.addWidget(self.output_title)
        output_layout.addWidget(self.output_spectrum)
        right_hud.addWidget(output_card)
        right_hud.addStretch(1)
        hud_layout.addWidget(right_hud_widget)

        layout.addWidget(hud, 5)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setObjectName("conversation")
        self.log.document().setMaximumBlockCount(300)
        self.log.setMinimumHeight(106)
        self.log.setMaximumHeight(230)
        self.log.setPlaceholderText("")
        self._stream_block_number: int | None = None
        self._stream_role: str | None = None
        self._last_final_stream: tuple[str, str] = ("", "")
        layout.addWidget(self.log, 2)

        entry_row = QHBoxLayout()
        self.input = _CommandInput()
        self.input.setObjectName("commandInput")
        self.input.setPlaceholderText("Ask JARVIS anything...")
        self.input.setMinimumHeight(38)
        self.input.setMaximumHeight(78)
        self.input.setTabChangesFocus(True)
        self.input.sendRequested.connect(self._submit_text)
        self.input.textChanged.connect(self._adjust_command_height)
        self._adjust_command_height()
        self.send_button = QPushButton("➤  Send")
        self.send_button.setObjectName("primaryButton")
        self.send_button.setToolTip("Send message")
        self.send_button.setMinimumWidth(104)
        self.send_button.clicked.connect(self._submit_text)
        self.send_button.pressed.connect(self._play_ui_sound)
        entry_row.addWidget(self.input, 1)
        entry_row.addWidget(self.send_button)
        layout.addLayout(entry_row)

        controls = QHBoxLayout()
        self.mic_button = QPushButton("◉   Microphone on  ·  F4")
        self.mic_button.setObjectName("quietButton")
        self.mic_button.setToolTip("Microphone on · F4")
        self.mic_button.setMinimumHeight(30)
        self.mic_button.clicked.connect(self._toggle_mute)
        self.mic_button.pressed.connect(self._play_ui_sound)
        controls.addWidget(self.mic_button)
        controls.addStretch(1)
        self.voice_attribution = QLabel("✦  MEHNATKASH GROUP")
        self.voice_attribution.setObjectName("voiceAttribution")
        controls.addWidget(self.voice_attribution)
        self.assistant_button.clicked.connect(self.input.setFocus)
        layout.addLayout(controls)

        root.addWidget(content, 1)

        self._load_weather()
        self._weather_timer = QTimer(self.window)
        self._weather_timer.timeout.connect(self._load_weather)
        self._weather_timer.start(15 * 60 * 1000)

        self._clock_timer = QTimer(self.window)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()
        self._network_sample = None
        self._telemetry_error_logged = False
        self._telemetry_timer = QTimer(self.window)
        self._telemetry_timer.timeout.connect(self._update_telemetry)
        self._telemetry_timer.start(2000)
        self._update_telemetry()

    def _apply_language_labels(self):
        lang = self._active_lang()
        if lang == "uz":
            self.brand_subtitle.setText("CE-21  ·  v2.1.1")
            self.assistant_button.setText("⌂   Yordamchi")
            self.settings_button.setText("⚙   Sozlamalar")
            self.page_title.setText("Shaxsiy intellekt")
            self.page_subtitle.setText("OVOZLI INTERFEYS  ·  QURILMA BILAN SINXRON")
            self.voice_title.setText("NEYRON ALOQA")
            self.input_title.setText("AUDIO KIRISH")
            self.output_title.setText("AUDIO CHIQISH")
            self.weather_title.setText("OB-HAVO · KUN/TUN")
            self.input.setPlaceholderText("J.A.R.V.I.S. ga buyruq yoki savol yozing...")
            self.send_button.setText("➤  Yuborish")
        elif lang == "ru":
            self.brand_subtitle.setText("CE-21  ·  v2.1.1")
            self.assistant_button.setText("⌂   Ассистент")
            self.settings_button.setText("⚙   Настройки")
            self.page_title.setText("Персональный интеллект")
            self.page_subtitle.setText("ГОЛОСОВОЙ ИНТЕРФЕЙС  ·  СИНХРОНИЗАЦИЯ")
            self.voice_title.setText("НЕЙРОСВЯЗЬ")
            self.input_title.setText("АУДИО ВХОД")
            self.output_title.setText("АУДИО ВЫХОД")
            self.weather_title.setText("ПОГОДА · ДЕНЬ/НОЧЬ")
            self.input.setPlaceholderText("Спросите J.A.R.V.I.S. о чем угодно...")
            self.send_button.setText("➤  Отправить")
        else:
            self.brand_subtitle.setText("CE-21  ·  v2.1.1")
            self.assistant_button.setText("⌂   Assistant")
            self.settings_button.setText("⚙   Settings")
            self.page_title.setText("Personal intelligence")
            self.page_subtitle.setText("VOICE INTERFACE  ·  DEVICE SYNC")
            self.voice_title.setText("NEURAL LINK")
            self.input_title.setText("AUDIO INPUT")
            self.output_title.setText("AUDIO OUTPUT")
            self.weather_title.setText("WEATHER")
            self.input.setPlaceholderText("Ask JARVIS anything...")
            self.send_button.setText("➤  Send")
        self._apply_state(self._voice_state)
        self._update_clock()

    def _adjust_command_height(self):
        line_height = self.input.fontMetrics().lineSpacing()
        lines = max(1, min(3, self.input.document().blockCount()))
        self.input.setFixedHeight(max(38, min(78, lines * line_height + 18)))

    def _update_clock(self):
        now = datetime.now().astimezone()
        hour = now.hour
        is_daytime = 6 <= hour < 19
        sky_symbol = "☀" if is_daytime else "☾"
        lang = self._active_lang()
        if lang == "uz":
            base_greeting = (
                "Xayrli tong"
                if 5 <= hour < 12
                else "Xayrli kun"
                if 12 <= hour < 17
                else "Xayrli kech"
                if 17 <= hour < 22
                else "Xayrli tun"
            )
        elif lang == "ru":
            base_greeting = (
                "Доброе утро"
                if 5 <= hour < 12
                else "Добрый день"
                if 12 <= hour < 17
                else "Добрый вечер"
                if 17 <= hour < 22
                else "Доброй ночи"
            )
        else:
            base_greeting = (
                "Good morning"
                if 5 <= hour < 12
                else "Good afternoon"
                if 12 <= hour < 17
                else "Good evening"
                if 17 <= hour < 22
                else "Good night"
            )
        if self.display_name:
            base_greeting = f"{base_greeting}, {self.display_name.split()[0]}"
        self.clock_greeting.setText(f"{sky_symbol}  {base_greeting}")
        self.clock.setText(now.strftime("%H:%M:%S"))
        offset = now.strftime("%z")
        timezone = f"UTC{offset[:3]}:{offset[3:]}" if offset else now.tzname() or "LOCAL"
        self.clock_date.setText(
            f"{now.strftime('%a · %d %b').upper()}   ·   WK {now.isocalendar().week}   ·   {timezone}"
        )
        self.seconds_ring.set_progress(now.second)

    def _update_telemetry(self):
        try:
            cpu = round(psutil.cpu_percent(interval=None))
            memory = round(psutil.virtual_memory().percent)
            counters = psutil.net_io_counters()
            now = time.monotonic()
            network_rate = None
            if self._network_sample is not None:
                previous_time, previous_sent, previous_received = self._network_sample
                elapsed = now - previous_time
                if elapsed > 0:
                    network_rate = (
                        counters.bytes_sent - previous_sent
                        + counters.bytes_recv - previous_received
                    ) / elapsed
            self._network_sample = (now, counters.bytes_sent, counters.bytes_recv)

            self._telemetry_values["CPU"].setText(f"{cpu}%")
            self._telemetry_values["RAM"].setText(f"{memory}%")
            self._telemetry_bars["CPU"].setValue(cpu)
            self._telemetry_bars["RAM"].setValue(memory)
            self._telemetry_values["NET"].setText(self._format_network_rate(network_rate))
            self._telemetry_error_logged = False
        except (OSError, RuntimeError, psutil.Error) as error:
            for value in self._telemetry_values.values():
                value.setText("—")
            for bar in self._telemetry_bars.values():
                bar.setValue(0)
            if not self._telemetry_error_logged:
                logging.getLogger(__name__).warning("System telemetry is unavailable: %s", error)
                self._telemetry_error_logged = True

    @staticmethod
    def _format_network_rate(bytes_per_second):
        if bytes_per_second is None:
            return "—"
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.0f} B/s"
        if bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f} KB/s"
        return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"

    def _load_weather(self):
        lang = self._active_lang()
        if not self.perm_location and not self.weather_city:
            self.weather_temperature.setText("—")
            if lang == "uz":
                self.weather_description.setText("Joylashuv o'chirilgan")
            elif lang == "ru":
                self.weather_description.setText("Геолокация отключена")
            else:
                self.weather_description.setText("Location sync paused")
            self.weather_icon.setText("◇")
            return
        self.weather_temperature.setText("…")
        target_label = self.weather_city or ("Avto" if lang == "uz" else ("Авто" if lang == "ru" else "Auto"))
        if lang == "uz":
            self.weather_description.setText(f"Sinxronlanmoqda ({target_label})…")
        elif lang == "ru":
            self.weather_description.setText(f"Синхронизация ({target_label})…")
        else:
            self.weather_description.setText(f"Syncing {target_label}…")
        self.weather_icon.setText("⋯")
        task = WeatherTask(self.weather_city, lang)
        task.signals.finished.connect(self._apply_weather)
        self._weather_task = task
        QThreadPool.globalInstance().start(task)

    def _apply_weather(
        self,
        requested_city: str,
        city: str,
        temperature: str,
        description: str,
        is_day: bool = True,
    ):
        if requested_city.casefold() != self.weather_city.casefold():
            return
        self.weather_temperature.setText(temperature or "—")
        if temperature:
            self.weather_description.setText(f"{city} · {description}")
            self._last_weather_summary = f"{city}: {temperature}, {description}"
        else:
            lang = self._active_lang()
            prefix = (
                "Ob-havo topilmadi"
                if lang == "uz"
                else ("Погода недоступна" if lang == "ru" else "Weather unavailable")
            )
            self.weather_description.setText(f"{prefix}: {description}")
        self.weather_icon.setText(
            self._weather_icon(description, is_day) if temperature else "◇"
        )

    @staticmethod
    def _weather_icon(description: str, is_day: bool = True) -> str:
        condition = description.casefold()
        if "thunder" in condition or "momaqaldiroq" in condition or "гроза" in condition:
            return "⚡"
        if "snow" in condition or "qor" in condition or "снег" in condition:
            return "❄"
        if (
            "rain" in condition
            or "drizzle" in condition
            or "yomg'ir" in condition
            or "jala" in condition
            or "дождь" in condition
            or "ливень" in condition
        ):
            return "☂"
        if "fog" in condition or "tuman" in condition or "туман" in condition:
            return "≋"
        if "cloud" in condition or "overcast" in condition or "bulut" in condition or "облач" in condition or "пасмур" in condition:
            return "☁" if is_day else "☾"
        return "☀" if is_day else "☾"

    def _install_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.window.windowIcon(), self.window)
        self.tray.setToolTip("J.A.R.V.I.S. CE-21 v2.1.1")
        menu = QMenu()
        open_action = QAction("Open J.A.R.V.I.S.", menu)
        open_action.triggered.connect(self._show_window)
        orb_action = QAction("Minimize to Floating Core (_)", menu)
        orb_action.triggered.connect(self._hide_to_orb)
        quit_action = QAction("Quit J.A.R.V.I.S. (✕)", menu)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(open_action)
        menu.addAction(orb_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._show_window()
            if reason == QSystemTrayIcon.ActivationReason.Trigger
            else None
        )
        self.tray.show()

    def _make_icon(self) -> QIcon:
        ico_path = Path(getattr(sys, "_MEIPASS", BASE_DIR)) / "assets" / "JARVIS.ico"
        if not ico_path.is_file():
            ico_path = BASE_DIR / "assets" / "JARVIS.ico"
        if ico_path.is_file():
            icon = QIcon(str(ico_path))
            if not icon.isNull():
                return icon
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(ACCENTS.get(self.accent_name, ACCENTS["Cyan"]))
        painter.setPen(QPen(color, 3))
        painter.setBrush(QColor("#071826"))
        painter.drawEllipse(5, 5, 54, 54)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(22, 22, 20, 20)
        painter.end()
        return QIcon(pixmap)

    def _apply_theme(self):
        accent = ACCENTS.get(self.accent_name, ACCENTS["Cyan"])
        self.window.setStyleSheet(build_stylesheet(accent))

    def _load_settings(self) -> dict:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _api_key_exists(self) -> bool:
        return bool(get_config().get("gemini_api_key"))

    def _save_settings(
        self,
        *,
        ui_language: str = "Auto (System)",
        accent_name: str,
        reduced_motion: bool,
        audio_device,
        voice_name: str,
        api_key: str,
        launch_at_startup: bool,
        matrix_enabled: bool,
        matrix_intensity: int,
        ui_sounds: bool,
        display_name: str,
        weather_city: str,
        perm_microphone: bool = True,
        perm_screen: bool = True,
        perm_system: bool = True,
        perm_location: bool = True,
        perm_self_close: bool = True,
    ):
        self.ui_language = ui_language if ui_language in UI_LANGUAGES else "Auto (System)"
        self.accent_name = accent_name if accent_name in ACCENTS else "Cyan"
        self.reduced_motion = reduced_motion
        self.audio_device = audio_device
        self.voice_name = voice_name if voice_name in VOICE_PRESETS else "Charon"
        self.launch_at_startup = launch_at_startup
        self.matrix_enabled = matrix_enabled
        self.matrix_intensity = max(0, min(100, matrix_intensity))
        self.ui_sounds = ui_sounds
        self.display_name = display_name.strip()
        self.weather_city = weather_city.strip()
        self.perm_microphone = bool(perm_microphone)
        self.perm_screen = bool(perm_screen)
        self.perm_system = bool(perm_system)
        self.perm_location = bool(perm_location)
        self.perm_self_close = bool(perm_self_close)
        self._settings = {
            "ui_language": self.ui_language,
            "accent": self.accent_name,
            "reduced_motion": self.reduced_motion,
            "audio_device": self.audio_device,
            "voice": self.voice_name,
            "launch_at_startup": self.launch_at_startup,
            "matrix_enabled": self.matrix_enabled,
            "matrix_intensity": self.matrix_intensity,
            "ui_sounds": self.ui_sounds,
            "display_name": self.display_name,
            "weather_city": self.weather_city,
            "perm_microphone": self.perm_microphone,
            "perm_screen": self.perm_screen,
            "perm_system": self.perm_system,
            "perm_location": self.perm_location,
            "perm_self_close": self.perm_self_close,
        }
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")
        if api_key:
            update_config({"gemini_api_key": api_key, "os_system": platform.system().lower()})
        if self._api_key_exists():
            self._api_ready.set()
        self._apply_theme()
        self._apply_native_backdrop()
        self._apply_language_labels()
        self.matrix.set_enabled(self.matrix_enabled)
        self.matrix.set_intensity(self.matrix_intensity)
        self.matrix.set_reduced_motion(self.reduced_motion)
        self.orb.set_appearance(ACCENTS[self.accent_name], self.reduced_motion)
        self.input_spectrum.set_accent(ACCENTS[self.accent_name])
        self._load_weather()
        self.voice_attribution.setText("✦  MEHNATKASH GROUP")
        app_icon = self._make_icon()
        self.app.setWindowIcon(app_icon)
        self.window.setWindowIcon(app_icon)
        self._configure_startup()
        lang = self._active_lang()
        if lang == "uz":
            self.write_log("SYS: Sozlamalar va ruxsatlar qurilma bilan sinxronlandi.")
        elif lang == "ru":
            self.write_log("SYS: Настройки и разрешения синхронизированы с устройством.")
        else:
            self.write_log("SYS: Settings and permissions synchronized with device.")
        if self.on_settings_changed:
            self.on_settings_changed()

    def _configure_startup(self):
        if platform.system() != "Windows":
            return
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            if self.launch_at_startup:
                if getattr(sys, "frozen", False):
                    command = f'"{Path(sys.executable).resolve()}"'
                else:
                    pythonw = Path(sys.executable).with_name("pythonw.exe")
                    script = Path(__file__).with_name("main.py").resolve()
                    command = f'"{pythonw if pythonw.exists() else sys.executable}" "{script}"'
                winreg.SetValueEx(key, "JARVIS", 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, "JARVIS")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except OSError as error:
            logging.getLogger(__name__).warning("Could not update Windows startup: %s", error)

    def open_settings(self):
        dialog = _SettingsDialog(self)
        dialog.exec()

    def _show_window(self):
        self.floating_orb.hide()
        self.window.showNormal()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        QTimer.singleShot(100, self._apply_native_backdrop)

    def _apply_native_backdrop(self):
        if self.window.isVisible():
            applied = apply_acrylic_backdrop(int(self.window.winId()), dark=True)
            if platform.system() == "Windows" and not applied:
                logging.getLogger(__name__).info(
                    "Windows did not provide a native acrylic backdrop; using translucent UI."
                )

    def _hide_to_orb(self):
        screen = self.window.screen()
        if screen is not None and not self.floating_orb.isVisible():
            area = screen.availableGeometry()
            self.floating_orb.move(
                area.right() - self.floating_orb.width() - 28,
                area.bottom() - self.floating_orb.height() - 36,
            )
        self.window.hide()
        self.floating_orb.show()
        self.floating_orb.raise_()

    def _quit_app(self):
        self._api_ready.set()
        if hasattr(self, "tray") and self.tray is not None:
            self.tray.hide()
        self.floating_orb.hide()
        self.window.hide()
        self.app.quit()

    def _toggle_mute(self):
        self.muted = not self.muted

    def _play_ui_sound(self):
        if self.ui_sounds:
            QApplication.beep()

    def _focus_notes(self):
        self.input.setFocus()

    def _open_screenshot(self):
        if not QDesktopServices.openUrl(QUrl("ms-screenclip:")):
            self.write_log("ERR: Windows screen snipping is unavailable on this system.")

    def open_command_palette(self):
        palette = QDialog(self.window)
        palette.setWindowTitle("JARVIS Command Palette")
        palette.setObjectName("commandPalette")
        palette.setFixedWidth(520)
        palette_layout = QVBoxLayout(palette)
        search = QLineEdit()
        search.setPlaceholderText("Search commands, apps, and settings…")
        search.setObjectName("paletteSearch")
        palette_layout.addWidget(search)
        results = QListWidget()
        commands = (
            ("Open settings & permissions", self.open_settings),
            ("Toggle microphone mute (F4)", self._toggle_mute),
            ("Minimize to floating core (_)", self._hide_to_orb),
            ("Focus assistant input", self._focus_notes),
            ("Take screenshot", self._open_screenshot),
            ("Toggle Matrix Rain", self._toggle_matrix),
            ("Quit JARVIS (✕)", self._quit_app),
        )
        for label, callback in commands:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, callback)
            results.addItem(item)
        palette_layout.addWidget(results)

        def filter_commands(text: str):
            term = text.casefold().strip()
            for index in range(results.count()):
                item = results.item(index)
                item.setHidden(term not in item.text().casefold())
            for index in range(results.count()):
                if not results.item(index).isHidden():
                    results.setCurrentRow(index)
                    break

        def activate_current():
            item = results.currentItem()
            if item is not None and not item.isHidden():
                callback = item.data(Qt.ItemDataRole.UserRole)
                palette.accept()
                callback()

        search.textChanged.connect(filter_commands)
        search.returnPressed.connect(activate_current)
        results.itemActivated.connect(
            lambda item: (palette.accept(), item.data(Qt.ItemDataRole.UserRole)())
        )
        palette.setStyleSheet(
            build_stylesheet(ACCENTS.get(self.accent_name, ACCENTS["Cyan"]))
        )
        palette.show()
        palette.move(self.window.frameGeometry().center() - palette.rect().center())
        search.setFocus()
        palette.exec()

    def _toggle_matrix(self):
        self.matrix_enabled = not self.matrix_enabled
        self.matrix.set_enabled(self.matrix_enabled)
        self._settings["matrix_enabled"] = self.matrix_enabled
        SETTINGS_FILE.write_text(json.dumps(self._settings, indent=2), encoding="utf-8")
        self.write_log(
            f"SYS: Matrix background {'enabled' if self.matrix_enabled else 'disabled'}."
        )

    def is_self_close_command(self, text: str) -> bool:
        if not self.perm_self_close:
            return False
        lowered = text.casefold().strip()
        return any(trigger in lowered for trigger in _SELF_CLOSE_TRIGGERS)

    def _submit_text(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self.write_log(f"You: {text}")
        if self.is_self_close_command(text):
            self.write_log("Jarvis: Xo'p bo'ladi, janob. Dastur yopilmoqda.")
            QTimer.singleShot(1200, self._quit_app)
            return
        if self.on_text_command:
            threading.Thread(
                target=self.on_text_command,
                args=(text,),
                daemon=True,
                name="JarvisTextCommand",
            ).start()

    def _role_style(self, role: str) -> tuple[str, Qt.AlignmentFlag, QColor]:
        if role == "you":
            return (
                "#e6edf3",
                Qt.AlignmentFlag.AlignRight,
                QColor(0, 205, 235, 46),
            )
        if role == "jarvis":
            return (
                ACCENTS.get(self.accent_name, ACCENTS["Cyan"]),
                Qt.AlignmentFlag.AlignLeft,
                QColor(120, 200, 220, 28),
            )
        if role == "err":
            return (
                "#ec7979",
                Qt.AlignmentFlag.AlignLeft,
                QColor(236, 121, 121, 24),
            )
        return (
            "#9ba8b5",
            Qt.AlignmentFlag.AlignLeft,
            QColor(120, 160, 185, 20),
        )

    def _insert_chat_block(self, display_text: str, role: str) -> int:
        color, alignment, bg_color = self._role_style(role)
        scrollbar = self.log.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 8
        previous_scroll = scrollbar.value()

        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        block = QTextBlockFormat()
        block.setAlignment(alignment)
        block.setBackground(bg_color)
        block.setLeftMargin(12)
        block.setRightMargin(12)
        block.setTopMargin(5)
        block.setBottomMargin(5)
        if self.log.document().characterCount() > 1:
            cursor.insertBlock(block)
        else:
            cursor.setBlockFormat(block)

        char_format = QTextCharFormat()
        char_format.setForeground(QColor(color))
        cursor.insertText(display_text, char_format)
        block_num = cursor.blockNumber()
        self.log.setTextCursor(cursor)
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(previous_scroll)
        return block_num

    def _apply_stream_log(self, role: str, text: str, is_final: bool):
        clean = text.strip()
        if not clean:
            if is_final and self._stream_role == role:
                self._stream_role = None
                self._stream_block_number = None
            return

        doc = self.log.document()
        if (
            self._stream_role == role
            and self._stream_block_number is not None
            and 0 <= self._stream_block_number < doc.blockCount()
        ):
            scrollbar = self.log.verticalScrollBar()
            was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 8
            previous_scroll = scrollbar.value()

            target_block = doc.findBlockByNumber(self._stream_block_number)
            cursor = QTextCursor(target_block)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            color, _, _ = self._role_style(role)
            char_format = QTextCharFormat()
            char_format.setForeground(QColor(color))
            cursor.insertText(clean, char_format)
            if was_at_bottom:
                scrollbar.setValue(scrollbar.maximum())
            else:
                scrollbar.setValue(previous_scroll)
        else:
            self._stream_role = role
            self._stream_block_number = self._insert_chat_block(clean, role)

        if is_final:
            self._last_final_stream = (role, clean)
            self._stream_role = None
            self._stream_block_number = None

    def _append_log(self, text: str):
        raw = text.strip()
        if not raw:
            return
        lowered = raw.lower()
        if lowered.startswith("you:"):
            role = "you"
            display = raw.split(":", 1)[1].strip()
        elif lowered.startswith(("jarvis:", "ai:")):
            role = "jarvis"
            display = raw.split(":", 1)[1].strip()
        elif lowered.startswith(("err:", "error:")) or "failed" in lowered:
            role = "err"
            display = raw
        else:
            role = "sys"
            display = raw

        if role in {"you", "jarvis"}:
            if self._stream_role == role:
                self._apply_stream_log(role, display, is_final=True)
            elif self._last_final_stream == (role, display):
                self._last_final_stream = ("", "")
            else:
                self._insert_chat_block(display, role)
        else:
            self._insert_chat_block(display, role)

        if role == "you":
            self.set_state("PROCESSING")
        elif role == "jarvis":
            self.set_state("SPEAKING")

    def _type_next_message(self):
        pass

    def _apply_state(self, state: str):
        normalized = state.upper()
        if normalized == "ONLINE":
            normalized = "IDLE"
        self.orb.set_state(normalized)
        self.floating_orb.set_state(normalized)
        lang = self._active_lang()
        if lang == "uz":
            labels = {
                "IDLE": ("TAYYOR", "Tizim onlayn", "●  TAYYOR"),
                "CONNECTING": ("ULANMOQDA", "Aloqa o'rnatilmoqda", "●  ULANMOQDA"),
                "LISTENING": ("ONLAYN", "Ovoz tizimi faol", "●  ONLAYN"),
                "MUTED": ("MIK O'CHIQ", "Kirish pauzada · F4 yoqish", "●  O'CHIQ"),
                "THINKING": ("BAJARILMOQDA", "JARVIS ishlamoqda", "●  BAJARILMOQDA"),
                "PROCESSING": ("BAJARILMOQDA", "JARVIS ishlamoqda", "●  BAJARILMOQDA"),
                "SPEAKING": ("OVOZ FAOL", "JARVIS gapirmoqda", "●  GAPIRMOQDA"),
                "ERROR": ("ALOQA XATOSI", "Internet va sozlamani tekshiring", "●  XATO"),
            }
            sys_status_label = "TIZIM HOLATI"
        elif lang == "ru":
            labels = {
                "IDLE": ("ГОТОВ", "Система онлайн", "●  ГОТОВ"),
                "CONNECTING": ("ПОДКЛЮЧЕНИЕ", "Установка связи", "●  ПОДКЛЮЧЕНИЕ"),
                "LISTENING": ("ОНЛАЙН", "Голосовая система активна", "●  ОНЛАЙН"),
                "MUTED": ("МИК ВЫКЛ", "Ввод на паузе · F4 вкл", "●  ВЫКЛ"),
                "THINKING": ("ОБРАБОТКА", "JARVIS работает", "●  ОБРАБОТКА"),
                "PROCESSING": ("ОБРАБОТКА", "JARVIS работает", "●  ОБРАБОТКА"),
                "SPEAKING": ("ВЫВОД АКТИВЕН", "JARVIS говорит", "●  ГОВОРИТ"),
                "ERROR": ("ОШИБКА СВЯЗИ", "Проверьте сеть и настройки", "●  ОШИБКА"),
            }
            sys_status_label = "СТАТУС СИСТЕМЫ"
        else:
            labels = {
                "IDLE": ("READY", "System online", "●  READY"),
                "CONNECTING": ("CONNECTING", "Establishing link", "●  CONNECTING"),
                "LISTENING": ("ONLINE", "Voice system active", "●  ONLINE"),
                "MUTED": ("MIC MUTED", "Input paused · F4 to resume", "●  MUTED"),
                "THINKING": ("PROCESSING", "JARVIS is working", "●  PROCESSING"),
                "PROCESSING": ("PROCESSING", "JARVIS is working", "●  PROCESSING"),
                "SPEAKING": ("OUTPUT ACTIVE", "JARVIS is speaking", "●  SPEAKING"),
                "ERROR": ("LINK ERROR", "Check connection and settings", "●  ERROR"),
            }
            sys_status_label = "SYSTEM STATUS"

        neural, detail, sidebar = labels.get(
            normalized, labels["IDLE"]
        )
        self.voice_status.setText(neural)
        self.voice_detail.setText(detail)
        self.online_status.setText(f"{sidebar}\n   {sys_status_label}")
        self.online_status.setProperty("state", normalized)
        self.online_status.style().unpolish(self.online_status)
        self.online_status.style().polish(self.online_status)
        muted = self.muted
        if lang == "uz":
            mic_text = "◉   Mikrofon o'chiq  ·  F4" if muted else "◉   Mikrofon yoqiq  ·  F4"
        elif lang == "ru":
            mic_text = "◉   Микрофон выкл  ·  F4" if muted else "◉   Микрофон вкл  ·  F4"
        else:
            mic_text = "◉   Microphone muted  ·  F4" if muted else "◉   Microphone on  ·  F4"
        self.mic_button.setText(mic_text)
        self.mic_button.setToolTip(mic_text)
        self.mic_button.setProperty("muted", muted)
        self.mic_button.style().unpolish(self.mic_button)
        self.mic_button.style().polish(self.mic_button)
        self.input_spectrum.set_active(
            normalized in {"LISTENING", "THINKING", "PROCESSING", "IDLE"} and not muted
        )
        self.output_spectrum.set_active(normalized == "SPEAKING")

    def set_audio_levels(self, levels, channel="input"):
        self._signals.audio_levels.emit(levels, channel)

    def _apply_audio_levels(self, levels, channel):
        self.orb.set_audio_levels(levels)
        self.matrix.set_audio_levels(levels)
        self.floating_orb.set_audio_levels(levels)
        if channel == "input":
            self.input_spectrum.set_levels(levels)
        elif channel == "output":
            self.output_spectrum.set_levels(levels)

    def stream_transcript(self, role: str, text: str, is_final: bool = False):
        self._signals.stream.emit(str(role), str(text), bool(is_final))

    def write_log(self, text: str):
        self._signals.log.emit(str(text))

    def set_state(self, state: str):
        normalized = str(state).upper()
        if normalized != "MUTED":
            self._voice_state = normalized
        if self.muted and normalized == "LISTENING":
            normalized = "MUTED"
        self._signals.state.emit(normalized)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        self.set_state("MUTED" if self.muted else "LISTENING")

    def wait_for_api_key(self):
        self._api_ready.wait()

    def request_quit(self):
        self._signals.quit.emit()

    def shutdown(self):
        self._signals.quit.emit()

    def run(self):
        self._show_window()
        return self.app.exec()
