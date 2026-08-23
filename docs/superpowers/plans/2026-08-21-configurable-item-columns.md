# 품목 표 열(컬럼) 사용자 설정 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 지출결의서 자동생성 앱의 품목 표에서, 사용자가 열(규격/단위/수량/단가 + 타이핑으로 추가하는 커스텀 항목)을 켜고 끄고 순서를 바꿀 수 있게 하고, 단위/수량은 항상 셀 1칸(병합 없음), 품목/규격은 더 넓게, 커스텀 항목은 PDF 업로드 시에도 자동 인식되게 만든다.

**Architecture:** `data/column_settings.json`에 열 목록(순서 있는 리스트)을 저장하는 신규 모듈 `column_settings.py`를 만들고, 이 하나의 설정을 (1) 엑셀 생성(`generator.py`) (2) PDF 자동 인식(`pdf_item_parser.py`) (3) 화면 입력 표/PDF 미리보기(`templates/index.html`) 세 곳이 모두 따르게 만든다. 품목(name)/공급가(supply)/부가세(vat)는 항상 고정(첫 칸/마지막 두 칸)이고, 나머지(규격/단위/수량/단가/커스텀)만 설정 대상이다.

**Tech Stack:** Flask, openpyxl, pdfplumber/pytesseract(기존 그대로), vanilla JS (신규 라이브러리 추가 없음, HTML5 드래그 API로 순서변경 구현)

**Spec:** `docs/superpowers/specs/2026-08-21-configurable-item-columns-design.md`

## Global Constraints

- 품목(name)은 항상 표 맨 앞, 공급가(supply)/부가세(vat)는 항상 맨 뒤 — 설정 목록에 포함되지 않음.
- 단위(unit)/수량(qty)과 모든 커스텀(비-builtin) 열은 항상 셀 1칸(병합 없음). 품목/규격/단가/공급가/부가세는 가중치 비례 분배(가중치: name=6, spec=5, price=3, supply=3, vat=3).
- builtin 열(규격/단위/수량/단가)은 끄기만 가능, 삭제 불가. 커스텀 열은 켜기/끄기/삭제/순서변경 다 가능.
- 기존 함수 시그니처에 새 파라미터를 추가할 때는 전부 **기본값을 기존 동작과 동일하게** 유지해서, 기존 테스트/호출부가 그대로 통과해야 한다 (회귀 없음).
- 새 JS 라이브러리/CDN 의존성을 추가하지 않는다 (이 앱은 전부 vanilla JS).

---

## Task 1: `column_settings.py` 모듈 — 열 설정 저장소

**Files:**
- Create: `column_settings.py`
- Test: `test_column_settings.py`

**Interfaces:**
- Consumes: `paths.app_dir()` (기존), `pdf_item_parser.normalize_header` (기존)
- Produces:
  - `load_columns() -> list[dict]` — 각 dict는 `{"key": str, "label": str, "enabled": bool, "builtin": bool}`
  - `save_columns(columns: list[dict]) -> None`
  - `add_custom_column(label: str) -> dict | None` — 성공 시 추가(또는 기존 중복 항목)된 dict, label이 빈 문자열이면 `None`
  - `set_column_enabled(key: str, enabled: bool) -> list[dict]` — 갱신된 전체 목록 반환
  - `delete_column(key: str) -> bool` — 삭제됐으면 True, builtin이거나 없는 key면 False
  - `DEFAULT_COLUMNS: list[dict]` (모듈 상수)

- [ ] **Step 1: 실패하는 테스트 작성**

`test_column_settings.py` 새로 작성:

```python
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
        assert [c["key"] for c in columns] == ["spec", "unit", "qty", "price"]
        assert all(c["builtin"] and c["enabled"] for c in columns)
        assert os.path.exists(column_settings.COLUMN_SETTINGS_PATH)
    finally:
        restore()
    print("OK: test_load_columns_creates_default_when_missing")


def test_add_custom_column_appends_and_persists():
    restore = _use_temp_data_dir("_test_data_add")
    try:
        entry = column_settings.add_custom_column("중량")
        assert entry["label"] == "중량"
        assert entry["builtin"] is False
        assert entry["enabled"] is True
        assert entry["key"] not in {"spec", "unit", "qty", "price"}

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
        first = column_settings.add_custom_column("중량")
        second = column_settings.add_custom_column("중 량")  # 정규화하면 같은 라벨
        assert first["key"] == second["key"]
        assert len(column_settings.load_columns()) == 5  # builtin 4개 + 커스텀 1개
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
        assert [c["key"] for c in columns] == ["spec", "unit", "qty", "price"]
    finally:
        restore()
    print("OK: test_set_column_enabled_toggles_without_reordering")


def test_delete_column_removes_custom_but_not_builtin():
    restore = _use_temp_data_dir("_test_data_delete")
    try:
        entry = column_settings.add_custom_column("중량")
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
        assert [c["key"] for c in column_settings.load_columns()] == ["price", "qty", "unit", "spec"]
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python test_column_settings.py`
Expected: `ModuleNotFoundError: No module named 'column_settings'`

- [ ] **Step 3: `column_settings.py` 구현**

```python
"""품목 표에 표시할 열(품명/공급가/부가세 제외) 구성을 저장하는 로컬 설정.

data/column_settings.json 에 순서가 있는 리스트로 저장한다. 리스트에 있는
순서가 화면 입력 표/엑셀 생성/PDF 인식 매칭에서 쓰는 열 순서다. 품목(name)은
항상 맨 앞, 공급가(supply)/부가세(vat)는 항상 맨 뒤 고정이라 이 목록에는
들어가지 않는다.
"""

import json
import os

from paths import app_dir
from pdf_item_parser import normalize_header

BASE_DIR = app_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")
COLUMN_SETTINGS_PATH = os.path.join(DATA_DIR, "column_settings.json")

DEFAULT_COLUMNS = [
    {"key": "spec", "label": "규격", "enabled": True, "builtin": True},
    {"key": "unit", "label": "단위", "enabled": True, "builtin": True},
    {"key": "qty", "label": "수량", "enabled": True, "builtin": True},
    {"key": "price", "label": "단가", "enabled": True, "builtin": True},
]


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path, data):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_columns():
    data = _load_json(COLUMN_SETTINGS_PATH, None)
    if data is None:
        columns = [dict(c) for c in DEFAULT_COLUMNS]
        _save_json(COLUMN_SETTINGS_PATH, {"columns": columns})
        return columns
    return data.get("columns", [])


def save_columns(columns):
    _save_json(COLUMN_SETTINGS_PATH, {"columns": columns})


def _next_custom_key(columns):
    existing = {c["key"] for c in columns}
    n = 1
    while f"custom_{n}" in existing:
        n += 1
    return f"custom_{n}"


def add_custom_column(label):
    label = (label or "").strip()
    if not label:
        return None
    columns = load_columns()
    normalized = normalize_header(label)
    for c in columns:
        if normalize_header(c["label"]) == normalized:
            return c
    entry = {"key": _next_custom_key(columns), "label": label, "enabled": True, "builtin": False}
    columns.append(entry)
    save_columns(columns)
    return entry


def set_column_enabled(key, enabled):
    columns = load_columns()
    for c in columns:
        if c["key"] == key:
            c["enabled"] = bool(enabled)
    save_columns(columns)
    return columns


def delete_column(key):
    columns = load_columns()
    remaining = [c for c in columns if not (c["key"] == key and not c.get("builtin"))]
    if len(remaining) == len(columns):
        return False
    save_columns(remaining)
    return True
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_column_settings.py`
Expected: `ALL PASSED`

- [ ] **Step 5: 커밋**

```bash
git add column_settings.py test_column_settings.py
git commit -m "feat: add column_settings module for configurable item columns"
```

---

## Task 2: `generator.py` — 동적 열 배치 + 폭 배분 규칙

**Files:**
- Modify: `generator.py`
- Modify: `test_column_layout.py` (기존 4개 테스트를 새 규칙에 맞게 다시 씀)

**Interfaces:**
- Consumes: `column_settings.load_columns()` (Task 1)
- Produces:
  - `_infer_active_keys(items, configured_keys) -> set[str]`
  - `_compute_column_layout(configured_columns, active_keys) -> dict[str, tuple[int, int, str]]` (열별 `(start_col, end_col, label)`, 1-indexed 컬럼 번호)
  - `_write_item_row(ws, row, layout, item, configured_columns)` (기존 시그니처에서 `supply_letter` 인자 제거, 내부에서 `_col_letter(layout, "supply")`로 구함)

이 Task는 `generator.py`의 `ITEM_FIELDS`/`_infer_flags` 를 완전히 대체한다. 실제 계산 결과(기본 4개 다 켜짐)는 다음과 같음을 미리 확인해뒀다: 품목 B-H(7칸), 규격 I-N(6칸), 단위 O(1칸), 수량 P(1칸), 단가 Q-T(4칸), 공급가 U-X(4칸), 부가세 Y-AB(4칸).

- [ ] **Step 1: 실패하는 테스트로 `test_column_layout.py` 전체 교체**

```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python test_column_layout.py`
Expected: `ImportError: cannot import name '_infer_active_keys' from 'generator'` (아직 옛 `_infer_flags`/`ITEM_FIELDS` 기반이라 실패)

- [ ] **Step 3: `generator.py`에서 `ITEM_FIELDS`/`_infer_flags`/`_compute_column_layout`/`_add_item_row_merges`/`_rebuild_header_row`/`_write_item_row`/`_rebuild_item_section` 교체**

`generator.py` 상단 import에 추가:

```python
import column_settings
```

`ITEM_FIELDS` 선언(라인 76-84)과 `_infer_flags`(라인 98-104), `_compute_column_layout`(라인 107-117)를 전부 지우고 아래로 교체:

```python
NAME_KEY = "name"
SUPPLY_KEY = "supply"
VAT_KEY = "vat"

FIXED_LABELS = {NAME_KEY: "품목", SUPPLY_KEY: "공급가", VAT_KEY: "부가세"}
WIDE_WEIGHTS = {NAME_KEY: 6, "spec": 5, "price": 3, SUPPLY_KEY: 3, VAT_KEY: 3}
NARROW_BUILTIN_KEYS = {"unit", "qty"}


def _is_narrow(column_def):
    """단위/수량, 그리고 모든 커스텀(비-builtin) 열은 셀 1칸(병합 없음)으로 고정한다."""
    return column_def["key"] in NARROW_BUILTIN_KEYS or not column_def.get("builtin", True)


def _infer_active_keys(items, configured_keys):
    """설정된 열 중, 실제로 값이 있는 품목이 하나라도 있는 열만 "활성"으로 본다.
    (app.py의 /generate 라우트가 이미 체크박스로 꺼진 필드는 item dict에 안 넣으므로,
    여기서는 순수하게 데이터 존재 여부만 본다 - 옛 _infer_flags와 동일한 철학.)
    """
    return {key for key in configured_keys if any(key in item for item in items)}


def _compute_column_layout(configured_columns, active_keys):
    """configured_columns: column_settings.load_columns() 형태의 순서 있는 리스트.
    active_keys: _infer_active_keys()로 구한, 실제로 채워진 열의 key 집합.

    반환값: {key: (start_col, end_col, label)} - name/supply/vat 포함, 1-indexed 컬럼 번호.
    """
    ordered = [c for c in configured_columns if c["key"] in active_keys]
    narrow_defs = [c for c in ordered if _is_narrow(c)]
    wide_defs = [c for c in ordered if not _is_narrow(c)]

    wide_keys = [NAME_KEY] + [c["key"] for c in wide_defs] + [SUPPLY_KEY, VAT_KEY]
    weights = [WIDE_WEIGHTS.get(k, 3) for k in wide_keys]
    pool = TABLE_WIDTH - len(narrow_defs)
    spans = _largest_remainder_allocation(weights, pool)
    wide_span_map = dict(zip(wide_keys, spans))

    def label_of(key):
        if key in FIXED_LABELS:
            return FIXED_LABELS[key]
        return next(c["label"] for c in configured_columns if c["key"] == key)

    layout = {}
    col = TABLE_START_COL
    span = wide_span_map[NAME_KEY]
    layout[NAME_KEY] = (col, col + span - 1, label_of(NAME_KEY))
    col += span
    for c in ordered:
        span = 1 if _is_narrow(c) else wide_span_map[c["key"]]
        layout[c["key"]] = (col, col + span - 1, label_of(c["key"]))
        col += span
    for key in (SUPPLY_KEY, VAT_KEY):
        span = wide_span_map[key]
        layout[key] = (col, col + span - 1, label_of(key))
        col += span
    return layout
```

`_write_item_row`(라인 166-201)를 아래로 교체 (규격/단위/커스텀 등 "값을 그대로 써넣기만 하면 되는" 필드를 하나의 루프로 처리하고, qty/price/supply/vat 관계는 기존 그대로 유지):

```python
def _write_item_row(ws, row, layout, item, configured_columns):
    ws.row_dimensions[row].height = ITEM_ROW_HEIGHT
    _apply_outer_frame(ws, row)
    ws[f"{_col_letter(layout, 'name')}{row}"] = item.get("name", "")

    plain_keys = [c["key"] for c in configured_columns if c["key"] in layout and c["key"] not in ("qty", "price")]
    for key in plain_keys:
        value = item.get(key)
        if value:
            ws[f"{_col_letter(layout, key)}{row}"] = value

    use_qty = "qty" in layout and item.get("qty") is not None
    use_price = "price" in layout and item.get("price") is not None
    supply_letter = _col_letter(layout, "supply")
    if use_qty:
        qty_cell = ws[f"{_col_letter(layout, 'qty')}{row}"]
        qty_cell.value = item["qty"]
        qty_cell.number_format = ACCOUNTING_NUMBER_FORMAT
    if use_price:
        price_letter = _col_letter(layout, "price")
        price_cell = ws[f"{price_letter}{row}"]
        price_cell.value = item["price"]
        price_cell.number_format = ACCOUNTING_NUMBER_FORMAT
        if use_qty:
            qty_letter = _col_letter(layout, "qty")
            ws[f"{supply_letter}{row}"] = f"={qty_letter}{row}*{price_letter}{row}"
        else:
            ws[f"{supply_letter}{row}"] = f"={price_letter}{row}"
    else:
        ws[f"{supply_letter}{row}"] = item.get("supply", 0)
    supply_cell = ws[f"{supply_letter}{row}"]
    supply_cell.number_format = ACCOUNTING_NUMBER_FORMAT
    vat_cell = ws[f"{_col_letter(layout, 'vat')}{row}"]
    vat_cell.value = f"={supply_letter}{row}/10"
    vat_cell.number_format = ACCOUNTING_NUMBER_FORMAT

    _add_item_row_merges(ws, row, layout)
    for start, end, _label in layout.values():
        _style_span(ws, row, start, end, FONT_REGULAR)
```

`_rebuild_item_section`(라인 261-326) 안의 아래 부분만 교체:

```python
    flags = _infer_flags(items)
    layout = _compute_column_layout(flags)
    supply_letter = _col_letter(layout, "supply")

    _rebuild_header_row(ws, layout)

    row = FIRST_ITEM_ROW
    for item in items:
        _write_item_row(ws, row, layout, item, supply_letter)
        row += 1
```

를

```python
    configured_columns = column_settings.load_columns()
    active_keys = _infer_active_keys(items, {c["key"] for c in configured_columns})
    layout = _compute_column_layout(configured_columns, active_keys)

    _rebuild_header_row(ws, layout)

    row = FIRST_ITEM_ROW
    for item in items:
        _write_item_row(ws, row, layout, item, configured_columns)
        row += 1
```

로 바꾼다 (`_write_item_row` 호출부만 인자가 `supply_letter` → `configured_columns`로 바뀜, 나머지 함수 본문은 그대로 유지).

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_column_layout.py`
Expected: `ALL PASSED`

- [ ] **Step 5: 회귀 확인 — 엑셀 실제 생성까지 되는지**

Run: `python test_generator.py` 와 `python test_item_table_layout.py`
Expected: 둘 다 예외 없이 끝남 (exit code 0). 만약 `test_generator.py`/`test_item_table_layout.py`가 `ITEM_FIELDS`나 `_infer_flags`를 직접 import하고 있으면, 그 부분만 `column_settings.DEFAULT_COLUMNS`/`_infer_active_keys`를 쓰도록 최소한으로 고친다 (동작 자체는 바꾸지 않음).

- [ ] **Step 6: 커밋**

```bash
git add generator.py test_column_layout.py
git commit -m "feat: make item table column layout configurable via column_settings"
```

---

## Task 3: `pdf_item_parser.py` — 커스텀 항목도 PDF에서 자동 인식

**Files:**
- Modify: `pdf_item_parser.py`
- Modify: `test_pdf_item_parser.py` (신규 테스트 추가, 기존 테스트는 그대로 유지)

**Interfaces:**
- Consumes: 없음 (이 파일은 column_settings를 모른다 — `extra_fields` dict를 호출부(app.py)가 만들어서 넘겨준다)
- Produces: `parse_pdf_items(pdf_bytes, extra_fields: dict[str, list[str]] | None = None) -> dict` — `extra_fields`는 `{"custom_1": ["중량"]}` 형태. 나머지 내부 함수들은 전부 `synonyms=None` 파라미터를 추가로 받고, `None`이면 기존 `HEADER_SYNONYMS`를 그대로 쓴다(기존 호출부/테스트 전부 무변경으로 통과).

이 Task는 함수 시그니처에 **기본값이 있는 파라미터를 추가**하는 것뿐이라, 기존 로직/기존 테스트는 전혀 안 건드린다. 모든 함수가 "합쳐진 동의어 딕셔너리"를 매개변수로 받아 쓰도록 관통시킨다.

- [ ] **Step 1: 실패하는 테스트 작성 — `test_pdf_item_parser.py`에 추가**

```python
def test_map_table_columns_recognizes_custom_synonym():
    table = [
        ["품명", "규격", "수량", "중량", "단가"],
        ["AL바", "100x5", "5", "25kg", "7400"],
    ]
    result = map_table_columns(table, synonyms={"weight": ["중량"]})
    assert result["columns"]["weight"] == [3]
    print("OK: test_map_table_columns_recognizes_custom_synonym")


def test_extract_items_from_table_passes_through_custom_column():
    table = [
        ["품명", "규격", "수량", "중량", "단가"],
        ["AL바", "100x5", "5", "25kg", "7400"],
    ]
    synonyms = {"weight": ["중량"]}
    mapping = map_table_columns(table, synonyms=synonyms)
    rows = extract_items_from_table(table, mapping, synonyms=synonyms)
    assert rows[0]["weight"] == "25kg"
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved[0]["weight"] == "25kg"
    assert resolved[0]["price"] == 7400.0
    print("OK: test_extract_items_from_table_passes_through_custom_column")


def test_parse_pdf_items_without_extra_fields_is_unaffected():
    # extra_fields를 안 넘기면(기존 호출부) 기존 동작 그대로여야 한다.
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_without_extra_fields_is_unaffected (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_test.pdf"))
    assert result["items"]
    print("OK: test_parse_pdf_items_without_extra_fields_is_unaffected")


def test_parse_pdf_items_extra_fields_does_not_break_scanned_pdf_pipeline():
    # 알루스퀘어 PDF(OCR 경로)에 extra_fields를 넘겨도 파이프라인이 깨지지 않고,
    # 기존 회귀 테스트(품명/규격 인식)와 동일하게 최소 2개 품목이 나와야 한다.
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_extra_fields_does_not_break_scanned_pdf_pipeline (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_알루스퀘어.pdf"), extra_fields={"weight": ["중량"]})
    assert len(result["items"]) == 2
    for item in result["items"]:
        assert "AL" in item["name"]
    print("OK: test_parse_pdf_items_extra_fields_does_not_break_scanned_pdf_pipeline")
```

`__main__` 블록에도 위 4개 함수 호출을 추가한다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python test_pdf_item_parser.py`
Expected: `TypeError: map_table_columns() got an unexpected keyword argument 'synonyms'`

- [ ] **Step 3: `pdf_item_parser.py`에 `synonyms` 파라미터 관통**

아래 함수들을 각각 이렇게 바꾼다 (전부 "새 파라미터 추가 + 기본값이면 `HEADER_SYNONYMS` 사용"이라 로직 자체는 그대로):

```python
def match_field(header_text, synonyms=None):
    if not header_text:
        return None
    synonyms = synonyms or HEADER_SYNONYMS
    for line in str(header_text).split("\n"):
        normalized = normalize_header(line)
        if not normalized:
            continue
        for field, syns in synonyms.items():
            for syn in syns:
                if normalize_header(syn) == normalized:
                    return field
    return None


def match_field_fuzzy(label_text, synonyms=None):
    normalized = normalize_header(label_text)
    if not normalized:
        return None
    synonyms = synonyms or HEADER_SYNONYMS
    best_field, best_len = None, 0
    for field, syns in synonyms.items():
        for syn in syns:
            syn_norm = normalize_header(syn)
            if syn_norm and syn_norm in normalized and len(syn_norm) > best_len:
                best_field, best_len = field, len(syn_norm)
    return best_field
```

```python
def find_header_row(table, max_scan=None, synonyms=None):
    best_idx, best_score = None, 0
    rows = table[:max_scan] if max_scan is not None else table
    for idx, row in enumerate(rows):
        score = sum(1 for cell in row if match_field(cell, synonyms=synonyms))
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx, best_score


def score_table(table, synonyms=None):
    if not table:
        return 0
    _, score = find_header_row(table, synonyms=synonyms)
    return score


def map_table_columns(table, synonyms=None):
    if not table:
        return None
    header_idx, _ = find_header_row(table, synonyms=synonyms)
    if header_idx is None:
        return None
    columns = {}
    for idx, cell in enumerate(table[header_idx]):
        field = match_field(cell, synonyms=synonyms)
        if field:
            columns.setdefault(field, []).append(idx)
    if "name" not in columns or ("qty" not in columns and "price" not in columns):
        return None
    return {"columns": columns, "data_start": header_idx + 1}
```

```python
def _header_cell_leftover(cell_text, synonyms=None):
    if not cell_text:
        return ""
    lines = str(cell_text).split("\n")
    last_label_idx = -1
    for idx, line in enumerate(lines):
        if match_field(line, synonyms=synonyms):
            last_label_idx = idx
    return "\n".join(lines[last_label_idx + 1:]).strip()
```

`extract_items_from_table`은 시그니처에 `synonyms=None` 추가하고, `_header_cell_leftover(...)` 호출에 `synonyms=synonyms`를 넘기고, 커스텀 열도 담아가도록 아래처럼 바꾼다:

```python
FIXED_TABLE_FIELDS = {"name", "spec", "unit", "qty", "price"}


def extract_items_from_table(table, mapping, synonyms=None):
    columns = mapping["columns"]

    def first_col(field):
        indices = columns.get(field)
        return indices[0] if indices else None

    name_col = first_col("name")
    spec_col = first_col("spec")
    unit_col = first_col("unit")
    qty_col = first_col("qty")
    price_cols = columns.get("price", [])
    extra_cols = {field: first_col(field) for field in columns if field not in FIXED_TABLE_FIELDS}

    def cell(row, col):
        if col is None or col >= len(row):
            return ""
        value = row[col]
        return value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())

    header_row = table[mapping["data_start"] - 1]
    leftover = {}
    for indices in columns.values():
        for idx in indices:
            text = _header_cell_leftover(header_row[idx] if idx < len(header_row) else "", synonyms=synonyms)
            if text:
                leftover[idx] = text

    data_rows = table[mapping["data_start"]:]
    if leftover:
        synthetic_row = [leftover.get(i, "") for i in range(max(leftover) + 1)]
        data_rows = [synthetic_row] + data_rows

    rows = []
    for raw_row in data_rows:
        name = cell(raw_row, name_col)
        if not name:
            continue
        row = {
            "name": name,
            "spec": cell(raw_row, spec_col),
            "unit": cell(raw_row, unit_col),
            "qty_raw": cell(raw_row, qty_col),
            "price_raws": [cell(raw_row, c) for c in price_cols],
        }
        for field, col in extra_cols.items():
            value = cell(raw_row, col)
            if value:
                row[field] = value
        rows.append(row)
    return rows
```

`resolve_duplicate_price_columns`을 커스텀 키도 그대로 넘기도록 교체:

```python
def resolve_duplicate_price_columns(rows):
    resolved = []
    for row in rows:
        qty = parse_number(row["qty_raw"])
        resolved_row = {
            "name": row["name"],
            "spec": row["spec"],
            "unit": row["unit"],
            "qty": qty,
            "price": _pick_price(qty, row["price_raws"]),
        }
        for key, value in row.items():
            if key not in ("name", "spec", "unit", "qty_raw", "price_raws"):
                resolved_row[key] = value
        resolved.append(resolved_row)
    return resolved
```

(`clean_item_rows`, `apply_hierarchical_prefix`는 이미 `dict(row)` 방식으로 나머지 키를 그대로 통과시키므로 손댈 필요 없음.)

`_find_best_table`, OCR 쪽 `_could_seed_label`, `_label_field_for_prefix`, `_match_row_labels`, `_find_ocr_header_row`, `ocr_extract_items`, `_parse_scanned_pdf`, `extract_paragraph_fallback`도 전부 같은 패턴으로 `synonyms=None` 파라미터를 추가하고 내부 호출에 그대로 전달한다:

```python
def _find_best_table(pdf, synonyms=None):
    best_table, best_score = None, 0
    for page in pdf.pages:
        for table in page.extract_tables():
            score = score_table(table, synonyms=synonyms)
            if score > best_score:
                best_table, best_score = table, score
    return best_table


def _could_seed_label(token_text, synonyms=None):
    synonyms = synonyms or HEADER_SYNONYMS
    normalized = normalize_header(token_text)
    if not normalized:
        return False
    for syns in synonyms.values():
        for syn in syns:
            if normalized in normalize_header(syn):
                return True
    return False


def _label_field_for_prefix(normalized_prefix, synonyms=None):
    synonyms = synonyms or HEADER_SYNONYMS
    best_field, best_len = None, 0
    for field, syns in synonyms.items():
        for syn in syns:
            syn_norm = normalize_header(syn)
            if syn_norm and normalized_prefix.startswith(syn_norm) and len(syn_norm) > best_len:
                best_field, best_len = field, len(syn_norm)
    return best_field


def _match_row_labels(words, max_window=3, synonyms=None):
    fields = {}
    n = len(words)
    for start in range(n):
        if not _could_seed_label(words[start]["text"], synonyms=synonyms):
            continue
        concatenated = ""
        real_count = 0
        idx = start
        while idx < n and real_count < max_window:
            token = words[idx]["text"]
            if not _NOISE_TOKEN_RE.match(token):
                concatenated += token
                real_count += 1
                field = _label_field_for_prefix(normalize_header(concatenated), synonyms=synonyms)
                if field:
                    fields.setdefault(field, []).append(words[start]["left"])
                    break
            idx += 1
    return fields


def _find_ocr_header_row(rows, synonyms=None):
    best_idx, best_fields, best_score = None, None, 0
    for idx, row in enumerate(rows):
        fields = _match_row_labels(row["words"], synonyms=synonyms)
        if "name" in fields and len(fields) > best_score:
            best_idx, best_fields, best_score = idx, fields, len(fields)
    return best_idx, best_fields


def ocr_extract_items(pil_image, synonyms=None):
    _configure_tesseract()
    try:
        words = _ocr_words(pil_image)
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError(str(exc)) from exc

    rows = _cluster_words_into_rows(words)
    header_idx, header_fields = _find_ocr_header_row(rows, synonyms=synonyms)
    if header_idx is None:
        return None

    table, mapping = _build_table_from_ocr_rows(rows, header_idx, header_fields)
    if "qty" not in mapping["columns"] and "price" not in mapping["columns"]:
        return None

    table[0] = ["" for _ in table[0]]

    raw_rows = extract_items_from_table(table, mapping, synonyms=synonyms)
    resolved_rows = resolve_duplicate_price_columns(raw_rows)
    cleaned_rows = clean_item_rows(resolved_rows)
    return apply_hierarchical_prefix(cleaned_rows)


def _parse_scanned_pdf(pdf_bytes, warnings, synonyms=None):
    try:
        ocr_pages = _render_pages_for_ocr(pdf_bytes)
        ocr_full_text = "\n".join(ocr_page_text(img) for img in ocr_pages)
        company = extract_company_name(ocr_full_text)
        title = extract_title(ocr_full_text)

        candidate_images = list(ocr_pages) + _extract_large_embedded_images(pdf_bytes)

        items = None
        for img in candidate_images:
            items = ocr_extract_items(img, synonyms=synonyms)
            if items:
                break

        if items:
            pass
        else:
            fallback_item = extract_paragraph_fallback(ocr_full_text, synonyms=synonyms)
            if fallback_item:
                items = [fallback_item]
                warnings.append("표를 찾지 못해 OCR로 일부 항목만 인식했습니다. 나머지는 직접 입력해주세요.")
            else:
                items = []
                warnings.append("OCR로 표를 인식하지 못했습니다. 직접 입력해주세요.")

        warnings.append(
            "스캔(이미지) PDF라서 OCR로 인식했습니다. 인식 결과가 원본과 다를 수 있으니 꼭 확인해주세요."
        )
        return items, company, title
    except OCRUnavailableError:
        warnings.append("OCR 엔진을 찾을 수 없어 스캔 PDF를 인식하지 못했습니다. 미리보기 이미지를 보고 직접 입력해주세요.")
        return [], None, None


def extract_paragraph_fallback(text, synonyms=None):
    found = {}
    for line in text.split("\n"):
        sep = ":" if ":" in line else ("：" if "：" in line else None)
        if sep is None:
            continue
        label, _, value = line.partition(sep)
        field = match_field_fuzzy(label, synonyms=synonyms)
        if not field or field in found:
            continue
        value = value.strip()
        if value:
            found[field] = value
    if "name" not in found:
        return None
    result = {
        "name": found.get("name", ""),
        "spec": found.get("spec", ""),
        "unit": found.get("unit", ""),
        "qty": parse_number(found.get("qty")),
        "price": parse_number(found.get("price")),
    }
    for field, value in found.items():
        if field not in result:
            result[field] = value
    return result
```

마지막으로 `parse_pdf_items`에 `extra_fields` 파라미터를 추가하고, 합쳐진 `synonyms`를 안쪽 호출들에 전부 전달한다:

```python
def parse_pdf_items(pdf_bytes, extra_fields=None):
    synonyms = HEADER_SYNONYMS
    if extra_fields:
        synonyms = dict(HEADER_SYNONYMS)
        synonyms.update(extra_fields)

    warnings = []
    page_images = render_page_images(pdf_bytes)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

        if not full_text.strip():
            items, company, title = _parse_scanned_pdf(pdf_bytes, warnings, synonyms=synonyms)
            return {
                "items": items,
                "page_images": page_images,
                "warnings": warnings,
                "company": company,
                "title": title,
            }

        company = extract_company_name(full_text)
        title = extract_title(full_text)

        best_table = _find_best_table(pdf, synonyms=synonyms)
        mapping = map_table_columns(best_table, synonyms=synonyms) if best_table else None

        if mapping:
            raw_rows = extract_items_from_table(best_table, mapping, synonyms=synonyms)
            resolved_rows = resolve_duplicate_price_columns(raw_rows)
            cleaned_rows = clean_item_rows(resolved_rows)
            items = apply_hierarchical_prefix(cleaned_rows)
        else:
            fallback_item = extract_paragraph_fallback(full_text, synonyms=synonyms)
            if fallback_item:
                items = [fallback_item]
                warnings.append("표를 찾지 못해 일부 항목만 인식했습니다. 나머지는 직접 입력해주세요.")
            else:
                items = []
                warnings.append("표를 인식하지 못했습니다. 직접 입력해주세요.")

    return {"items": items, "page_images": page_images, "warnings": warnings, "company": company, "title": title}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_pdf_item_parser.py`
Expected: `ALL PASSED` (기존 40여개 + 신규 4개 전부)

- [ ] **Step 5: 커밋**

```bash
git add pdf_item_parser.py test_pdf_item_parser.py
git commit -m "feat: let PDF header matching recognize user-defined custom field labels"
```

---

## Task 4: `app.py` — 열 설정 라우트 + `/parse_pdf`, `/generate` 연동

**Files:**
- Modify: `app.py`
- Test: `test_column_settings_route.py` (신규)
- Modify: `test_parse_pdf_route.py` (기존 키셋 검증 갱신 — company/title 빠져있던 기존 버그도 같이 고침)

**Interfaces:**
- Consumes: `column_settings.load_columns/save_columns/add_custom_column/set_column_enabled/delete_column` (Task 1), `parse_pdf_items(pdf_bytes, extra_fields=...)` (Task 3)
- Produces: `GET/POST /column_settings`, `POST /column_settings/add`, `POST /column_settings/enable`, `POST /column_settings/delete`

- [ ] **Step 1: 실패하는 라우트 테스트 작성 — `test_column_settings_route.py`**

```python
import io
import os
import shutil

import app as app_module
import column_settings


def _use_temp_data_dir():
    original_data_dir = column_settings.DATA_DIR
    original_path = column_settings.COLUMN_SETTINGS_PATH
    temp_dir = os.path.join(os.path.dirname(__file__), "_test_data_route")
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


def test_get_column_settings_returns_defaults():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.get("/column_settings")
        assert resp.status_code == 200
        body = resp.get_json()
        assert [c["key"] for c in body["columns"]] == ["spec", "unit", "qty", "price"]
    finally:
        restore()
    print("OK: test_get_column_settings_returns_defaults")


def test_add_column_route_then_it_appears_in_get():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.post("/column_settings/add", data={"label": "중량"})
        assert resp.status_code == 200
        added = resp.get_json()["column"]
        assert added["label"] == "중량"

        resp2 = client.get("/column_settings")
        assert added["key"] in [c["key"] for c in resp2.get_json()["columns"]]
    finally:
        restore()
    print("OK: test_add_column_route_then_it_appears_in_get")


def test_add_column_route_rejects_blank_label():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.post("/column_settings/add", data={"label": "  "})
        assert resp.status_code == 400
    finally:
        restore()
    print("OK: test_add_column_route_rejects_blank_label")


def test_save_column_settings_route_reorders():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        columns = column_settings.load_columns()
        reordered = list(reversed(columns))
        resp = client.post("/column_settings", json={"columns": reordered})
        assert resp.status_code == 200
        assert [c["key"] for c in column_settings.load_columns()] == ["price", "qty", "unit", "spec"]
    finally:
        restore()
    print("OK: test_save_column_settings_route_reorders")


def test_delete_column_route_rejects_builtin():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.post("/column_settings/delete", data={"key": "unit"})
        assert resp.status_code == 400
    finally:
        restore()
    print("OK: test_delete_column_route_rejects_builtin")


def test_parse_pdf_route_passes_enabled_custom_labels_as_extra_fields():
    # column_settings에 커스텀 열을 추가해두면 /parse_pdf가 에러 없이 그 필드를
    # extra_fields로 넘긴 채로 정상 응답해야 한다 (값 인식 여부는 이 테스트의 범위가 아님).
    restore = _use_temp_data_dir()
    try:
        column_settings.add_custom_column("중량")
        client = app_module.app.test_client()

        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "품명 규격 단위 수량 단가")
        pdf_bytes = doc.tobytes()
        doc.close()

        data = {"file": (io.BytesIO(pdf_bytes), "quote.pdf")}
        resp = client.post("/parse_pdf", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
    finally:
        restore()
    print("OK: test_parse_pdf_route_passes_enabled_custom_labels_as_extra_fields")


if __name__ == "__main__":
    test_get_column_settings_returns_defaults()
    test_add_column_route_then_it_appears_in_get()
    test_add_column_route_rejects_blank_label()
    test_save_column_settings_route_reorders()
    test_delete_column_route_rejects_builtin()
    test_parse_pdf_route_passes_enabled_custom_labels_as_extra_fields()
    print("ALL PASSED")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python test_column_settings_route.py`
Expected: `404 Not Found` 계열 실패 (`/column_settings` 라우트가 아직 없음)

- [ ] **Step 3: `app.py`에 라우트 추가 + 기존 라우트 연동**

`app.py` 상단 import에 추가:

```python
import column_settings
```

`index()` 라우트에 `columns=column_settings.load_columns()`를 템플릿 컨텍스트에 추가:

```python
@app.route("/")
def index():
    projects = history_store.load_projects()
    for p in projects:
        p["label"] = history_store.effective_label(p)
    return render_template(
        "index.html",
        history=history_store.load_history(),
        projects=projects,
        columns=column_settings.load_columns(),
        refreshed=request.args.get("refreshed"),
        added=request.args.get("added"),
    )
```

새 라우트들 추가 (`/refresh_read_seed`와 `/parse_pdf` 사이 어디든):

```python
@app.route("/column_settings", methods=["GET"])
def get_column_settings():
    return jsonify({"columns": column_settings.load_columns()})


@app.route("/column_settings", methods=["POST"])
def save_column_settings_route():
    payload = request.get_json(silent=True) or {}
    columns = payload.get("columns")
    if not isinstance(columns, list):
        return jsonify({"error": "columns가 필요합니다."}), 400
    column_settings.save_columns(columns)
    return jsonify({"columns": columns})


@app.route("/column_settings/add", methods=["POST"])
def add_column_setting():
    label = request.form.get("label", "").strip()
    if not label:
        return jsonify({"error": "항목 이름을 입력해주세요."}), 400
    entry = column_settings.add_custom_column(label)
    return jsonify({"column": entry, "columns": column_settings.load_columns()})


@app.route("/column_settings/enable", methods=["POST"])
def set_column_enabled_route():
    key = request.form.get("key", "")
    if not key:
        return jsonify({"error": "key가 필요합니다."}), 400
    enabled = request.form.get("enabled") == "1"
    columns = column_settings.set_column_enabled(key, enabled)
    return jsonify({"columns": columns})


@app.route("/column_settings/delete", methods=["POST"])
def delete_column_setting():
    key = request.form.get("key", "")
    if not key:
        return jsonify({"error": "key가 필요합니다."}), 400
    deleted = column_settings.delete_column(key)
    if not deleted:
        return jsonify({"error": "삭제할 수 없는 항목입니다."}), 400
    return jsonify({"columns": column_settings.load_columns()})
```

`/parse_pdf`를 아래로 교체:

```python
@app.route("/parse_pdf", methods=["POST"])
def parse_pdf():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "파일이 없습니다."}), 400
    extra_fields = {
        c["key"]: [c["label"]]
        for c in column_settings.load_columns()
        if not c.get("builtin") and c.get("enabled")
    }
    try:
        result = parse_pdf_items(file.read(), extra_fields=extra_fields or None)
    except Exception:
        return jsonify({"error": "PDF를 읽을 수 없습니다. 파일이 손상되었거나 PDF 형식이 아닐 수 있습니다."}), 400
    return jsonify(result)
```

`/generate`의 폼 파싱 부분(현재 `use_spec`/`use_unit`/`use_qty`/`use_price`와 `names`/`specs`/`units`/`qtys`/`prices`/`supplies`를 각각 뽑아 `zip`하던 부분)을 아래로 교체:

```python
@app.route("/generate", methods=["POST"])
def generate():
    form = request.form
    columns = column_settings.load_columns()

    names = form.getlist("item_name[]")
    supplies = form.getlist("item_supply[]")
    active_values = {
        c["key"]: form.getlist(f"item_{c['key']}[]")
        for c in columns
        if f"use_{c['key']}" in form
    }

    items = []
    try:
        for idx, name in enumerate(names):
            if not name.strip():
                continue
            item = {"name": name.strip()}
            for key, values in active_values.items():
                raw = values[idx] if idx < len(values) else ""
                if key == "qty":
                    item["qty"] = float(raw) if raw.strip() else 0
                elif key == "price":
                    item["price"] = float(raw) if raw.strip() else 0
                else:
                    item[key] = raw.strip()
            if "price" not in item:
                supply_raw = supplies[idx] if idx < len(supplies) else ""
                item["supply"] = float(supply_raw) if supply_raw.strip() else 0
            items.append(item)
    except ValueError:
        return "수량/단가/공급가는 숫자로 입력해주세요.", 400

    if not items:
        return "품목을 1개 이상 입력해주세요.", 400
    ...
```

(이 아래 `data = {...}` 부분과 나머지는 그대로 둔다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_column_settings_route.py`
Expected: `ALL PASSED`

- [ ] **Step 5: 기존 `/parse_pdf` 응답 키셋 테스트 갱신 (이번 작업과 무관했던 기존 실패도 같이 고침)**

`test_parse_pdf_route.py`의 `test_parse_pdf_route_returns_json_with_expected_keys`에서:

```python
    assert set(body.keys()) == {"items", "page_images", "warnings"}
```

를

```python
    assert set(body.keys()) == {"items", "page_images", "warnings", "company", "title"}
```

로 바꾼다.

Run: `python test_parse_pdf_route.py`
Expected: `ALL PASSED`

- [ ] **Step 6: 커밋**

```bash
git add app.py test_column_settings_route.py test_parse_pdf_route.py
git commit -m "feat: wire column_settings into parse_pdf and generate routes"
```

---

## Task 5: `templates/index.html` — 동적 열 렌더링 + "열 관리" 모달

**Files:**
- Modify: `templates/index.html`

이 파일에는 JS 단위 테스트가 없으므로(기존에도 없었음), 이 Task의 검증은 **Step 4의 수동 스모크 테스트**로 한다.

**Interfaces:**
- Consumes: `columns` (Jinja 컨텍스트, Task 4에서 `index()`가 전달), `/column_settings*` 라우트들 (Task 4)

> **줄 번호 주의:** 아래 각 스텝에서 언급하는 "N~M행"은 **이 Task를 시작하기 전(Task 1~4까지만 반영된) 원본 `templates/index.html`** 기준이다. 이 Task 안에서 앞 스텝의 교체가 끝나면 뒤 스텝들의 실제 줄 번호는 밀린다 — 줄 번호로 대략의 위치만 잡고, 실제 교체 대상은 각 스텝에 그대로 인용된 **기존 코드 문자열**(예: `function addRow(prefill) {...}` 전체, `const PROJECTS = ...` 다음 줄들)로 정확히 찾아서 바꾄다.

- [ ] **Step 1: 품목 필드셋 HTML을 동적 렌더링용 골격으로 교체**

`templates/index.html`의 293~325행(`<fieldset id="itemsFieldset">` ~ `</fieldset>`)을 아래로 교체:

```html
    <fieldset id="itemsFieldset">
      <legend>품목</legend>
      <div class="col-toggles" id="colToggles"></div>
      <button type="button" class="small" id="manageColumnsBtn" style="margin-bottom:10px;">⚙ 열 관리</button>
      <table id="itemsTable">
        <thead>
          <tr id="itemsHeaderRow"></tr>
        </thead>
        <tbody id="itemsBody"></tbody>
      </table>
      <div class="row-buttons">
        <button type="button" class="small" id="addRowBtn">+ 품목 추가</button>
        <button type="button" class="small" id="pdfUploadBtn">📄 PDF로 품목 불러오기</button>
        <input type="file" id="pdfFileInput" accept="application/pdf" style="display:none">
      </div>
      <div class="totals">
        공급가 합계: <span id="sumSupply">0</span>원 &nbsp;|&nbsp;
        부가세 합계: <span id="sumVat">0</span>원 &nbsp;|&nbsp;
        <b>총 합계: <span id="sumTotal">0</span>원</b>
      </div>
    </fieldset>
```

- [ ] **Step 2: PDF 미리보기 표 헤더도 동적 골격으로, "열 관리" 모달 HTML 추가**

PDF 모달 안 348~358행(`<thead>...</thead>`)을 아래로 교체:

```html
            <thead>
              <tr id="pdfDraftHeaderRow"></tr>
            </thead>
```

`</div>` (374행, `pdfModalOverlay` 닫힘) 바로 다음에 새 모달 추가:

```html
  <div id="columnModalOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:200;">
    <div style="background:#fff;max-width:480px;margin:60px auto;border-radius:10px;padding:20px 24px;">
      <h2 style="font-size:16px;margin:0 0 12px;">열 관리</h2>
      <p style="font-size:12px;color:#667085;margin:0 0 10px;">드래그해서 순서를 바꾸거나, 체크로 켜고 끄고, 커스텀 항목은 ✕로 삭제할 수 있습니다. 저장하면 화면이 새로고침됩니다.</p>
      <ul id="columnManageList" style="list-style:none;padding:0;margin:0 0 14px;"></ul>
      <div style="display:flex;gap:6px;">
        <input type="text" id="newColumnLabel" placeholder="새 항목 이름 (예: 중량)" style="flex:1;padding:7px;border:1px solid var(--border);border-radius:6px;">
        <button type="button" class="small" id="addColumnBtn">추가</button>
      </div>
      <div id="columnManageMsg" style="font-size:12px;margin-top:8px;color:#b42318;"></div>
      <div class="row-buttons" style="margin-top:14px;">
        <button type="button" class="small" id="closeColumnModalBtn">저장하고 닫기</button>
        <button type="button" class="small" id="cancelColumnModalBtn">취소</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 3: JS를 `COLUMNS` 기반 동적 렌더링으로 교체**

`<script>` 블록에서 아래 부분들을 교체한다.

`const PROJECTS = ...` 바로 다음 줄들(377~382행, `itemsBody`/`colSpec`/`colUnit`/`colQty`/`colPrice` 상수 선언)을 아래로 교체:

```javascript
const PROJECTS = {{ projects | tojson }};
let COLUMNS = {{ columns | tojson }};
const itemsBody = document.getElementById('itemsBody');

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value == null ? '' : String(value);
  return div.innerHTML;
}

function renderColumnToggles() {
  const box = document.getElementById('colToggles');
  box.innerHTML = '';
  COLUMNS.forEach(c => {
    const label = document.createElement('label');
    label.innerHTML = `<input type="checkbox" name="use_${c.key}" data-key="${c.key}" ${c.enabled ? 'checked' : ''}> ${escapeHtml(c.label)}`;
    box.appendChild(label);
    label.querySelector('input').addEventListener('change', async (e) => {
      c.enabled = e.target.checked;
      applyColumnVisibility();
      const fd = new FormData();
      fd.append('key', c.key);
      fd.append('enabled', c.enabled ? '1' : '0');
      try { await fetch('/column_settings/enable', { method: 'POST', body: fd }); } catch (err) { /* 다음 새로고침 때 재시도됨 */ }
    });
  });
}

function renderItemsHeader() {
  const tr = document.getElementById('itemsHeaderRow');
  tr.innerHTML = '<th style="width:22%">품목</th>' +
    COLUMNS.map(c => `<th data-col="${c.key}">${escapeHtml(c.label)}</th>`).join('') +
    '<th style="width:14%">공급가</th><th style="width:5%"></th>';
}

function renderPdfDraftHeader() {
  const tr = document.getElementById('pdfDraftHeaderRow');
  tr.innerHTML = '<th style="border:1px solid var(--border);padding:6px;">품목</th>' +
    COLUMNS.map(c => `<th style="border:1px solid var(--border);padding:6px;">${escapeHtml(c.label)}</th>`).join('') +
    '<th style="border:1px solid var(--border);padding:6px;"></th>';
}
```

`function addRow(prefill) {...}` 전체(558~577행)를 아래로 교체 (`escapeHtml`은 위에서 먼저 정의해 옮겼으니 중복 정의하지 않는다 — 아래 Step에서 기존 `escapeHtml` 정의(672~676행)는 삭제):

```javascript
function addRow(prefill) {
  prefill = prefill || {};
  const tr = document.createElement('tr');
  const cellsHtml = COLUMNS.map(c => {
    if (c.key === 'qty') {
      return `<td data-col="qty"><input type="number" class="f-field" data-key="qty" value="${prefill.qty ?? 1}" min="0" step="any"></td>`;
    }
    if (c.key === 'price') {
      return `<td data-col="price"><input type="number" class="f-field" data-key="price" value="${prefill.price ?? 0}" min="0" step="any"></td>`;
    }
    const defaultValue = c.key === 'unit' ? 'EA' : '';
    const val = prefill[c.key] != null ? prefill[c.key] : defaultValue;
    return `<td data-col="${c.key}"><input type="text" class="f-field" data-key="${c.key}" value="${escapeHtml(val)}"></td>`;
  }).join('');
  tr.innerHTML = `
    <td><input type="text" class="f-name" value="${escapeHtml(prefill.name||'')}"></td>
    ${cellsHtml}
    <td>
      <span class="f-supply-calc">0</span>
      <input type="number" class="f-supply-input" value="0" min="0" step="any" style="display:none">
    </td>
    <td><button type="button" class="small removeRowBtn">삭제</button></td>
  `;
  itemsBody.appendChild(tr);
  tr.querySelectorAll('[data-key="qty"], [data-key="price"], .f-supply-input').forEach(el => el.addEventListener('input', recalc));
  tr.querySelector('.removeRowBtn').addEventListener('click', () => { tr.remove(); recalc(); });
  applyColumnVisibility();
}
```

`function applyColumnVisibility() {...}` 부터 `[colSpec, colUnit, colQty, colPrice].forEach(...)` 줄까지(579~592행)를 아래로 교체:

```javascript
function applyColumnVisibility() {
  const show = {};
  COLUMNS.forEach(c => show[c.key] = c.enabled);
  document.querySelectorAll('[data-col]').forEach(el => {
    el.style.display = show[el.dataset.col] ? '' : 'none';
  });
  const priceOn = !!show.price;
  document.querySelectorAll('#itemsBody tr').forEach(tr => {
    const calc = tr.querySelector('.f-supply-calc');
    const inp = tr.querySelector('.f-supply-input');
    if (priceOn) { calc.style.display = ''; inp.style.display = 'none'; }
    else { calc.style.display = 'none'; inp.style.display = ''; }
  });
  recalc();
}
```

`function recalc() {...}` 전체(594~614행)를 아래로 교체:

```javascript
function recalc() {
  let sumSupply = 0, sumVat = 0;
  const priceCol = COLUMNS.find(c => c.key === 'price');
  const qtyCol = COLUMNS.find(c => c.key === 'qty');
  const usePrice = !!(priceCol && priceCol.enabled);
  const useQty = !!(qtyCol && qtyCol.enabled);
  itemsBody.querySelectorAll('tr').forEach(tr => {
    let supply;
    if (usePrice) {
      const price = parseFloat(tr.querySelector('[data-key="price"]').value) || 0;
      const qty = useQty ? (parseFloat(tr.querySelector('[data-key="qty"]').value) || 0) : 1;
      supply = qty * price;
      tr.querySelector('.f-supply-calc').textContent = supply.toLocaleString();
    } else {
      supply = parseFloat(tr.querySelector('.f-supply-input').value) || 0;
    }
    sumSupply += supply;
    sumVat += supply / 10;
  });
  document.getElementById('sumSupply').textContent = sumSupply.toLocaleString();
  document.getElementById('sumVat').textContent = sumVat.toLocaleString();
  document.getElementById('sumTotal').textContent = (sumSupply + sumVat).toLocaleString();
}
```

`document.getElementById('addRowBtn').addEventListener(...)`와 그 다음 `addRow();` 줄(616~617행) 바로 아래에 초기 렌더링 호출을 추가:

```javascript
document.getElementById('addRowBtn').addEventListener('click', () => addRow());
renderColumnToggles();
renderItemsHeader();
renderPdfDraftHeader();
addRow();
```

폼 제출 핸들러(619~664행) 안의 `rows.forEach(tr => {...})` 블록(632~639행)을 아래로 교체:

```javascript
  rows.forEach(tr => {
    fd.append('item_name[]', tr.querySelector('.f-name').value);
    COLUMNS.forEach(c => {
      const el = tr.querySelector(`[data-key="${c.key}"]`);
      fd.append(`item_${c.key}[]`, el ? el.value : '');
    });
    fd.append('item_supply[]', tr.querySelector('.f-supply-input').value);
  });
```

기존 `function escapeHtml(value) {...}` 정의(672~676행, PDF 모달 스크립트 쪽에 있던 것)는 이제 위에서 먼저 선언했으므로 **삭제**한다(중복 선언 방지).

`function addDraftRow(prefill) {...}` 전체(678~691행)를 아래로 교체:

```javascript
function addDraftRow(prefill) {
  prefill = prefill || {};
  const tr = document.createElement('tr');
  const cells = COLUMNS.map(c => {
    const type = (c.key === 'qty' || c.key === 'price') ? 'number' : 'text';
    const val = prefill[c.key] != null ? prefill[c.key] : '';
    return `<td style="border:1px solid var(--border);padding:4px;"><input type="${type}" class="d-field" data-key="${c.key}" value="${escapeHtml(val)}" style="width:100%;border:none;"></td>`;
  }).join('');
  tr.innerHTML = `
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="d-name" value="${escapeHtml(prefill.name || '')}" style="width:100%;border:none;"></td>
    ${cells}
    <td style="border:1px solid var(--border);padding:4px;"><button type="button" class="small removeDraftBtn">삭제</button></td>
  `;
  pdfDraftBody.appendChild(tr);
  tr.querySelector('.removeDraftBtn').addEventListener('click', () => tr.remove());
}
```

`function collectDraftItems() {...}` 전체(732~740행)를 아래로 교체:

```javascript
function collectDraftItems() {
  return [...pdfDraftBody.querySelectorAll('tr')].map(tr => {
    const item = { name: tr.querySelector('.d-name').value };
    COLUMNS.forEach(c => {
      const el = tr.querySelector(`[data-key="${c.key}"]`);
      if (!el) return;
      if (c.key === 'qty' || c.key === 'price') {
        item[c.key] = parseFloat(el.value) || 0;
      } else {
        item[c.key] = el.value;
      }
    });
    return item;
  }).filter(item => item.name.trim());
}
```

마지막으로, `</script>` 바로 앞에 "열 관리" 모달 동작 JS를 추가:

```javascript
function renderColumnManageList() {
  const list = document.getElementById('columnManageList');
  list.innerHTML = '';
  COLUMNS.forEach(c => {
    const li = document.createElement('li');
    li.draggable = true;
    li.dataset.key = c.key;
    li.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px;border:1px solid var(--border);border-radius:6px;margin-bottom:6px;background:#fff;';
    li.innerHTML = `
      <span style="cursor:grab;">⠿</span>
      <input type="checkbox" class="col-enabled-cb" ${c.enabled ? 'checked' : ''}>
      <span style="flex:1;">${escapeHtml(c.label)}</span>
      ${c.builtin ? '' : '<button type="button" class="small removeColumnBtn">✕</button>'}
    `;
    li.querySelector('.col-enabled-cb').addEventListener('change', (e) => { c.enabled = e.target.checked; });
    const removeBtn = li.querySelector('.removeColumnBtn');
    if (removeBtn) {
      removeBtn.addEventListener('click', async () => {
        const fd = new FormData();
        fd.append('key', c.key);
        await fetch('/column_settings/delete', { method: 'POST', body: fd });
        COLUMNS = COLUMNS.filter(x => x.key !== c.key);
        renderColumnManageList();
      });
    }
    list.appendChild(li);
  });
}

let dragSrcKey = null;
const columnManageList = document.getElementById('columnManageList');
columnManageList.addEventListener('dragstart', (e) => {
  const li = e.target.closest('li');
  if (!li) return;
  dragSrcKey = li.dataset.key;
  e.dataTransfer.effectAllowed = 'move';
});
columnManageList.addEventListener('dragover', (e) => e.preventDefault());
columnManageList.addEventListener('drop', (e) => {
  e.preventDefault();
  const targetLi = e.target.closest('li');
  if (!targetLi || !dragSrcKey || targetLi.dataset.key === dragSrcKey) return;
  const srcIdx = COLUMNS.findIndex(c => c.key === dragSrcKey);
  const targetIdx = COLUMNS.findIndex(c => c.key === targetLi.dataset.key);
  const [moved] = COLUMNS.splice(srcIdx, 1);
  COLUMNS.splice(targetIdx, 0, moved);
  dragSrcKey = null;
  renderColumnManageList();
});

document.getElementById('manageColumnsBtn').addEventListener('click', () => {
  renderColumnManageList();
  document.getElementById('columnManageMsg').textContent = '';
  document.getElementById('newColumnLabel').value = '';
  document.getElementById('columnModalOverlay').style.display = 'block';
});

document.getElementById('cancelColumnModalBtn').addEventListener('click', () => {
  document.getElementById('columnModalOverlay').style.display = 'none';
  location.reload();  // 취소해도 화면에 반영된 enabled 토글은 이미 서버에 저장됐을 수 있으니 새로고침으로 진짜 상태와 맞춘다
});

document.getElementById('closeColumnModalBtn').addEventListener('click', async () => {
  await fetch('/column_settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ columns: COLUMNS }),
  });
  document.getElementById('columnModalOverlay').style.display = 'none';
  location.reload();
});

document.getElementById('addColumnBtn').addEventListener('click', async () => {
  const input = document.getElementById('newColumnLabel');
  const label = input.value.trim();
  const msg = document.getElementById('columnManageMsg');
  if (!label) { msg.textContent = '항목 이름을 입력해주세요.'; return; }
  const fd = new FormData();
  fd.append('label', label);
  const res = await fetch('/column_settings/add', { method: 'POST', body: fd });
  const data = await res.json();
  if (!res.ok) { msg.textContent = data.error || '추가에 실패했습니다.'; return; }
  msg.textContent = '';
  input.value = '';
  if (!COLUMNS.find(c => c.key === data.column.key)) {
    COLUMNS.push(data.column);
  }
  renderColumnManageList();
});
```

- [ ] **Step 4: 수동 스모크 테스트**

Run: `python app.py` 로 개발 서버를 띄우고 브라우저에서:
1. 페이지가 열리면 품목 표에 규격/단위/수량/단가 체크박스 4개 + "⚙ 열 관리" 버튼이 보이는지 확인.
2. "⚙ 열 관리" 클릭 → 모달에서 "중량" 타이핑 후 "추가" → 목록에 추가되는지 확인.
3. 드래그로 순서를 바꾼 뒤 "저장하고 닫기" → 새로고침 후 품목 표 헤더 순서가 바뀌었는지, 체크박스도 5개(중량 포함)가 되는지 확인.
4. `PDF_read/견적서_알루스퀘어.pdf`를 "PDF로 품목 불러오기"로 업로드 → 미리보기 표에 "중량" 열이 있고 값이 채워지려고 시도하는지 확인(스캔 품질상 완벽하진 않을 수 있음, 열 자체가 나타나는지가 핵심).
5. 품목을 1개 입력하고 "엑셀 파일 생성" → 다운로드된 xlsx를 열어 단위/수량 칸이 병합 없이 1칸인지, 품목/규격 칸이 이전보다 넓어졌는지, 중량 칸에 입력한 값이 들어갔는지 확인.
6. "⚙ 열 관리"에서 커스텀 열(중량)을 ✕로 삭제 → 저장 후 사라지는지 확인.

Expected: 위 6개 모두 화면에서 그대로 동작.

- [ ] **Step 5: 커밋**

```bash
git add templates/index.html
git commit -m "feat: render item columns dynamically and add drag-reorderable column settings UI"
```

---

## Task 6: 전체 회귀 확인

**Files:** (수정 없음, 확인만)

- [ ] **Step 1: 전체 테스트 스위트 실행**

Run:
```bash
python test_column_settings.py
python test_column_layout.py
python test_pdf_item_parser.py
python test_column_settings_route.py
python test_parse_pdf_route.py
python test_generator.py
python test_item_table_layout.py
python test_history_store_merge.py
python test_template_banner.py
python test_read_seed.py
python test_app_refresh_route.py
```
Expected: 전부 `ALL PASSED` (또는 예외 없이 종료).

- [ ] **Step 2: `_diag_*`류 임시 파일이 안 남았는지 확인**

Run: `git status --short`
Expected: Task 1~5에서 의도적으로 만든 파일들(column_settings.py, test_column_settings.py, test_column_settings_route.py, 수정된 generator.py/pdf_item_parser.py/app.py/templates/index.html/test_column_layout.py/test_pdf_item_parser.py/test_parse_pdf_route.py)만 보여야 함.

- [ ] **Step 3: 최종 커밋 (필요 시)**

Run 시 정리할 게 남았으면:
```bash
git add -A
git commit -m "chore: finalize configurable item columns feature"
```
