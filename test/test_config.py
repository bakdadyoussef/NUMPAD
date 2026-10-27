import json
from services.config_manager import ConfigManager, DEFAULTS, deep_merge


def test_deep_merge_keeps_defaults():
    merged = deep_merge(DEFAULTS, {"movement": {"base_speed": 123}})
    assert merged["movement"]["base_speed"] == 123
    assert "maximum_speed" in merged["movement"]


def test_config_round_trip(tmp_path):
    manager = ConfigManager(tmp_path)
    manager.load()
    manager.data["movement"]["base_speed"] = 333
    manager.save()
    manager2 = ConfigManager(tmp_path)
    manager2.load()
    assert manager2.data["movement"]["base_speed"] == 333


def test_invalid_movement_range_rejected(tmp_path):
    manager = ConfigManager(tmp_path)
    manager.load()
    manager.data["movement"]["base_speed"] = -1
    try:
        manager.validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid speed should be rejected")
