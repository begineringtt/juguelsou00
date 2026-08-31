# PDF 품목 헤더 매핑 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `견적서_20260721(그린플러스_IR Cut_8월).pdf`처럼 (1) 품목 헤더가 `Quantity`/`Price(￦/M2)`처럼 기존 동의어와 정확히 일치하지 않는 견적서와 (2) 품목명(Description) 칸에 행 구분선이 없어서 표 추출 시 그 칸이 통째로 빈 값(`None`)이 되는 견적서, 이 두 문제를 동시에 겪는 PDF에서도 품목이 인식되게 한다.

**Architecture:** `pdf_item_parser.py`의 기존 헤더 동의어 매칭 파이프라인(`match_field`/`find_header_row`/`map_table_columns`)에 손을 대지 않고, (1) 동의어 사전에 `QUANTITY`/`PRICE`를 추가하고 표 헤더 스코어링 경로에서만 정확 매칭 실패 시 기존 `match_field_fuzzy`로 한 번 더 시도하도록 얇은 fallback을 씌운다. (2) `page.find_tables()`가 주는 셀 좌표(bbox)와 `page.crop()`을 이용해, 구조적으로 셀 자체가 없는(선이 없는) 품목명 칸만 좌표 기반으로 복구하는 순수 함수를 추가하고 `_find_best_table`에서 `extract_tables()` 대신 `find_tables()`+`.extract()`를 직접 호출하도록 바꿔 그 복구를 끼워 넣는다. 기존에 값이 있던 칸은 절대 건드리지 않는다.

**Tech Stack:** Python, pdfplumber (이미 의존성에 있음, 새 라이브러리 추가 없음)

**Spec:** `docs/superpowers/specs/2026-08-05-pdf-header-and-projects-design.md` (A항목만 — B/C/D항목은 이번 계획의 범위 밖)

## Global Constraints

- 기존 8개 샘플 PDF에 대한 `test_pdf_item_parser.py`의 기존 테스트는 전부 그대로 통과해야 한다 (회귀 없음) — 특히 `find_header_row`/`map_table_columns`에 fuzzy fallback을 추가해도 기존 샘플들의 헤더 선택 결과가 바뀌면 안 된다.
- 이미 값이 채워진 표 셀은 어떤 경우에도 덮어쓰지 않는다 — 구조적으로 셀 자체(bbox)가 없는 경우에만 좌표 크롭으로 복구한다.
- 새 함수는 실제 PDF 없이도 단위 테스트할 수 있도록 순수 함수로 작성한다 (fake bbox/crop 함수로 테스트).
- `과제 CRUD를 id 기반 REST API로 재구현`(스펙 D항목)은 이번 계획에 포함하지 않는다 — 기존 `/add_project`/`/update_project`/`/delete_project`(`project_name` 키 기반)는 그대로 둔다.

---

## Task 1: 헤더 동의어 확장 + fuzzy fallback을 표 헤더 매칭 경로에 연결

**Files:**
- Modify: `pdf_item_parser.py:35-41` (`HEADER_SYNONYMS`), `pdf_item_parser.py:250-259` (`find_header_row`), `pdf_item_parser.py:269-282` (`map_table_columns`)
- Test: `test_pdf_item_parser.py`

**Interfaces:**
- Consumes: 기존 `match_field(header_text) -> str|None`, 기존 `match_field_fuzzy(label_text) -> str|None` (둘 다 이미 존재, 시그니처 변경 없음)
- Produces: `find_header_row`/`map_table_columns`가 이제 정확 매칭 실패 시 fuzzy로도 컬럼을 인식함 (반환 타입/시그니처는 기존과 동일하게 유지)

- [ ] **Step 1: 실패하는 테스트 작성**

`test_pdf_item_parser.py`에 아래 테스트를 `test_match_field_fuzzy_matches_substring_with_bullet_prefix` 함수 뒤에 추가한다:

```python
def test_match_field_exact_recognizes_quantity_synonym():
    assert match_field("Quantity") == "qty"
    print("OK: test_match_field_exact_recognizes_quantity_synonym")


def test_find_header_row_uses_fuzzy_fallback_for_unmatched_exact_labels():
    # "Price(￦/M2)"는 "UNIT PRICE"/"단가"와 정확히 일치하지 않지만 "PRICE"를
    # 부분 문자열로 포함하므로 fuzzy fallback으로 매칭돼야 한다.
    table = [
        ["Description", "Quantity", "Unit", "Price(￦/M2)"],
        ["ETFE film", "2.0", "days", "6,119,375"],
    ]
    idx, score = find_header_row(table)
    assert idx == 0
    assert score == 4
    print("OK: test_find_header_row_uses_fuzzy_fallback_for_unmatched_exact_labels")


def test_map_table_columns_maps_quantity_and_bracketed_price_headers():
    table = [
        ["Description", "Quantity", "Unit", "Price(￦/M2)"],
        ["ETFE film", "2.0", "days", "6,119,375"],
    ]
    result = map_table_columns(table)
    assert result["columns"] == {"name": [0], "qty": [1], "unit": [2], "price": [3]}
    print("OK: test_map_table_columns_maps_quantity_and_bracketed_price_headers")
```

`__main__` 블록의 호출 목록(`test_match_field_fuzzy_matches_substring_with_bullet_prefix()` 다음 줄)에도 세 함수 호출을 추가한다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python test_pdf_item_parser.py`
Expected: `test_match_field_exact_recognizes_quantity_synonym`은 `assert match_field("Quantity") == "qty"`에서 `None == "qty"`로 FAIL. `test_find_header_row_uses_fuzzy_fallback_for_unmatched_exact_labels`는 `score == 4`가 아니라 `score == 2`(Description은 이미 name과 정확 일치, Unit도 정확 일치, Quantity/Price는 매칭 안 됨)로 FAIL. `test_map_table_columns_maps_quantity_and_bracketed_price_headers`는 `columns`에 `qty`/`price`가 없어 FAIL.

- [ ] **Step 3: `HEADER_SYNONYMS`에 동의어 추가**

`pdf_item_parser.py`의 `HEADER_SYNONYMS`(현재 35-41행)를 다음으로 교체:

```python
HEADER_SYNONYMS = {
    "name": ["품명", "품 명", "공사명/품명", "물품명", "ITEM", "DESCRIPTION"],
    "spec": ["규격", "규 격", "SIZE", "형식", "규격/색상", "사양"],
    "unit": ["단위", "단 위", "UNIT"],
    "qty": ["수량", "수 량", "Q'TY", "QTY", "QUANTITY"],
    "price": ["단가", "단 가", "UNIT PRICE", "PRICE"],
}
```

- [ ] **Step 4: `find_header_row`에 fuzzy fallback 연결**

`pdf_item_parser.py`의 `find_header_row`(현재 250-259행, `max_scan` 관련 주석 포함)를 다음으로 교체:

```python
# max_scan is unused by any current caller (both call sites scan the whole
# table) — kept as an escape hatch if a future table ever needs capping.
def find_header_row(table, max_scan=None):
    best_idx, best_score = None, 0
    rows = table[:max_scan] if max_scan is not None else table
    for idx, row in enumerate(rows):
        score = sum(1 for cell in row if match_field(cell) or match_field_fuzzy(cell))
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx, best_score
```

- [ ] **Step 5: `map_table_columns`에 fuzzy fallback 연결**

`pdf_item_parser.py`의 `map_table_columns`(현재 269-282행)를 다음으로 교체:

```python
def map_table_columns(table):
    if not table:
        return None
    header_idx, _ = find_header_row(table)
    if header_idx is None:
        return None
    columns = {}
    for idx, cell in enumerate(table[header_idx]):
        field = match_field(cell) or match_field_fuzzy(cell)
        if field:
            columns.setdefault(field, []).append(idx)
    if "name" not in columns or ("qty" not in columns and "price" not in columns):
        return None
    return {"columns": columns, "data_start": header_idx + 1}
```

- [ ] **Step 6: 테스트 통과 확인 + 회귀 확인**

Run: `python test_pdf_item_parser.py`
Expected: 새로 추가한 3개 테스트 포함 전부 PASS (`ALL PASSED`). 특히 기존 `test_find_header_row_scans_past_five_metadata_rows`, `test_map_table_columns_detects_duplicate_price_header` 등 기존 테스트도 그대로 PASS해야 한다 (fuzzy fallback 추가로 인한 회귀가 없어야 함).

- [ ] **Step 7: Commit**

```bash
git add pdf_item_parser.py test_pdf_item_parser.py
git commit -m "feat: add QUANTITY/PRICE header synonyms with fuzzy fallback for table header matching"
```

---

## Task 2: 좌표 기반 품목명 칸 복구

**Files:**
- Modify: `pdf_item_parser.py:435-442` (`_find_best_table`)
- Test: `test_pdf_item_parser.py`

**Interfaces:**
- Consumes: 없음 (순수 함수, 새로 추가)
- Produces:
  - `_recover_missing_name_column(table_x0: float, rows: list[list], row_cells: list[list[tuple|None]], crop_text_fn: Callable[[float, float, float, float], str|None]) -> list[list]` — `rows`와 같은 모양의 새 리스트를 반환. `row_cells[i][0]`이 `None`인(구조적으로 셀이 없는) 행만, 그 행의 다른 칸들 중 가장 왼쪽 x0을 오른쪽 경계로 삼아 `crop_text_fn(table_x0, top, name_x1, bottom)`을 호출해 그 결과로 `row[0]`을 채운다. `row_cells[i][0]`이 `None`이 아니면(이미 셀이 있으면, 값이 비어 있어도) 해당 행은 건드리지 않는다.
  - `_find_best_table(pdf)`는 기존과 동일한 반환 타입(`list[list] | None`)을 유지하되, 내부적으로 위 복구를 적용한 표를 스코어링 대상으로 사용한다.

- [ ] **Step 1: `_recover_missing_name_column` 단위 테스트 작성**

`test_pdf_item_parser.py`에 `pdf_item_parser` 임포트 목록(8-14행)에 `_recover_missing_name_column`을 추가하고, `test_render_page_images_returns_one_png_per_page` 함수 뒤에 아래 테스트를 추가한다:

```python
def test_recover_missing_name_column_fills_structurally_missing_cell():
    from pdf_item_parser import _recover_missing_name_column

    rows = [
        [None, "Quantity", "Unit"],
        [None, "2.0", "days"],
    ]
    row_cells = [
        [None, (100, 0, 150, 20), (150, 0, 200, 20)],
        [None, (100, 20, 150, 40), (150, 20, 200, 40)],
    ]
    crop_calls = []

    def fake_crop(x0, top, x1, bottom):
        crop_calls.append((x0, top, x1, bottom))
        return {
            (0, 0, 100, 20): "Description",
            (0, 20, 100, 40): "ETFE film",
        }.get((x0, top, x1, bottom))

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result[0][0] == "Description"
    assert result[1][0] == "ETFE film"
    assert len(crop_calls) == 2
    print("OK: test_recover_missing_name_column_fills_structurally_missing_cell")


def test_recover_missing_name_column_leaves_existing_cells_untouched():
    from pdf_item_parser import _recover_missing_name_column

    rows = [["TOTAL", "", "", "999"]]
    row_cells = [[(0, 0, 50, 20), (50, 0, 80, 20), (80, 0, 110, 20), (110, 0, 150, 20)]]

    def fake_crop(*args):
        raise AssertionError("이미 셀이 있는 행은 크롭을 호출하면 안 된다")

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result == rows
    print("OK: test_recover_missing_name_column_leaves_existing_cells_untouched")


def test_recover_missing_name_column_skips_when_no_other_cells_to_bound_region():
    from pdf_item_parser import _recover_missing_name_column

    rows = [[None, None, None]]
    row_cells = [[None, None, None]]

    def fake_crop(*args):
        raise AssertionError("경계로 쓸 다른 칸이 없으면 크롭을 호출하면 안 된다")

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result[0][0] is None
    print("OK: test_recover_missing_name_column_skips_when_no_other_cells_to_bound_region")


def test_recover_missing_name_column_skips_when_crop_returns_no_text():
    from pdf_item_parser import _recover_missing_name_column

    rows = [[None, "1"]]
    row_cells = [[None, (50, 0, 80, 20)]]

    def fake_crop(x0, top, x1, bottom):
        return None

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result[0][0] is None
    print("OK: test_recover_missing_name_column_skips_when_crop_returns_no_text")
```

`__main__` 블록에 위 4개 테스트 호출을 `test_render_page_images_returns_one_png_per_page()` 다음 줄에 추가한다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name '_recover_missing_name_column'` (아직 함수가 없으므로 4개 테스트 모두 이 임포트 단계에서 FAIL).

- [ ] **Step 3: `_recover_missing_name_column` 구현**

`pdf_item_parser.py`의 `_find_best_table` 함수(현재 435-442행) 바로 앞에 새 함수를 추가한다:

```python
def _recover_missing_name_column(table_x0, rows, row_cells, crop_text_fn):
    """열 왼쪽에 구분선이 없어서 pdfplumber의 표 추출이 품목명 칸을 통째로
    놓치는 표를 보정한다.

    row_cells[i][j]는 (x0, top, x1, bottom) 튜플 또는 None(그 위치에 셀
    경계선 자체가 없음)이다. 첫 칸(품목명)에 셀 경계가 없는 행만, 그 행의
    나머지 칸 중 가장 왼쪽 x0을 오른쪽 경계로 삼아 crop_text_fn으로 텍스트를
    복구한다. 첫 칸에 이미 셀 경계가 있는 행(값이 비어 있어도)은 건드리지
    않는다 - 구조적으로 없는 칸만 보충하는 것이 목적이다.
    """
    recovered = [list(row) for row in rows]
    for row, cells in zip(recovered, row_cells):
        if not cells or cells[0] is not None:
            continue
        populated = [c for c in cells[1:] if c is not None]
        if not populated:
            continue
        name_x1 = min(c[0] for c in populated)
        if name_x1 <= table_x0:
            continue
        _, top, _, bottom = populated[0]
        text = crop_text_fn(table_x0, top, name_x1, bottom)
        if text:
            row[0] = text.strip()
    return recovered
```

- [ ] **Step 4: 새 4개 테스트 통과 확인**

Run: `python test_pdf_item_parser.py`
Expected: 방금 추가한 4개 `test_recover_missing_name_column_*` 테스트 PASS. (다른 테스트는 아직 `_find_best_table`을 안 건드렸으므로 이 시점까지 영향 없음)

- [ ] **Step 5: `_find_best_table`이 복구를 사용하도록 연결**

`pdf_item_parser.py`의 `_find_best_table`(현재 435-442행)을 다음으로 교체:

```python
def _find_best_table(pdf):
    best_table, best_score = None, 0
    for page in pdf.pages:
        for plumber_table in page.find_tables():
            table_x0 = plumber_table.bbox[0]
            row_cells = [row.cells for row in plumber_table.rows]

            def crop_text_fn(x0, top, x1, bottom, page=page):
                return page.crop((x0, top, x1, bottom)).extract_text()

            table = _recover_missing_name_column(
                table_x0, plumber_table.extract(), row_cells, crop_text_fn
            )
            score = score_table(table)
            if score > best_score:
                best_table, best_score = table, score
    return best_table
```

(`crop_text_fn`의 `page=page` 기본 인자는 for 루프 변수를 클로저가 늦게 바인딩하는 문제를 피하기 위한 것 — 이 루프에서는 안쪽 for에서 매번 새로 정의되므로 실제로는 문제가 없지만, 명시적으로 고정해 의도를 분명히 한다.)

- [ ] **Step 6: 실제 샘플 PDF로 통합 테스트 작성**

`test_pdf_item_parser.py`의 `test_parse_pdf_items_scanned_pdf_degrades_gracefully_without_tesseract` 함수 뒤에 추가:

```python
def test_parse_pdf_items_recovers_borderless_name_column_with_english_headers():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_recovers_borderless_name_column_with_english_headers (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_20260721(그린플러스_IR Cut_8월).pdf"))
    items = result["items"]
    assert len(items) == 2
    assert items[0]["qty"] == 2.0
    assert items[0]["unit"] == "days"
    assert items[0]["price"] == 6119375.0
    assert "ETFE" in items[0]["name"]
    assert items[1]["qty"] == 1300.0
    assert items[1]["unit"] == "㎡"
    assert items[1]["price"] == 11000.0
    assert "Nb2O5" in items[1]["name"]
    print("OK: test_parse_pdf_items_recovers_borderless_name_column_with_english_headers")
```

`__main__` 블록에도 이 함수 호출을 추가한다.

- [ ] **Step 7: 통합 테스트 통과 + 전체 회귀 확인**

Run: `python test_pdf_item_parser.py`
Expected: 새 통합 테스트 PASS, 그리고 기존 8개 샘플 관련 테스트(`test_parse_pdf_items_normal_table_case`, `test_parse_pdf_items_hierarchical_case`, `test_parse_pdf_items_duplicate_header_case`, `test_parse_pdf_items_no_table_fallback_case`, `test_parse_pdf_items_scanned_pdf_*`, `test_extract_company_name_various_samples`, `test_extract_title_various_samples`)도 전부 그대로 PASS — 특히 `test_extract_company_name_various_samples`의 `"견적서_20260721(그린플러스_IR Cut_8월).pdf": "마이크로웍스솔루션즈 주식회사"`, `test_extract_title_various_samples`의 같은 파일 `None` 기대값이 변하지 않아야 한다 (이 변경은 품목 표 추출에만 영향을 주고 업체명/제목 인식에는 영향이 없어야 함).

Run: `python test_generator.py && python test_column_layout.py && python test_item_table_layout.py && python test_history_store_merge.py && python test_read_seed.py`
Expected: 전부 PASS (이번 변경은 `pdf_item_parser.py`에만 있으므로 다른 모듈 테스트는 영향받지 않아야 하지만, 회귀 없음을 명시적으로 확인).

- [ ] **Step 8: Commit**

```bash
git add pdf_item_parser.py test_pdf_item_parser.py
git commit -m "feat: recover borderless item-name column via coordinate-based crop"
```
