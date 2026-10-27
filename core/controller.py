from __future__ import annotations
import math
import sys
import time
from PySide6.QtCore import QObject, QTimer, Signal
from backends.windows import winapi

DEFAULT_KEYMAP = {
    "KP_7": "move_up_left", "KP_8": "move_up", "KP_9": "move_up_right",
    "KP_4": "move_left", "KP_5": "stop", "KP_6": "move_right",
    "KP_1": "move_down_left", "KP_2": "move_down", "KP_3": "move_down_right",
    "KP_0": "left_button_hold", "KP_DECIMAL": "left_click", "KP_DIVIDE": "right_click",
    "KP_MULTIPLY": "middle_click", "KP_ADD": "scroll_up", "KP_SUBTRACT": "scroll_down",
    "KP_ENTER": "precision"
}
DIRECTIONS = {
    "move_up": (0, -1), "move_down": (0, 1), "move_left": (-1, 0), "move_right": (1, 0),
    "move_up_left": (-1, -1), "move_up_right": (1, -1),
    "move_down_left": (-1, 1), "move_down_right": (1, 1),
}


class MouseController(QObject):
    status_message = Signal(str)
    state_changed = Signal(bool)
    stats_changed = Signal(dict)
    key_captured = Signal(str)

    def __init__(self, backend, config):
        super().__init__()
        self.backend = backend
        self.config = config
        self.enabled = False
        self.pressed: set[str] = set()
        self.held_buttons: set[str] = set()
        self._last_tick = time.monotonic()
        self._move_started: float | None = None
        self._fraction_x = 0.0
        self._fraction_y = 0.0
        self._scroll_started: dict[str, float] = {}
        self._last_scroll: dict[str, float] = {}
        self._ticks = 0
        self._last_stats = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(int(self.config.data.get("movement", {}).get("update_interval_ms", 8)))
        self.timer.timeout.connect(self.tick)
        self.keymap = dict(DEFAULT_KEYMAP)
        self._load_active_profile()

    def _load_active_profile(self):
        settings = self.config.data
        profile_name = settings.get("controller", {}).get("active_profile", "Balanced")
        profiles = settings.get("profiles", {})
        if profile_name in profiles:
            self.keymap.update(profiles[profile_name].get("keymap", {}))

    def start(self):
        self.timer.start()
        self._last_tick = time.monotonic()

    def stop(self):
        self.disable("Application shutting down")
        self.timer.stop()

    def set_enabled(self, enabled: bool):
        if enabled == self.enabled:
            return True
        if enabled:
            if not self.backend.set_active(True):
                return False
            self.enabled = True
            self.pressed.clear()
            self._move_started = None
            self._last_tick = time.monotonic()
            self.state_changed.emit(True)
            self.status_message.emit("Mouse mode enabled.")
            return True
        self.disable("Mouse mode disabled")
        return True

    def disable(self, reason: str = "Mouse mode disabled"):
        self.enabled = False
        self.backend.set_active(False)
        self.pressed.clear()
        self._move_started = None
        self._fraction_x = self._fraction_y = 0.0
        self._scroll_started.clear()
        self._last_scroll.clear()
        self._release_all_buttons()
        self.state_changed.emit(False)
        self.status_message.emit(reason)

    def emergency_stop(self):
        self.disable("Emergency stop activated; keypad input restored.")

    def set_keymap(self, keymap: dict):
        self.keymap = {key: keymap.get(key, "unassigned") for key in DEFAULT_KEYMAP}
        for key, action in keymap.items():
            self.keymap[key] = action
        self.config.data.setdefault("profiles", {}).setdefault("Custom", {})["keymap"] = dict(self.keymap)
        self.config.data.setdefault("controller", {})["active_profile"] = "Custom"

    def set_profile(self, name: str):
        profiles = self.config.data.get("profiles", {})
        if name not in profiles:
            return
        profile = profiles[name]
        self.keymap = dict(DEFAULT_KEYMAP)
        self.keymap.update(profile.get("keymap", {}))
        self.config.data.setdefault("controller", {})["active_profile"] = name
        for section in ("movement", "scrolling"):
            if isinstance(profile.get(section), dict):
                self.config.data[section].update(profile[section])
        self.config.save()

    def _release_all_buttons(self):
        for button in tuple(self.held_buttons):
            try:
                winapi.button_up(button)
            except Exception:
                pass
        self.held_buttons.clear()

    def _process_events(self):
        while True:
            try:
                event = self.backend.events.get_nowait()
            except Exception:
                break
            if event.kind == "capture":
                self.key_captured.emit(event.key)
                continue
            if event.kind == "emergency":
                self.emergency_stop()
                continue
            if event.kind == "toggle":
                self.set_enabled(not self.enabled)
                continue
            if event.kind == "down":
                if not self.enabled:
                    continue
                was_down = event.key in self.pressed
                self.pressed.add(event.key)
                if not was_down:
                    self._on_action_down(event.key, event.timestamp)
            elif event.kind == "up":
                self.pressed.discard(event.key)
                action = self.keymap.get(event.key, "unassigned")
                if action == "left_button_hold" and "left" in self.held_buttons:
                    self._release_button("left")
                if not self._direction_keys_held():
                    self._move_started = None

    def _on_action_down(self, key: str, timestamp: float):
        action = self.keymap.get(key, "unassigned")
        if action == "left_click":
            self._click("left")
        elif action == "right_click":
            self._click("right")
        elif action == "middle_click":
            self._click("middle")
        elif action == "left_button_hold":
            self._press_button("left")
        elif action == "right_button_hold":
            self._press_button("right")
        elif action == "middle_button_hold":
            self._press_button("middle")
        elif action == "double_click_left":
            self._click("left")
            QTimer.singleShot(100, lambda: self._click("left") if self.enabled else None)
        elif action in ("scroll_up", "scroll_down", "scroll_left", "scroll_right"):
            self._scroll_started[action] = timestamp
            self._last_scroll[action] = 0.0
        elif action == "stop":
            self._move_started = None
            self._fraction_x = self._fraction_y = 0.0

    def _click(self, button):
        try:
            winapi.click(button)
        except Exception as exc:
            self.status_message.emit(f"Mouse click failed: {exc}")

    def _press_button(self, button):
        if button in self.held_buttons:
            return
        try:
            winapi.button_down(button)
            self.held_buttons.add(button)
        except Exception as exc:
            self.status_message.emit(f"Mouse button press failed: {exc}")

    def _release_button(self, button):
        if button not in self.held_buttons:
            return
        try:
            winapi.button_up(button)
        except Exception as exc:
            self.status_message.emit(f"Mouse button release failed: {exc}")
        finally:
            self.held_buttons.discard(button)

    def _direction_keys_held(self):
        return any(self.keymap.get(k, "unassigned") in DIRECTIONS for k in self.pressed)

    def tick(self):
        self._process_events()
        now = time.monotonic()
        dt = min(max(now - self._last_tick, 0.0), 0.05)
        self._last_tick = now
        if self.enabled:
            self._move(dt, now)
            self._scroll(now)
        self._ticks += 1
        if now - self._last_stats >= 1.0:
            self.stats_changed.emit({"ticks_per_second": self._ticks, "enabled": self.enabled, "pressed_keys": len(self.pressed), "held_buttons": sorted(self.held_buttons)})
            self._ticks = 0
            self._last_stats = now

    def _move(self, dt: float, now: float):
        x = y = 0
        for key in self.pressed:
            dx, dy = DIRECTIONS.get(self.keymap.get(key, "unassigned"), (0, 0))
            x += dx
            y += dy
        if x == 0 and y == 0:
            self._move_started = None
            return
        if any(self.keymap.get(k, "unassigned") == "stop" for k in self.pressed):
            return
        if self._move_started is None:
            self._move_started = now
        magnitude = math.hypot(x, y)
        x /= magnitude
        y /= magnitude
        settings = self.config.data.get("movement", {})
        base = float(settings.get("base_speed", 420.0))
        maximum = float(settings.get("maximum_speed", 1500.0))
        acceleration = float(settings.get("acceleration", 1.8))
        held = max(0.0, now - self._move_started)
        acceleration_delay = max(0.0, float(settings.get("repeat_delay_ms", 150)) / 1000.0)
        acceleration_time = max(0.0, held - acceleration_delay)
        speed = min(maximum, base * (1.0 + acceleration * acceleration_time))
        if "precision" in self.pressed:
            speed *= float(settings.get("precision_multiplier", 0.35))
        if "speed_boost" in self.pressed:
            speed *= 1.75
        if settings.get("diagonal_normalization", True):
            pass  # Direction vector is already normalized above.
        self._fraction_x += x * speed * dt
        self._fraction_y += y * speed * dt
        move_x = int(self._fraction_x)
        move_y = int(self._fraction_y)
        self._fraction_x -= move_x
        self._fraction_y -= move_y
        if move_x or move_y:
            try:
                winapi.move_relative(move_x, move_y)
            except Exception as exc:
                self.status_message.emit(f"Pointer movement failed: {exc}")
                self.emergency_stop()

    def _scroll(self, now: float):
        settings = self.config.data.get("scrolling", {})
        delay = max(0.0, float(settings.get("repeat_delay_ms", 200)) / 1000.0)
        interval = max(0.02, float(settings.get("repeat_interval_ms", 50)) / 1000.0)
        step = max(1, int(settings.get("vertical_step", 3))) * winapi.WHEEL_DELTA
        horizontal_step = max(1, int(settings.get("horizontal_step", 3))) * winapi.WHEEL_DELTA
        active_actions = {self.keymap.get(k, "unassigned") for k in self.pressed}
        for action in ("scroll_up", "scroll_down", "scroll_left", "scroll_right"):
            if action in ("scroll_left", "scroll_right") and not settings.get("horizontal_enabled", True):
                continue
            if action not in active_actions:
                self._scroll_started.pop(action, None)
                self._last_scroll.pop(action, None)
                continue
            started = self._scroll_started.get(action, now)
            last = self._last_scroll.get(action, 0.0)
            if now - started < delay:
                continue
            if last and now - last < interval:
                continue
            vertical = step if action == "scroll_up" else -step if action == "scroll_down" else 0
            horizontal = horizontal_step if action == "scroll_right" else -horizontal_step if action == "scroll_left" else 0
            try:
                winapi.wheel(vertical, horizontal)
                self._last_scroll[action] = now
            except Exception as exc:
                self.status_message.emit(f"Scrolling failed: {exc}")
                self.emergency_stop()
                return
