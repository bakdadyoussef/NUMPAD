from __future__ import annotations
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path

DEFAULTS = {
    "schema_version": 1,
    "startup": {"launch_at_login": False, "mouse_mode_on_start": False, "minimize_to_tray": True, "show_notifications": True},
    "controller": {"enabled": False, "num_lock_independent": True, "active_profile": "Balanced", "emergency_hotkey": "CTRL+ALT+ESC", "activation_hotkey": "F8"},
    "movement": {"base_speed": 420.0, "maximum_speed": 1500.0, "acceleration": 1.8, "repeat_delay_ms": 150, "update_interval_ms": 8, "precision_multiplier": 0.35, "diagonal_normalization": True},
    "scrolling": {"vertical_step": 3, "horizontal_step": 3, "horizontal_enabled": True, "repeat_delay_ms": 200, "repeat_interval_ms": 50},
    "keymap": {},
    "profiles": {
        "Precision": {"movement": {"base_speed": 100.0, "maximum_speed": 260.0, "acceleration": 0.25, "precision_multiplier": 0.25, "diagonal_normalization": True}, "scrolling": {"vertical_step": 1, "horizontal_step": 1, "repeat_delay_ms": 250, "repeat_interval_ms": 80}, "keymap": {}},
        "Balanced": {"movement": {"base_speed": 420.0, "maximum_speed": 1500.0, "acceleration": 1.8, "precision_multiplier": 0.35, "diagonal_normalization": True}, "scrolling": {"vertical_step": 3, "horizontal_step": 3, "repeat_delay_ms": 200, "repeat_interval_ms": 50}, "keymap": {}},
        "Fast": {"movement": {"base_speed": 700.0, "maximum_speed": 2600.0, "acceleration": 2.8, "precision_multiplier": 0.4, "diagonal_normalization": True}, "scrolling": {"vertical_step": 5, "horizontal_step": 5, "repeat_delay_ms": 120, "repeat_interval_ms": 35}, "keymap": {}}
    }
}


def deep_merge(base, override):
    result = deepcopy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ConfigManager:
    def __init__(self, directory: str | os.PathLike):
        self.directory = Path(directory)
        self.path = self.directory / "config.json"
        self.backup_path = self.directory / "config.json.bak"
        self.data = deepcopy(DEFAULTS)
        self.last_error = ""

    def load(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.data = deepcopy(DEFAULTS)
            self.save()
            return self.data
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("Configuration root must be a JSON object")
            self.data = deep_merge(DEFAULTS, loaded)
            self.validate(self.data)
        except Exception as exc:
            self.last_error = str(exc)
            try:
                loaded = json.loads(self.backup_path.read_text(encoding="utf-8"))
                self.data = deep_merge(DEFAULTS, loaded)
                self.validate(self.data)
            except Exception:
                self.data = deepcopy(DEFAULTS)
            self.last_error = f"Configuration could not be loaded safely: {exc}. Safe defaults are active."
        return self.data

    def validate(self, data=None):
        data = self.data if data is None else data
        movement = data.get("movement", {})
        ranges = {"base_speed": (1, 5000), "maximum_speed": (1, 10000), "acceleration": (0, 10), "repeat_delay_ms": (0, 2000), "update_interval_ms": (4, 100), "precision_multiplier": (0.05, 1.0)}
        for name, (low, high) in ranges.items():
            value = movement.get(name, DEFAULTS["movement"].get(name))
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError(f"movement.{name} must be between {low} and {high}")
        scrolling = data.get("scrolling", {})
        for name, low, high in (("vertical_step", 1, 20), ("horizontal_step", 1, 20), ("repeat_delay_ms", 0, 2000), ("repeat_interval_ms", 20, 1000)):
            value = scrolling.get(name, DEFAULTS["scrolling"].get(name))
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError(f"scrolling.{name} must be between {low} and {high}")
        if movement.get("maximum_speed", 1) < movement.get("base_speed", 1):
            raise ValueError("movement.maximum_speed must be greater than or equal to movement.base_speed")
        controller = data.get("controller", {})
        if not isinstance(controller, dict):
            raise ValueError("controller must be an object")
        if controller.get("activation_hotkey", "F8") not in {"F6", "F7", "F8", "F9", "F10", "F11"}:
            raise ValueError("controller.activation_hotkey must be F6, F7, F8, F9, F10, or F11")
        if controller.get("emergency_hotkey", "CTRL+ALT+ESC") not in {"CTRL+ALT+ESC", "CTRL+ALT+F10", "CTRL+ALT+F11"}:
            raise ValueError("controller.emergency_hotkey must be CTRL+ALT+ESC, CTRL+ALT+F10, or CTRL+ALT+F11")
        if controller.get("activation_hotkey", "F8") == controller.get("emergency_hotkey", "CTRL+ALT+ESC").replace("CTRL+ALT+", ""):
            raise ValueError("Activation and emergency shortcuts must use different keys")
        if not isinstance(data.get("profiles"), dict):
            raise ValueError("profiles must be an object")
        if not isinstance(data.get("keymap"), dict):
            raise ValueError("keymap must be an object")
        valid_keys = {"KP_0", "KP_1", "KP_2", "KP_3", "KP_4", "KP_5", "KP_6", "KP_7", "KP_8", "KP_9", "KP_DECIMAL", "KP_DIVIDE", "KP_MULTIPLY", "KP_ADD", "KP_SUBTRACT", "KP_ENTER"}
        valid_actions = {"unassigned", "move_up", "move_down", "move_left", "move_right", "move_up_left", "move_up_right", "move_down_left", "move_down_right", "stop", "left_click", "right_click", "middle_click", "double_click_left", "left_button_hold", "right_button_hold", "middle_button_hold", "scroll_up", "scroll_down", "scroll_left", "scroll_right", "precision", "speed_boost"}
        for key, action in data.get("keymap", {}).items():
            if key not in valid_keys or action not in valid_actions:
                raise ValueError(f"Unsupported keymap entry: {key!r} -> {action!r}")
        for profile_name, profile in data["profiles"].items():
            if not isinstance(profile, dict):
                raise ValueError(f"Profile {profile_name!r} must be an object")
            for section in ("movement", "scrolling", "keymap"):
                if section in profile and not isinstance(profile[section], dict):
                    raise ValueError(f"Profile {profile_name!r} section {section!r} must be an object")
            for key, action in profile.get("keymap", {}).items():
                if key not in valid_keys or action not in valid_actions:
                    raise ValueError(f"Unsupported keymap entry in profile {profile_name!r}: {key!r} -> {action!r}")
        return True

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.validate(self.data)
        payload = json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"
        fd, temp_name = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=str(self.directory))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if self.path.exists():
                try:
                    self.backup_path.write_bytes(self.path.read_bytes())
                except OSError:
                    pass
            os.replace(temp_name, self.path)
        finally:
            try:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            except OSError:
                pass

    def open_directory(self):
        return str(self.directory)
