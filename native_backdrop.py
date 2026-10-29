from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes


_logger = logging.getLogger(__name__)


class _Margins(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("state", ctypes.c_int),
        ("flags", ctypes.c_int),
        ("gradient_color", ctypes.c_uint),
        ("animation_id", ctypes.c_int),
    ]


class _WindowCompositionAttributeData(ctypes.Structure):
    _fields_ = [
        ("attribute", ctypes.c_int),
        ("data", ctypes.POINTER(_AccentPolicy)),
        ("size_of_data", ctypes.c_size_t),
    ]


def apply_acrylic_backdrop(hwnd: int, dark: bool = True) -> bool:
    """Apply Windows 11 Desktop Acrylic, falling back to legacy composition blur."""
    if os.name != "nt":
        return False

    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(_Margins),
        ]
        dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

        margins = _Margins(-1, -1, -1, -1)
        dwmapi.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd), ctypes.byref(margins))

        dark_mode = wintypes.DWORD(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            20,  # DWMWA_USE_IMMERSIVE_DARK_MODE
            ctypes.byref(dark_mode),
            ctypes.sizeof(dark_mode),
        )

        backdrop_type = wintypes.DWORD(3)  # DWMSBT_TRANSIENTWINDOW (Desktop Acrylic)
        result = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            38,  # DWMWA_SYSTEMBACKDROP_TYPE
            ctypes.byref(backdrop_type),
            ctypes.sizeof(backdrop_type),
        )
        if result == 0:
            return True
    except (AttributeError, OSError) as error:
        _logger.info("Windows DWM backdrop API is unavailable: %s", error)

    try:
        if _enable_acrylic_fallback(hwnd):
            return True
    except (AttributeError, OSError) as error:
        _logger.info("Legacy acrylic backdrop is unavailable: %s", error)

    return False


def _enable_acrylic_fallback(hwnd: int) -> bool:
    user32 = ctypes.WinDLL("user32")
    policy = _AccentPolicy(
        state=4,  # ACCENT_ENABLE_ACRYLICBLURBEHIND
        flags=2,
        gradient_color=0x42201406,  # translucent dark blue-cyan in ABGR order
        animation_id=0,
    )
    data = _WindowCompositionAttributeData(
        attribute=19,  # WCA_ACCENT_POLICY
        data=ctypes.pointer(policy),
        size_of_data=ctypes.sizeof(policy),
    )
    function = user32.SetWindowCompositionAttribute
    function.argtypes = [wintypes.HWND, ctypes.POINTER(_WindowCompositionAttributeData)]
    function.restype = wintypes.BOOL
    return bool(function(wintypes.HWND(hwnd), ctypes.byref(data)))
