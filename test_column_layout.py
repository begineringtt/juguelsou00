from openpyxl.utils import get_column_letter

from generator import _compute_column_layout, _infer_active_keys
import column_settings


def _letters(layout, key):
    start, end, _label = layout[key]
    return get_column_letter(start), get_column_letter(end)


def test_all_builtin_columns_enabled():
    columns = column_settings.DEFAULT_COLUMNS
    active = {"spec", "unit", "qty", "price"}
    layout = _compute_column_layout(columns, active)
    assert _letters(layout, "name") == ("B", "H")
    assert _letters(layout, "spec") == ("I", "N")
    assert _letters(layout, "unit") == ("O", "O")
    assert _letters(layout, "qty") == ("P", "P")
    assert _letters(layout, "price") == ("Q", "T")
    assert _letters(layout, "supply") == ("U", "X")
    assert _letters(layout, "vat") == ("Y", "AB")
    print("OK: test_all_builtin_columns_enabled")


def test_unit_and_qty_are_always_single_column():
    columns = column_settings.DEFAULT_COLUMNS
    active = {"spec", "unit", "qty", "price"}
    layout = _compute_column_layout(columns, active)
    assert layout["unit"][1] - layout["unit"][0] == 0
    assert layout["qty"][1] - layout["qty"][0] == 0
    print("OK: test_unit_and_qty_are_always_single_column")


def test_spec_dropped_fills_27_columns():
    columns = column_settings.DEFAULT_COLUMNS
    active = {"unit", "qty", "price"}  # spec 미사용
    layout = _compute_column_layout(columns, active)
    assert "spec" not in layout
    assert set(layout.keys()) == {"name", "unit", "qty", "price", "supply", "vat"}
    ranges = sorted((v[0], v[1]) for v in layout.values())
    assert ranges[0][0] == 2
    assert ranges[-1][1] == 28
    for i in range(len(ranges) - 1):
        assert ranges[i][1] + 1 == ranges[i + 1][0]
    print("OK: test_spec_dropped_fills_27_columns")


def test_all_optional_columns_dropped():
    columns = column_settings.DEFAULT_COLUMNS
    layout = _compute_column_layout(columns, set())
    assert set(layout.keys()) == {"name", "supply", "vat"}
    assert _letters(layout, "name") == ("B", "N")
    assert _letters(layout, "supply") == ("O", "U")
    assert _letters(layout, "vat") == ("V", "AB")
    print("OK: test_all_optional_columns_dropped")


def test_custom_column_defaults_to_single_column_and_takes_configured_order():
    columns = column_settings.DEFAULT_COLUMNS + [
        {"key": "custom_1", "label": "중량", "enabled": True, "builtin": False}
    ]
    active = {"spec", "unit", "qty", "price", "custom_1"}
    layout = _compute_column_layout(columns, active)
    assert layout["custom_1"][1] - layout["custom_1"][0] == 0
    # 설정 순서(규격,단위,수량,단가,중량) 그대로 열 순서에 반영됨
    assert layout["price"][1] < layout["custom_1"][0]
    assert layout["custom_1"][1] < layout["supply"][0]
    print("OK: test_custom_column_defaults_to_single_column_and_takes_configured_order")


def test_infer_active_keys_only_counts_keys_present_in_items():
    items = [{"name": "a", "spec": "x", "qty": 1, "price": 100}]
    active = _infer_active_keys(items, {"spec", "unit", "qty", "price"})
    assert active == {"spec", "qty", "price"}
    print("OK: test_infer_active_keys_only_counts_keys_present_in_items")


if __name__ == "__main__":
    test_all_builtin_columns_enabled()
    test_unit_and_qty_are_always_single_column()
    test_spec_dropped_fills_27_columns()
    test_all_optional_columns_dropped()
    test_custom_column_defaults_to_single_column_and_takes_configured_order()
    test_infer_active_keys_only_counts_keys_present_in_items()
    print("ALL PASSED")
