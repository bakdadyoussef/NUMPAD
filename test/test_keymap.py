import pytest
pytest.importorskip("PySide6")
from core.controller import DEFAULT_KEYMAP, DIRECTIONS


def test_default_map_has_eight_directions():
    actions = set(DEFAULT_KEYMAP.values())
    assert all(action in actions for action in DIRECTIONS)


def test_numpad_keys_are_named_physically():
    assert DEFAULT_KEYMAP["KP_8"] == "move_up"
    assert DEFAULT_KEYMAP["KP_0"] == "left_button_hold"
