from __future__ import annotations
import os
import sys
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QFormLayout, QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QSystemTrayIcon, QMenu, QMessageBox, QLineEdit, QGroupBox,
    QStatusBar, QFileDialog, QInputDialog, QSlider, QStyle)
from core.controller import DEFAULT_KEYMAP
from services.startup_manager import set_launch_at_login

ACTION_OPTIONS = [
    "unassigned", "move_up", "move_down", "move_left", "move_right", "move_up_left", "move_up_right",
    "move_down_left", "move_down_right", "stop", "left_click", "right_click", "middle_click",
    "double_click_left", "left_button_hold", "right_button_hold", "middle_button_hold",
    "scroll_up", "scroll_down", "scroll_left", "scroll_right", "precision", "speed_boost"
]

class MainWindow(QMainWindow):
    exit_requested = Signal()

    def __init__(self, config, controller, backend):
        super().__init__()
        self.config = config
        self.controller = controller
        self.backend = backend
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        self._capture_row = None
        self._key_rows = list(DEFAULT_KEYMAP.keys())
        self.setWindowTitle("NumPad Mouse Control")
        self.resize(900, 650)
        self.setMinimumSize(760, 540)
        self.setStyleSheet(self._stylesheet())
        self._build_ui()
        self._build_tray()
        self.controller.state_changed.connect(self._refresh_state)
        self.controller.key_captured.connect(self._finish_key_capture)
        self.controller.stats_changed.connect(self._refresh_stats)
        self._refresh_state(self.controller.enabled)
        if self.config.last_error:
            self.show_status(self.config.last_error)

    def _stylesheet(self):
        return """
        QMainWindow, QWidget { background: #15191d; color: #e9edf0; font-size: 10pt; }
        QTabWidget::pane { border: 1px solid #343d43; border-radius: 8px; }
        QTabBar::tab { background: #20272c; padding: 10px 15px; margin: 2px; border-radius: 5px; }
        QTabBar::tab:selected { background: #155b3a; }
        QPushButton { background: #263139; border: 1px solid #3b474f; border-radius: 6px; padding: 8px 12px; }
        QPushButton:hover { background: #34434a; }
        QPushButton:disabled { color: #778087; }
        QPushButton#primary { background: #155b3a; border-color: #24734e; font-weight: bold; }
        QPushButton#danger { background: #7b2929; border-color: #9a3939; font-weight: bold; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget { background: #20272c; border: 1px solid #3b474f; border-radius: 4px; padding: 5px; }
        QComboBox QAbstractItemView { background: #20272c; selection-background-color: #155b3a; }
        QGroupBox { border: 1px solid #343d43; border-radius: 7px; margin-top: 12px; padding: 12px; font-weight: bold; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QStatusBar { background: #101417; color: #b8c2c8; }
        QHeaderView::section { background: #263139; padding: 6px; border: none; }
        QCheckBox { spacing: 8px; }
        QLabel#muted { color: #a6b1b8; }
        """

    def _build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        header = QHBoxLayout()
        title = QLabel("⌖  NumPad Mouse")
        title.setStyleSheet("font-size: 22pt; font-weight: 700; color: #f2f5f6;")
        subtitle = QLabel("Configurable keyboard-to-mouse controller")
        subtitle.setObjectName("muted")
        title_col = QVBoxLayout(); title_col.addWidget(title); title_col.addWidget(subtitle)
        header.addLayout(title_col); header.addStretch()
        self.state_label = QLabel("INACTIVE")
        self.state_label.setStyleSheet("background:#30383e; padding:8px 12px; border-radius:6px; font-weight:bold;")
        header.addWidget(self.state_label)
        outer.addLayout(header)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._dashboard_page(), "Dashboard")
        self.tabs.addTab(self._movement_page(), "Movement")
        self.tabs.addTab(self._buttons_page(), "Mouse buttons")
        self.tabs.addTab(self._scroll_page(), "Scrolling")
        self.tabs.addTab(self._keymap_page(), "Keymap editor")
        self.tabs.addTab(self._profiles_page(), "Profiles")
        self.tabs.addTab(self._background_page(), "Background")
        self.tabs.addTab(self._diagnostics_page(), "Diagnostics")
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self.show_status("Ready. Mouse mode is disabled by default.")

    def _dashboard_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        intro = QLabel("Use the numeric keypad to move, click, drag, and scroll. Mouse mode is disabled until you enable it.")
        intro.setWordWrap(True); intro.setObjectName("muted"); layout.addWidget(intro)
        group = QGroupBox("Quick controls"); g = QVBoxLayout(group)
        row = QHBoxLayout()
        self.toggle_button = QPushButton("Enable mouse mode (F8)"); self.toggle_button.setObjectName("primary")
        self.toggle_button.clicked.connect(lambda: self.controller.set_enabled(not self.controller.enabled))
        emergency = QPushButton("Emergency stop (configurable)"); emergency.setObjectName("danger"); emergency.clicked.connect(self.controller.emergency_stop)
        row.addWidget(self.toggle_button); row.addWidget(emergency); g.addLayout(row)
        self.profile_summary = QLabel("Profile: Balanced"); g.addWidget(self.profile_summary)
        self.hook_summary = QLabel("Keyboard hook: checking…"); g.addWidget(self.hook_summary)
        layout.addWidget(group)
        pad_group = QGroupBox("Default keypad layout"); grid = QVBoxLayout(pad_group)
        grid.addWidget(QLabel("7 ↖     8 ↑     9 ↗       / Right click       * Middle click       − Scroll down"))
        grid.addWidget(QLabel("4 ←     5 STOP  6 →       0 Hold left button   . Left click     + Scroll up"))
        grid.addWidget(QLabel("1 ↙     2 ↓     3 ↘"))
        layout.addWidget(pad_group)
        note = QLabel("Emergency stop disables mouse mode and restores keypad input. Keep this window or the tray menu accessible while testing.")
        note.setWordWrap(True); note.setObjectName("muted"); layout.addWidget(note)
        layout.addStretch()
        return page

    def _movement_page(self):
        page = QWidget(); form = QFormLayout(page)
        movement = self.config.data["movement"]
        self.base_speed = QDoubleSpinBox(); self.base_speed.setRange(1, 5000); self.base_speed.setDecimals(0); self.base_speed.setSuffix(" px/s"); self.base_speed.setValue(movement["base_speed"])
        self.max_speed = QDoubleSpinBox(); self.max_speed.setRange(1, 10000); self.max_speed.setDecimals(0); self.max_speed.setSuffix(" px/s"); self.max_speed.setValue(movement["maximum_speed"])
        self.acceleration = QDoubleSpinBox(); self.acceleration.setRange(0, 10); self.acceleration.setSingleStep(.1); self.acceleration.setValue(movement["acceleration"])
        self.update_interval = QSpinBox(); self.update_interval.setRange(4, 100); self.update_interval.setSuffix(" ms"); self.update_interval.setValue(movement["update_interval_ms"])
        self.repeat_delay = QSpinBox(); self.repeat_delay.setRange(0, 2000); self.repeat_delay.setSuffix(" ms"); self.repeat_delay.setValue(movement["repeat_delay_ms"])
        self.precision_multiplier = QDoubleSpinBox(); self.precision_multiplier.setRange(.05, 1); self.precision_multiplier.setSingleStep(.05); self.precision_multiplier.setValue(movement["precision_multiplier"])
        self.diagonal = QCheckBox("Normalize diagonal movement"); self.diagonal.setChecked(movement["diagonal_normalization"])
        form.addRow("Initial movement speed", self.base_speed); form.addRow("Maximum movement speed", self.max_speed)
        form.addRow("Acceleration", self.acceleration); form.addRow("Update interval target", self.update_interval)
        form.addRow("Acceleration delay / repeat delay", self.repeat_delay); form.addRow("Precision speed multiplier", self.precision_multiplier); form.addRow("", self.diagonal)
        save = QPushButton("Apply movement settings"); save.setObjectName("primary"); save.clicked.connect(self._save_movement); form.addRow("", save)
        form.addRow("Tip", QLabel("Use a low base speed for precise positioning and raise maximum speed for crossing the screen quickly."))
        return page

    def _buttons_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Mouse-button actions are configurable in the Keymap Editor."))
        layout.addWidget(QLabel("Default: KP Decimal = left click; KP Divide = right click; KP Multiply = middle click; KP 0 = hold left button for dragging."))
        layout.addWidget(QLabel("Optional actions supported by the keymap: double-click, right/middle button hold, and drag lock can be added in future refinements."))
        layout.addStretch()
        return page

    def _scroll_page(self):
        page = QWidget(); form = QFormLayout(page); s = self.config.data["scrolling"]
        self.vertical_step = QSpinBox(); self.vertical_step.setRange(1, 20); self.vertical_step.setValue(s["vertical_step"])
        self.horizontal_step = QSpinBox(); self.horizontal_step.setRange(1, 20); self.horizontal_step.setValue(s.get("horizontal_step", 3))
        self.scroll_delay = QSpinBox(); self.scroll_delay.setRange(0, 2000); self.scroll_delay.setSuffix(" ms"); self.scroll_delay.setValue(s["repeat_delay_ms"])
        self.scroll_interval = QSpinBox(); self.scroll_interval.setRange(20, 1000); self.scroll_interval.setSuffix(" ms"); self.scroll_interval.setValue(s["repeat_interval_ms"])
        self.horizontal_enabled = QCheckBox("Enable horizontal scrolling"); self.horizontal_enabled.setChecked(s.get("horizontal_enabled", True))
        form.addRow("Vertical scroll amount", self.vertical_step); form.addRow("Horizontal scroll amount", self.horizontal_step)
        form.addRow("Repeat delay", self.scroll_delay); form.addRow("Repeat interval", self.scroll_interval); form.addRow("", self.horizontal_enabled)
        save = QPushButton("Apply scrolling settings"); save.setObjectName("primary"); save.clicked.connect(self._save_scrolling); form.addRow("", save)
        form.addRow("Default keys", QLabel("KP Add / Subtract = up / down. Assign scroll left / right in the keymap for horizontal scrolling."))
        return page

    def _keymap_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Choose an action for each physical keypad key. Unassigned keypad keys are still suppressed while mouse mode is active."))
        self.keymap_table = QTableWidget(len(DEFAULT_KEYMAP), 2)
        self.keymap_table.setHorizontalHeaderLabels(["Physical key", "Assigned action"])
        self.keymap_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.keymap_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.keymap_table.verticalHeader().setVisible(False)
        keymap = dict(DEFAULT_KEYMAP); keymap.update(self.controller.keymap)
        self.action_boxes = {}
        for row, key in enumerate(self._key_rows):
            item = QTableWidgetItem(key); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable); self.keymap_table.setItem(row, 0, item)
            combo = QComboBox(); combo.addItems(ACTION_OPTIONS); current = keymap.get(key, "unassigned")
            if current not in ACTION_OPTIONS: current = "unassigned"
            combo.setCurrentText(current); self.keymap_table.setCellWidget(row, 1, combo); self.action_boxes[key] = combo
        layout.addWidget(self.keymap_table, 1)
        buttons = QHBoxLayout()
        capture = QPushButton("Capture key for selected row"); capture.clicked.connect(self._begin_key_capture)
        cancel_capture = QPushButton("Cancel capture"); cancel_capture.clicked.connect(self._cancel_key_capture)
        apply = QPushButton("Apply keymap"); apply.setObjectName("primary"); apply.clicked.connect(self._apply_keymap)
        reset = QPushButton("Restore default map"); reset.clicked.connect(self._reset_keymap)
        buttons.addWidget(capture); buttons.addWidget(cancel_capture); buttons.addWidget(apply); buttons.addWidget(reset); buttons.addStretch(); layout.addLayout(buttons)
        return page

    def _profiles_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        row = QHBoxLayout(); self.profile_combo = QComboBox(); self.profile_combo.addItems(list(self.config.data.get("profiles", {}).keys()))
        active = self.config.data.get("controller", {}).get("active_profile", "Balanced"); self.profile_combo.setCurrentText(active)
        load = QPushButton("Load profile"); load.setObjectName("primary"); load.clicked.connect(self._load_profile)
        row.addWidget(self.profile_combo, 1); row.addWidget(load); layout.addLayout(row)
        create_row = QHBoxLayout(); self.new_profile_name = QLineEdit(); self.new_profile_name.setPlaceholderText("New profile name")
        create = QPushButton("Save current settings as profile"); create.clicked.connect(self._create_profile)
        delete = QPushButton("Delete selected custom profile"); delete.clicked.connect(self._delete_profile)
        create_row.addWidget(self.new_profile_name, 1); create_row.addWidget(create); create_row.addWidget(delete); layout.addLayout(create_row)
        layout.addWidget(QLabel("Built-in profiles: Precision, Balanced, Fast. Custom profiles are stored in your user configuration.")); layout.addStretch()
        return page

    def _background_page(self):
        page = QWidget(); form = QFormLayout(page); startup = self.config.data["startup"]
        self.minimize_tray = QCheckBox("Minimize to system tray"); self.minimize_tray.setChecked(startup.get("minimize_to_tray", True))
        self.launch_login = QCheckBox("Launch automatically when I sign in to Windows"); self.launch_login.setChecked(startup.get("launch_at_login", False))
        self.mouse_on_start = QCheckBox("Enable mouse mode automatically at startup (not recommended)"); self.mouse_on_start.setChecked(startup.get("mouse_mode_on_start", False))
        self.notifications = QCheckBox("Show status notifications"); self.notifications.setChecked(startup.get("show_notifications", True))
        form.addRow("", self.minimize_tray); form.addRow("", self.launch_login); form.addRow("", self.mouse_on_start); form.addRow("", self.notifications)
        self.activation_combo = QComboBox(); self.activation_combo.addItems(["F6", "F7", "F8", "F9", "F10", "F11"])
        self.activation_combo.setCurrentText(self.config.data.get("controller", {}).get("activation_hotkey", "F8"))
        self.emergency_combo = QComboBox(); self.emergency_combo.addItems(["CTRL+ALT+ESC", "CTRL+ALT+F10", "CTRL+ALT+F11"])
        self.emergency_combo.setCurrentText(self.config.data.get("controller", {}).get("emergency_hotkey", "CTRL+ALT+ESC"))
        form.addRow("Global activation shortcut", self.activation_combo); form.addRow("Emergency stop shortcut", self.emergency_combo)
        save = QPushButton("Apply background settings"); save.setObjectName("primary"); save.clicked.connect(self._save_background); form.addRow("", save)
        open_folder = QPushButton("Open configuration folder"); open_folder.clicked.connect(self._open_config_folder); form.addRow("", open_folder)
        note = QLabel("Automatic startup integration is a user-level setting. This build exposes the preference; see README for the startup integration status and limitations."); note.setWordWrap(True); form.addRow("Note", note)
        return page

    def _diagnostics_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.diagnostics_text = QLabel("No diagnostics yet."); self.diagnostics_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); self.diagnostics_text.setWordWrap(True)
        layout.addWidget(self.diagnostics_text)
        row = QHBoxLayout(); safe = QPushButton("Safe Mode / disable interception"); safe.setObjectName("danger"); safe.clicked.connect(self.controller.emergency_stop)
        save = QPushButton("Save configuration now"); save.clicked.connect(self._save_all)
        row.addWidget(safe); row.addWidget(save); row.addStretch(); layout.addLayout(row); layout.addStretch()
        return page

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("NumPad Mouse Control")
        self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        menu = QMenu()
        self.tray_enable_action = QAction("Enable mouse mode", self); self.tray_enable_action.triggered.connect(lambda: self.controller.set_enabled(True)); menu.addAction(self.tray_enable_action)
        self.tray_disable_action = QAction("Disable mouse mode", self); self.tray_disable_action.triggered.connect(lambda: self.controller.set_enabled(False)); menu.addAction(self.tray_disable_action)
        menu.addAction("Open settings", self.showNormal)
        menu.addAction("Emergency stop", self.controller.emergency_stop)
        menu.addSeparator(); menu.addAction("Exit", self._request_exit)
        self.tray.setContextMenu(menu)
        if self._tray_available:
            self.tray.show()
        else:
            self.show_status("System tray is not available; background hiding may not be accessible.")
        self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

    def _save_movement(self):
        m = self.config.data["movement"]
        if self.max_speed.value() < self.base_speed.value():
            self._error("Maximum speed must be greater than or equal to initial movement speed."); return
        m.update({"base_speed": self.base_speed.value(), "maximum_speed": self.max_speed.value(), "acceleration": self.acceleration.value(), "update_interval_ms": self.update_interval.value(), "repeat_delay_ms": self.repeat_delay.value(), "precision_multiplier": self.precision_multiplier.value(), "diagonal_normalization": self.diagonal.isChecked()})
        self.controller.timer.setInterval(self.update_interval.value())
        try: self.config.save(); self.show_status("Movement settings saved.")
        except Exception as exc: self._error(str(exc))

    def _save_scrolling(self):
        s = self.config.data["scrolling"]
        s.update({"vertical_step": self.vertical_step.value(), "horizontal_step": self.horizontal_step.value(), "repeat_delay_ms": self.scroll_delay.value(), "repeat_interval_ms": self.scroll_interval.value(), "horizontal_enabled": self.horizontal_enabled.isChecked()})
        try: self.config.save(); self.show_status("Scrolling settings saved.")
        except Exception as exc: self._error(str(exc))

    def _apply_keymap(self):
        mapping = {self._key_rows[row]: self.action_boxes[old_key].currentText() for row, old_key in enumerate(list(self.action_boxes.keys()))}
        assigned = [(key, action) for key, action in mapping.items() if action != "unassigned"]
        conflicts = {}
        for key, action in assigned:
            conflicts.setdefault(action, []).append(key)
        # Multiple direction keys may intentionally share actions, but duplicate stop/click/hold actions are suspicious.
        dangerous = {a: ks for a, ks in conflicts.items() if len(ks) > 1 and (a.endswith("click") or a.endswith("hold") or a == "stop")}
        if dangerous:
            answer = QMessageBox.question(self, "Duplicate actions", "Some click/hold/stop actions are assigned to multiple keys. Keep this mapping?\n\n" + "\n".join(f"{a}: {', '.join(ks)}" for a, ks in dangerous.items()))
            if answer != QMessageBox.StandardButton.Yes: return
        self.controller.set_keymap(mapping)
        try: self.config.data["keymap"] = mapping; self.config.save(); self.show_status("Keymap applied and saved.")
        except Exception as exc: self._error(str(exc))

    def _begin_key_capture(self):
        row = self.keymap_table.currentRow()
        if row < 0:
            self._error("Select a keymap row first.")
            return
        if self.controller.enabled:
            self._error("Disable mouse mode before capturing a new physical key.")
            return
        if not self.backend.available:
            self._error("The Windows keyboard hook is unavailable, so key capture cannot run.")
            return
        self._capture_row = row
        self.backend.begin_capture()
        self.show_status("Press the numeric-keypad key you want to assign to this row, or click Cancel capture.")

    def _cancel_key_capture(self):
        self.backend.cancel_capture()
        self._capture_row = None
        self.show_status("Key capture cancelled.")

    def _finish_key_capture(self, key):
        if self._capture_row is None:
            return
        row = self._capture_row
        self._capture_row = None
        if key in self._key_rows and self._key_rows.index(key) != row:
            answer = QMessageBox.question(self, "Key already assigned", f"{key} is already used by another row. Replace the existing row's physical key assignment?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.show_status("Key capture cancelled; existing map preserved.")
                return
            other = self._key_rows.index(key)
            self._key_rows[other] = self._key_rows[row]
            self.keymap_table.item(other, 0).setText(self._key_rows[other])
        self._key_rows[row] = key
        self.keymap_table.item(row, 0).setText(key)
        self.show_status(f"Captured {key}. Apply the keymap to save the change.")

    def _reset_keymap(self):
        self._key_rows = list(DEFAULT_KEYMAP.keys())
        for row, key in enumerate(self._key_rows):
            self.keymap_table.item(row, 0).setText(key)
            self.action_boxes[key].setCurrentText(DEFAULT_KEYMAP[key])
        self._apply_keymap()

    def _load_profile(self):
        name = self.profile_combo.currentText()
        self.controller.set_profile(name)
        for row, key in enumerate(self._key_rows):
            old_key = list(self.action_boxes.keys())[row]
            self.action_boxes[old_key].setCurrentText(self.controller.keymap.get(key, self.controller.keymap.get(old_key, "unassigned")))
        m = self.config.data["movement"]
        self.base_speed.setValue(m["base_speed"]); self.max_speed.setValue(m["maximum_speed"])
        self.acceleration.setValue(m["acceleration"]); self.update_interval.setValue(m["update_interval_ms"])
        self.repeat_delay.setValue(m["repeat_delay_ms"]); self.precision_multiplier.setValue(m["precision_multiplier"])
        self.diagonal.setChecked(m["diagonal_normalization"])
        s = self.config.data["scrolling"]
        self.vertical_step.setValue(s["vertical_step"]); self.horizontal_step.setValue(s.get("horizontal_step", 3))
        self.scroll_delay.setValue(s["repeat_delay_ms"]); self.scroll_interval.setValue(s["repeat_interval_ms"])
        self.horizontal_enabled.setChecked(s.get("horizontal_enabled", True))
        self._refresh_state(self.controller.enabled)
        self.show_status(f"Loaded profile: {name}")

    def _create_profile(self):
        name = self.new_profile_name.text().strip()
        if not name or name in ("Precision", "Balanced", "Fast"):
            self._error("Enter a new, non-reserved profile name."); return
        self._save_movement(); self._save_scrolling(); self._apply_keymap()
        self.config.data.setdefault("profiles", {})[name] = {"movement": dict(self.config.data["movement"]), "scrolling": dict(self.config.data["scrolling"]), "keymap": dict(self.controller.keymap)}
        try:
            self.config.save()
            if self.profile_combo.findText(name) < 0: self.profile_combo.addItem(name)
            self.profile_combo.setCurrentText(name); self.new_profile_name.clear(); self.show_status(f"Saved profile: {name}")
        except Exception as exc: self._error(str(exc))

    def _delete_profile(self):
        name = self.profile_combo.currentText()
        if name in ("Precision", "Balanced", "Fast"):
            self._error("Built-in profiles cannot be deleted."); return
        if not name: return
        self.config.data.get("profiles", {}).pop(name, None)
        self.profile_combo.removeItem(self.profile_combo.currentIndex())
        if self.config.data.get("controller", {}).get("active_profile") == name:
            self.controller.set_profile("Balanced")
        try: self.config.save(); self.show_status(f"Deleted profile: {name}")
        except Exception as exc: self._error(str(exc))

    def _save_background(self):
        old_launch = bool(self.config.data["startup"].get("launch_at_login", False))
        requested_activation = self.activation_combo.currentText()
        requested_emergency = self.emergency_combo.currentText()
        if requested_activation == requested_emergency.replace("CTRL+ALT+", ""):
            self._error("Activation and emergency shortcuts must use different keys."); return
        try:
            self.backend.set_shortcuts(requested_activation, requested_emergency.replace("CTRL+ALT+", ""))
        except Exception as exc:
            self._error(str(exc)); return
        requested_launch = self.launch_login.isChecked()
        try:
            if requested_launch != old_launch:
                set_launch_at_login(requested_launch)
            self.config.data["startup"].update({"minimize_to_tray": self.minimize_tray.isChecked(), "launch_at_login": requested_launch, "mouse_mode_on_start": self.mouse_on_start.isChecked(), "show_notifications": self.notifications.isChecked()})
            self.config.data["controller"].update({"activation_hotkey": requested_activation, "emergency_hotkey": requested_emergency})
            self.config.save()
            self.show_status("Background settings saved.")
        except Exception as exc:
            self.launch_login.setChecked(old_launch)
            self._error(f"Could not apply background settings: {exc}")

    def _save_all(self):
        self._save_movement(); self._save_scrolling(); self._apply_keymap(); self._save_background()

    def _open_config_folder(self):
        path = self.config.open_directory()
        os.makedirs(path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _refresh_state(self, enabled):
        self.state_label.setText("ACTIVE — KEYPAD CAPTURED" if enabled else "INACTIVE — KEYPAD NORMAL")
        color = "#155b3a" if enabled else "#30383e"
        self.state_label.setStyleSheet(f"background:{color}; padding:8px 12px; border-radius:6px; font-weight:bold;")
        self.toggle_button.setText("Disable mouse mode" if enabled else "Enable mouse mode (F8)")
        self.tray_enable_action.setEnabled(not enabled); self.tray_disable_action.setEnabled(enabled)
        self.hook_summary.setText("Keyboard hook: installed" if self.backend.available else f"Keyboard hook: unavailable {self.backend.error or ''}")
        self.profile_summary.setText("Profile: " + self.config.data.get("controller", {}).get("active_profile", "Balanced"))

    def _refresh_stats(self, stats):
        self.diagnostics_text.setText("\n".join([
            f"Operating system: {sys.platform}", f"Backend available: {self.backend.available}",
            f"Hook error: {self.backend.error or 'None'}", f"Mouse mode active: {stats.get('enabled')}",
            f"Movement timer callbacks per second: {stats.get('ticks_per_second')}",
            f"Pressed keypad keys: {stats.get('pressed_keys')}", f"Controller-held mouse buttons: {stats.get('held_buttons')}",
            f"Configuration: {self.config.path}", f"Last configuration error: {self.config.last_error or 'None'}",
        ]))
        self._refresh_state(self.controller.enabled)

    def show_status(self, message):
        self.statusBar().showMessage(str(message), 7000)

    def show_platform_warning(self):
        self.show_status("Windows input backend unavailable on this OS. GUI and settings can still be inspected.")

    def _error(self, message):
        QMessageBox.warning(self, "NumPad Mouse Control", message)

    def _request_exit(self):
        self.exit_requested.emit()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.config.data.get("startup", {}).get("minimize_to_tray", True) and self._tray_available:
            event.ignore(); self.hide()
            if self.config.data.get("startup", {}).get("show_notifications", True):
                self.tray.showMessage("NumPad Mouse Control", "The application is still running in the system tray.", QSystemTrayIcon.MessageIcon.Information, 2500)
        else:
            answer = QMessageBox.question(self, "Exit application?", "Do you want to exit NumPad Mouse Control?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                self.exit_requested.emit(); event.accept(); QApplication.quit()
            else:
                event.ignore()
