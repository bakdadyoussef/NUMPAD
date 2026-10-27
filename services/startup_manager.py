"""Per-user Windows startup integration, without requiring administrator privileges."""
from __future__ import annotations
import os
import sys

APP_VALUE_NAME = "NumPadMouseControl"


def set_launch_at_login(enabled: bool, entry_script: str | None = None) -> None:
    if sys.platform != "win32":
        raise OSError("Windows startup integration is available only on Windows.")
    import winreg
    if getattr(sys, "frozen", False):
        command = f'"{sys.executable}"'
    else:
        script = os.path.abspath(entry_script or os.path.join(os.path.dirname(__file__), "..", "main.py"))
        command = f'"{sys.executable}" "{script}"'
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_VALUE_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_VALUE_NAME)
            except FileNotFoundError:
                pass


def is_launch_at_login_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_VALUE_NAME)
            return bool(value)
    except OSError:
        return False
