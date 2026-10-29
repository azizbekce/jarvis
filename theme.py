from __future__ import annotations


def build_stylesheet(
    accent: str,
    body_font: str = "Syne",
    display_font: str = "TS Block Bold",
    heading_font: str = "Syne ExtraBold",
) -> str:
    return f"""
        QWidget {{ color: #eafaff; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 9.5pt; font-weight: 500; }}
        QMainWindow {{ background: transparent; }}
        #content {{ background: rgba(3, 14, 25, 52); border: 1px solid rgba(0, 213, 255, 115);
            border-radius: 13px; }}
        #rail {{ background: rgba(3, 15, 27, 76); border-right: 1px solid rgba(0, 213, 255, 108); }}
        #brand {{ color: #effdff; font-family: '{display_font}', 'TS Block', '{body_font}', sans-serif;
            font-size: 12.5pt; font-weight: 700; letter-spacing: 1.2px; }}
        #brandSubtitle {{ color: {accent}; font-family: '{body_font}', 'Segoe UI', sans-serif;
            font-size: 6.5pt; font-weight: 700; letter-spacing: 2px; text-transform: uppercase; }}
        #brandDivider {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {accent}, stop:0.65 rgba(0, 213, 255, 90), stop:1 rgba(0, 213, 255, 0));
            border: 0; max-height: 1px; min-height: 1px; }}
        #credit {{ color: #61a3b4; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7pt;
            font-weight: 600; letter-spacing: 1px; text-transform: uppercase; }}
        #onlineStatus {{ color: #00e9c2; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 8pt;
            font-weight: 700; letter-spacing: 1px; }}
        #onlineStatus[state="MUTED"] {{ color: #d3a75c; }}
        #onlineStatus[state="ERROR"] {{ color: #ff7185; }}
        #railButton {{ text-align: left; background: transparent; color: #9fc2d0;
            font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 9.5pt; font-weight: 600;
            border: 1px solid transparent; border-radius: 8px; padding: 8px 10px; }}
        #railButton[active="true"] {{ color: #eaffff; background: rgba(0, 205, 239, 36);
            border-color: rgba(0, 229, 255, 96); }}
        #railButton:hover {{ color: #ffffff; border-color: rgba(0, 229, 255, 125);
            background: rgba(0, 229, 255, 24); }}
        #quietButton, .quietButton {{ background: rgba(5, 25, 40, 88); color: #b7edf4;
            font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 8.5pt; font-weight: 600;
            border: 1px solid rgba(0, 207, 240, 125); border-radius: 7px; padding: 5px 12px; }}
        #quietButton[muted="true"], .quietButton[muted="true"] {{ color: #ffc46c; border-color: rgba(255, 181, 71, 160); }}
        #quietButton:hover, .quietButton:hover {{ color: #ffffff; border-color: {accent}; background: rgba(0, 229, 255, 34); }}
        #pageTitle {{ color: #e9faff; font-family: '{heading_font}', '{body_font}', sans-serif;
            font-size: 14.5pt; font-weight: 800; letter-spacing: 0.4px; }}
        #pageSubtitle {{ color: #5bc4d8; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7pt;
            font-weight: 700; letter-spacing: 1.8px; text-transform: uppercase; }}
        #clockCard {{ background: rgba(4, 22, 38, 78); border: 1px solid rgba(0, 214, 255, 130);
            border-radius: 9px; }}
        #clockGreeting {{ color: #50d8e6; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7pt;
            font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; }}
        #clock {{ color: #effdff; font-family: '{display_font}', 'TS Block', '{body_font}', sans-serif;
            font-size: 18pt; font-weight: 700; letter-spacing: 1.2px; }}
        #clockDate {{ color: #86adbc; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 6.5pt;
            font-weight: 600; letter-spacing: 0.6px; text-transform: uppercase; }}
        #telemetryPanel {{ background: rgba(3, 19, 34, 80); border: 1px solid rgba(0, 193, 230, 110);
            border-radius: 8px; }}
        #telemetryLabel {{ color: #55c5d8; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7pt;
            font-weight: 700; letter-spacing: 0.6px; min-width: 30px; }}
        #telemetryValue {{ color: #c4f6ff; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7.5pt;
            font-weight: 600; }}
        #telemetryBar {{ background: rgba(48, 96, 116, 75); border: 0; border-radius: 3px; }}
        #telemetryBar::chunk {{ background: {accent}; border-radius: 3px; }}
        #widgetCard {{ background: rgba(4, 22, 38, 78); border: 1px solid rgba(0, 190, 225, 118);
            border-radius: 9px; }}
        #widgetEyebrow {{ color: #46cfdf; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7pt;
            font-weight: 700; letter-spacing: 1.3px; text-transform: uppercase; }}
        #widgetEyebrowAmber {{ color: #ffb547; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7pt;
            font-weight: 700; letter-spacing: 1.3px; text-transform: uppercase; }}
        #widgetPrimary {{ color: #d7faff; font-family: '{display_font}', 'TS Block', '{body_font}', sans-serif;
            font-size: 7.5pt; font-weight: 700; letter-spacing: 0.4px; }}
        #widgetSecondary {{ color: #8db8c8; font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 7.5pt;
            font-weight: 500; }}
        #weatherTemperature {{ color: #f5feff; font-family: '{body_font}', 'Segoe UI', sans-serif;
            font-size: 16pt; font-weight: 700; }}
        #weatherIcon {{ color: #a9efff; font-family: 'Segoe UI Symbol', 'Segoe UI', sans-serif; font-size: 17pt; }}
        #conversation {{ background: rgba(3, 17, 30, 74); border: 1px solid rgba(0, 194, 231, 118);
            border-radius: 9px; color: #eafaff; font-family: '{body_font}', 'Segoe UI', sans-serif;
            font-size: 9.5pt; font-weight: 500; padding: 10px; selection-background-color: #14515e; }}
        #commandInput {{ background: rgba(3, 18, 32, 98); border: 1px solid rgba(0, 206, 241, 145);
            border-radius: 8px; padding: 8px 12px; color: #f3fcff;
            font-family: '{body_font}', 'Segoe UI', sans-serif; font-size: 9.5pt; font-weight: 500; }}
        #commandInput:focus {{ border-color: {accent}; }}
        QLineEdit, QComboBox {{ background: rgba(4, 20, 33, 210);
            border: 1px solid rgba(0, 206, 241, 105); border-radius: 7px; padding: 8px 10px; color: #f3fcff; }}
        QLineEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
        QPushButton {{ background: rgba(8, 29, 43, 145); border: 1px solid rgba(0, 206, 241, 110);
            border-radius: 7px; padding: 7px 12px; font-weight: 600; }}
        QPushButton:hover {{ border-color: {accent}; color: #ffffff; background: rgba(0, 229, 255, 32); }}
        QPushButton:pressed {{ background: rgba(0, 229, 255, 70); }}
        #primaryButton {{ background: rgba(0, 197, 226, 225); border: 1px solid #45edff;
            color: #041a25; font-family: '{body_font}', 'Segoe UI', sans-serif;
            font-size: 9.5pt; font-weight: 700; padding: 8px 14px; }}
        #primaryButton:hover {{ background: #8af7ff; color: #031821; }}
        QDialog {{ background: rgba(5, 19, 31, 244); }}
        QTabWidget::pane {{ border: 1px solid rgba(0, 229, 255, 85); border-radius: 8px; }}
        QTabBar::tab {{ background: rgba(9, 29, 43, 210); color: #b4cbd0; padding: 9px 14px; border: 0; font-weight: 600; }}
        QTabBar::tab:selected {{ color: {accent}; border-bottom: 2px solid {accent}; }}
        #paletteSearch {{ font-size: 12pt; font-weight: 600; padding: 14px 18px; }}
        QListWidget {{ background: rgba(3, 16, 28, 245); border: 1px solid rgba(100, 210, 255, 65);
            border-radius: 8px; outline: 0; padding: 5px; }}
        QListWidget::item {{ padding: 10px 12px; border-radius: 5px; }}
        QListWidget::item:selected, QListWidget::item:hover {{ background: rgba(100, 210, 255, 35); }}
        #mutedNote {{ color: #9cb7bf; font-size: 9pt; }}
        #voiceAttribution {{ color: #44cbe0; font-family: '{body_font}', 'Segoe UI', sans-serif;
            font-size: 7pt; font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase; }}
        QCheckBox {{ spacing: 8px; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; }}
        QScrollBar:vertical {{ background: rgba(3, 19, 34, 80); width: 8px; margin: 3px; }}
        QScrollBar::handle:vertical {{ background: rgba(0, 194, 231, 140); min-height: 24px; border-radius: 4px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """
