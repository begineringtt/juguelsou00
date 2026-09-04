import os
import shutil

import column_settings


def _use_temp_data_dir(tmp_name):
    """테스트마다 격리된 data 디렉터리를 쓰도록 경로를 바꿔치기하고 원복 함수를 반환한다."""
    original_data_dir = column_settings.DATA_DIR
    original_path = column_settings.COLUMN_SETTINGS_PATH
    temp_dir = os.path.join(os.path.dirname(__file__), tmp_name)
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)
    column_settings.DATA_DIR = temp_dir
    column_settings.COLUMN_SETTINGS_PATH = os.path.join(temp_dir, "column_settings.json")

    def _restore():
        column_settings.DATA_DIR = original_data_dir
        column_settings.COLUMN_SETTINGS_PATH = original_path
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)

    return _restore


def test_load_columns_creates_default_when_missing():
    restore = _use_temp_data_dir("_test_data_default")
    try:
        columns = column_settings.load_columns()
        assert [c["key"] for c in columns] == ["spec", "unit", "qty", "price", "weight"]
        assert all(c["builtin"] and c["enabled"] for c in columns)
        assert os.path.exists(column_settings.COLUMN_SETTINGS_PATH)
    finally:
        restore()
    print("OK: test_load_columns_creates_default_when_missing")


def test_add_custom_column_appends_and_persists():
    restore = _use_temp_data_dir("_test_data_add")
    try:
        entry = column_settings.add_custom_column("생산지")
        assert entry["label"] == "생산지"
        assert entry["builtin"] is False
        assert entry["enabled"] is True
        assert entry["key"] not in {"spec", "unit", "qty", "price", "weight"}

        reloaded = column_settings.load_columns()
        assert reloaded[-1]["key"] == entry["key"]
    finally:
        restore()
    print("OK: test_add_custom_column_appends_and_persists")


def test_add_custom_column_rejects_blank_label():
    restore = _use_temp_data_dir("_test_data_blank")
    try:
        assert column_settings.add_custom_column("   ") is None
        assert column_settings.add_custom_column("") is None
    finally:
        restore()
    print("OK: test_add_custom_column_rejects_blank_label")


def test_add_custom_column_dedupes_by_normalized_label():
    restore = _use_temp_data_dir("_test_data_dedupe")
    try:
        first = column_settings.add_custom_column("생산지")
        second = column_settings.add_custom_column("생 산지")  # 정규화하면 같은 라벨
        assert first["key"] == second["key"]
        assert len(column_settings.load_columns()) == 6  # builtin 5개 + 커스텀 1개
    finally:
        restore()
    print("OK: test_add_custom_column_dedupes_by_normalized_label")


def test_set_column_enabled_toggles_without_reordering():
    restore = _use_temp_data_dir("_test_data_enable")
    try:
        column_settings.load_columns()
        columns = column_settings.set_column_enabled("unit", False)
        by_key = {c["key"]: c for c in columns}
        assert by_key["unit"]["enabled"] is False
        assert [c["key"] for c in columns] == ["spec", "unit", "qty", "price", "weight"]
    finally:
        restore()
    print("OK: test_set_column_enabled_toggles_without_reordering")


def test_delete_column_removes_custom_but_not_builtin():
    restore = _use_temp_data_dir("_test_data_delete")
    try:
        entry = column_settings.add_custom_column("생산지")
        assert column_settings.delete_column("unit") is False  # builtin은 삭제 불가
        assert column_settings.delete_column(entry["key"]) is True
        assert entry["key"] not in {c["key"] for c in column_settings.load_columns()}
    finally:
        restore()
    print("OK: test_delete_column_removes_custom_but_not_builtin")


def test_save_columns_overwrites_order():
    restore = _use_temp_data_dir("_test_data_reorder")
    try:
        columns = column_settings.load_columns()
        reordered = list(reversed(columns))
        column_settings.save_columns(reordered)
        assert [c["key"] for c in column_settings.load_columns()] == ["weight", "price", "qty", "unit", "spec"]
    finally:
        restore()
    print("OK: test_save_columns_overwrites_order")


if __name__ == "__main__":
    test_load_columns_creates_default_when_missing()
    test_add_custom_column_appends_and_persists()
    test_add_custom_column_rejects_blank_label()
    test_add_custom_column_dedupes_by_normalized_label()
    test_set_column_enabled_toggles_without_reordering()
    test_delete_column_removes_custom_but_not_builtin()
    test_save_columns_overwrites_order()
    print("ALL PASSED")
