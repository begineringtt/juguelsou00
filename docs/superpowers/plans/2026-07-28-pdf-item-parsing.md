# PDF 견적서 품목 자동 인식 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload a vendor quote PDF and have its item table (품명/규격/단위/수량/단가) auto-extracted into a review popup (PDF page images next to an editable draft table), then applied into the existing item table on the main form — either replacing or appending to whatever rows are already there.

**Architecture:** A new pure-Python module `pdf_item_parser.py` does all extraction/parsing as small composable functions (no Flask/HTML dependencies), tested against both synthetic data and the 8 real sample PDFs in `D:\claude_personal\setting_01\PDF_read`. A new Flask route `POST /parse_pdf` in `app.py` wraps it and returns JSON. The frontend (`templates/index.html`) adds an upload button that opens a modal reusing the existing `addRow()` pattern.

**Tech Stack:** Python 3, Flask, `pdfplumber` (table extraction), `PyMuPDF`/`fitz` (page-to-PNG rendering), vanilla JS (no new frontend framework).

## Global Constraints

- Design doc: `docs/superpowers/specs/2026-07-28-pdf-item-parsing-design.md` — every task below implements one part of it.
- Scope is items only (품명/규격/단위/수량/단가). Do not extract company/date/title fields from the PDF.
- Real sample PDFs live outside the repo at `D:\claude_personal\setting_01\PDF_read` and must never be committed to git (they are vendor quotes with pricing — sensitive). Tests that use them must check `os.path.isdir(SAMPLE_DIR)` first and print a `SKIP: ...` message + return early if the folder is absent, exactly like the existing test files in this repo do (see `test_app_refresh_route.py` for the established try/finally + monkeypatch style, and `test_column_layout.py` for the plain-`assert` + `print("OK: ...")` + `if __name__ == "__main__":` runner style — **follow this style, not pytest**, since pytest is not installed in this project).
- Existing test files in this repo are run directly with `python test_x.py`, not `pytest`. Every new test file must follow the same `def test_x(): ...; print("OK: test_x")` + `if __name__ == "__main__": test_x(); print("ALL PASSED")` convention.
- New dependencies: `pdfplumber`, `pymupdf` (import name `fitz`). Install with `python -m pip install pdfplumber pymupdf` before Task 8.
- Follow the existing code style in this repo: no docstrings beyond the module-level one already used in `generator.py`, Korean comments only where genuinely non-obvious, no type hints (the rest of the codebase doesn't use them).

---

### Task 1: Text & number normalization helpers

**Files:**
- Create: `expense_form_app/pdf_item_parser.py`
- Test: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Produces: `HEADER_SYNONYMS: dict[str, list[str]]`, `normalize_header(text) -> str`, `match_field(header_text) -> str | None`, `match_field_fuzzy(label_text) -> str | None`, `parse_number(text) -> float | None`. Later tasks import all of these from `pdf_item_parser`.

These are the string/number primitives every other rule builds on: `match_field` does exact (per-line) matching for real table headers, `match_field_fuzzy` does substring matching for the loose "라벨 : 값" paragraph fallback (Task 7), and `parse_number` turns messy extracted text like `"2 ,100,000"` or `"1.950 MT"` into a float.

- [ ] **Step 1: Write the failing tests**

Create `expense_form_app/test_pdf_item_parser.py`:

```python
from pdf_item_parser import normalize_header, match_field, match_field_fuzzy, parse_number


def test_normalize_header_strips_whitespace_and_uppercases():
    assert normalize_header("품 명") == "품명"
    assert normalize_header("Unit Price") == "UNITPRICE"
    assert normalize_header(None) == ""
    print("OK: test_normalize_header_strips_whitespace_and_uppercases")


def test_match_field_exact_single_line():
    assert match_field("품명") == "name"
    assert match_field("규 격") == "spec"
    assert match_field("UNIT") == "unit"
    assert match_field("Q'TY") == "qty"
    assert match_field("단가") == "price"
    assert match_field("비고") is None
    print("OK: test_match_field_exact_single_line")


def test_match_field_multiline_header_checks_each_line():
    assert match_field("품 명\nDESCRIPTION") == "name"
    assert match_field("공사명/품명\nDESCRIPTION") == "name"
    assert match_field("단가\nUNIT PRICE") == "price"
    print("OK: test_match_field_multiline_header_checks_each_line")


def test_match_field_fuzzy_matches_substring_with_bullet_prefix():
    assert match_field_fuzzy("ㅇ. 품 명 ") == "name"
    assert match_field_fuzzy("ㅇ. 단 가 ") == "price"
    assert match_field_fuzzy("ㅇ. 공 급 가 액") is None
    assert match_field_fuzzy("ㅇ. 부 가 세") is None
    print("OK: test_match_field_fuzzy_matches_substring_with_bullet_prefix")


def test_parse_number_handles_currency_and_stray_spaces():
    assert parse_number("550,000") == 550000.0
    assert parse_number("2 ,100,000") == 2100000.0
    assert parse_number("₩1,040,000") == 1040000.0
    assert parse_number("1.950 MT") == 1.95
    assert parse_number("-") is None
    assert parse_number("") is None
    assert parse_number(None) is None
    assert parse_number("TCP/IP") is None
    print("OK: test_parse_number_handles_currency_and_stray_spaces")


if __name__ == "__main__":
    test_normalize_header_strips_whitespace_and_uppercases()
    test_match_field_exact_single_line()
    test_match_field_multiline_header_checks_each_line()
    test_match_field_fuzzy_matches_substring_with_bullet_prefix()
    test_parse_number_handles_currency_and_stray_spaces()
    print("ALL PASSED")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ModuleNotFoundError: No module named 'pdf_item_parser'`

- [ ] **Step 3: Write the implementation**

Create `expense_form_app/pdf_item_parser.py`:

```python
import re

HEADER_SYNONYMS = {
    "name": ["품명", "품 명", "공사명/품명", "물품명", "ITEM"],
    "spec": ["규격", "규 격", "SIZE", "형식", "규격/색상", "사양"],
    "unit": ["단위", "단 위", "UNIT"],
    "qty": ["수량", "수 량", "Q'TY", "QTY"],
    "price": ["단가", "단 가", "UNIT PRICE"],
}

_NUMBER_RE = re.compile(r"[0-9][0-9,.\s]*[0-9]|[0-9]")


def normalize_header(text):
    if text is None:
        return ""
    text = str(text).replace("\n", " ")
    text = re.sub(r"\s+", "", text)
    return text.strip().upper()


def match_field(header_text):
    if not header_text:
        return None
    for line in str(header_text).split("\n"):
        normalized = normalize_header(line)
        if not normalized:
            continue
        for field, synonyms in HEADER_SYNONYMS.items():
            for syn in synonyms:
                if normalize_header(syn) == normalized:
                    return field
    return None


def match_field_fuzzy(label_text):
    normalized = normalize_header(label_text)
    if not normalized:
        return None
    best_field, best_len = None, 0
    for field, synonyms in HEADER_SYNONYMS.items():
        for syn in synonyms:
            syn_norm = normalize_header(syn)
            if syn_norm and syn_norm in normalized and len(syn_norm) > best_len:
                best_field, best_len = field, len(syn_norm)
    return best_field


def parse_number(text):
    if text is None:
        return None
    cleaned = str(text).replace("₩", "").replace("원", "")
    match = _NUMBER_RE.search(cleaned)
    if not match:
        return None
    token = re.sub(r"\s+", "", match.group(0)).replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: 5 `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: add PDF item parser text/number normalization helpers"
```

---

### Task 2: Header-row detection & column mapping

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Consumes: `match_field` (Task 1).
- Produces: `find_header_row(table, max_scan=5) -> (int|None, int)`, `score_table(table) -> int`, `map_table_columns(table) -> {"columns": dict[str, list[int]], "data_start": int} | None`. Task 3 consumes `map_table_columns`'s return value; the orchestrator (Task 9) consumes `score_table` to pick the best table on a page.

Real sample quirk this must handle: in `견적서_한수_근권부.pdf`, `pdfplumber.extract_tables()` returns the actual column header (`['No', '품 명', '규 격', ...]`) as **row index 1**, not row 0 — row 0 is a "합계금액 안내문" summary line that got merged into the same table. So the header must be found by scanning, not assumed to be row 0.

- [ ] **Step 1: Write the failing tests**

Add to `expense_form_app/test_pdf_item_parser.py` (keep existing tests, add these, update the import line and the `__main__` block):

```python
from pdf_item_parser import (
    normalize_header, match_field, match_field_fuzzy, parse_number,
    find_header_row, score_table, map_table_columns,
)
```

```python
def test_find_header_row_at_index_zero():
    table = [
        ["품명", "수량", "단가"],
        ["볼트", "10", "1000"],
    ]
    idx, score = find_header_row(table)
    assert idx == 0
    assert score == 3
    print("OK: test_find_header_row_at_index_zero")


def test_find_header_row_scans_past_summary_row():
    table = [
        ["합계금액 안내문", None, None],
        ["No", "품 명", "규 격", "단위", "수량", "단 가", "금 액"],
        ["1", "볼트", "M12", "EA", "10", "1000", "10000"],
    ]
    idx, score = find_header_row(table)
    assert idx == 1
    assert score == 5
    print("OK: test_find_header_row_scans_past_summary_row")


def test_score_table_counts_matched_fields():
    assert score_table([["품명", "수량", "단가"]]) == 3
    assert score_table([["회 사 명", "값"]]) == 0
    assert score_table([]) == 0
    print("OK: test_score_table_counts_matched_fields")


def test_map_table_columns_basic():
    table = [
        ["품명", "규격", "단위", "수량", "단가", "비고"],
        ["볼트", "M12", "EA", "10", "1000", ""],
    ]
    result = map_table_columns(table)
    assert result["data_start"] == 1
    assert result["columns"] == {"name": [0], "spec": [1], "unit": [2], "qty": [3], "price": [4]}
    print("OK: test_map_table_columns_basic")


def test_map_table_columns_finds_header_not_at_row_zero():
    table = [
        ["합계금액 안내문", None, None],
        ["품명", "수량", "단가"],
        ["볼트", "10", "1000"],
    ]
    result = map_table_columns(table)
    assert result["data_start"] == 2
    assert result["columns"]["name"] == [0]
    print("OK: test_map_table_columns_finds_header_not_at_row_zero")


def test_map_table_columns_detects_duplicate_price_header():
    table = [
        ["품 명", "형식", "수 량", "단가", "단가", "납기"],
        ["DR100GF", "", "2", "520000", "1040000", "2-3일"],
    ]
    result = map_table_columns(table)
    assert result["columns"]["price"] == [3, 4]
    print("OK: test_map_table_columns_detects_duplicate_price_header")


def test_map_table_columns_returns_none_without_name_column():
    table = [["회 사 명", "주식회사 쉘파스페이스"]]
    assert map_table_columns(table) is None
    print("OK: test_map_table_columns_returns_none_without_name_column")


def test_map_table_columns_returns_none_without_qty_or_price():
    table = [["품명", "규격", "단위"], ["볼트", "M12", "EA"]]
    assert map_table_columns(table) is None
    print("OK: test_map_table_columns_returns_none_without_qty_or_price")
```

Update the `if __name__ == "__main__":` block to call all new test functions before `print("ALL PASSED")`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'find_header_row' from 'pdf_item_parser'`

- [ ] **Step 3: Write the implementation**

Append to `expense_form_app/pdf_item_parser.py`:

```python
def find_header_row(table, max_scan=5):
    best_idx, best_score = None, 0
    for idx, row in enumerate(table[:max_scan]):
        score = sum(1 for cell in row if match_field(cell))
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx, best_score


def score_table(table):
    if not table:
        return 0
    _, score = find_header_row(table)
    return score


def map_table_columns(table):
    if not table:
        return None
    header_idx, _ = find_header_row(table)
    if header_idx is None:
        return None
    columns = {}
    for idx, cell in enumerate(table[header_idx]):
        field = match_field(cell)
        if field:
            columns.setdefault(field, []).append(idx)
    if "name" not in columns or ("qty" not in columns and "price" not in columns):
        return None
    return {"columns": columns, "data_start": header_idx + 1}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: detect header row and map table columns for PDF item parsing"
```

---

### Task 3: Row extraction from a mapped table

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Consumes: the `{"columns": ..., "data_start": ...}` shape from `map_table_columns` (Task 2).
- Produces: `extract_items_from_table(table, mapping) -> list[dict]`, where each dict has keys `name` (str), `spec` (str), `unit` (str), `qty_raw` (str), `price_raws` (list[str], length 1 or 2). Task 4 consumes this list directly.

- [ ] **Step 1: Write the failing test**

Add to `expense_form_app/test_pdf_item_parser.py` (add to import line: `extract_items_from_table`):

```python
def test_extract_items_from_table_basic():
    table = [
        ["품명", "규격", "단위", "수량", "단가"],
        ["볼트", "M12", "EA", "10", "1,000"],
        ["", "", "", "", ""],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert rows == [
        {"name": "볼트", "spec": "M12", "unit": "EA", "qty_raw": "10", "price_raws": ["1,000"]},
    ]
    print("OK: test_extract_items_from_table_basic")


def test_extract_items_from_table_keeps_both_duplicate_price_columns():
    table = [
        ["품 명", "형식", "수 량", "단가", "단가"],
        ["DR100GF", "", "2", "520000", "1040000"],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert rows[0]["price_raws"] == ["520000", "1040000"]
    print("OK: test_extract_items_from_table_keeps_both_duplicate_price_columns")


def test_extract_items_from_table_skips_rows_without_name():
    table = [
        ["품명", "수량", "단가"],
        [None, "1", "100"],
        ["볼트", "10", "1000"],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert len(rows) == 1
    assert rows[0]["name"] == "볼트"
    print("OK: test_extract_items_from_table_skips_rows_without_name")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'extract_items_from_table'`

- [ ] **Step 3: Write the implementation**

Append to `expense_form_app/pdf_item_parser.py`:

```python
def extract_items_from_table(table, mapping):
    columns = mapping["columns"]

    def first_col(field):
        indices = columns.get(field)
        return indices[0] if indices else None

    name_col = first_col("name")
    spec_col = first_col("spec")
    unit_col = first_col("unit")
    qty_col = first_col("qty")
    price_cols = columns.get("price", [])

    def cell(row, col):
        if col is None or col >= len(row):
            return ""
        value = row[col]
        return value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())

    rows = []
    for raw_row in table[mapping["data_start"]:]:
        name = cell(raw_row, name_col)
        if not name:
            continue
        rows.append({
            "name": name,
            "spec": cell(raw_row, spec_col),
            "unit": cell(raw_row, unit_col),
            "qty_raw": cell(raw_row, qty_col),
            "price_raws": [cell(raw_row, c) for c in price_cols],
        })
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: extract raw item rows from a mapped PDF table"
```

---

### Task 4: Duplicate price-column disambiguation

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Consumes: `parse_number` (Task 1), the row dicts produced by `extract_items_from_table` (Task 3).
- Produces: `resolve_duplicate_price_columns(rows) -> list[dict]`, where each output dict has keys `name`, `spec`, `unit`, `qty` (float|None), `price` (float|None). Task 5 and Task 6 consume this list.

Rule (from the design doc): when a row has two price candidates (e.g. `한열사_견적서_북미.pdf`'s duplicated "단가" header), assume the first is unit price and the second is the line amount, and confirm by checking whether `qty * price ≈ amount`; swap if the second candidate fits better; if neither fits (or qty is unknown), default to the first candidate.

- [ ] **Step 1: Write the failing test**

Add to `expense_form_app/test_pdf_item_parser.py` (add `resolve_duplicate_price_columns` to the import):

```python
def test_resolve_single_price_column():
    rows = [{"name": "볼트", "spec": "M12", "unit": "EA", "qty_raw": "10", "price_raws": ["1,000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved == [{"name": "볼트", "spec": "M12", "unit": "EA", "qty": 10.0, "price": 1000.0}]
    print("OK: test_resolve_single_price_column")


def test_resolve_duplicate_price_picks_column_matching_qty_times_price():
    rows = [{"name": "DR100GF", "spec": "", "unit": "", "qty_raw": "2", "price_raws": ["520000", "1040000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved[0]["price"] == 520000.0
    assert resolved[0]["qty"] == 2.0
    print("OK: test_resolve_duplicate_price_picks_column_matching_qty_times_price")


def test_resolve_duplicate_price_handles_swapped_columns():
    rows = [{"name": "X", "spec": "", "unit": "", "qty_raw": "2", "price_raws": ["1040000", "520000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved[0]["price"] == 520000.0
    print("OK: test_resolve_duplicate_price_handles_swapped_columns")


def test_resolve_duplicate_price_defaults_to_first_when_qty_missing():
    rows = [{"name": "X", "spec": "", "unit": "", "qty_raw": "", "price_raws": ["520000", "1040000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved[0]["price"] == 520000.0
    assert resolved[0]["qty"] is None
    print("OK: test_resolve_duplicate_price_defaults_to_first_when_qty_missing")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'resolve_duplicate_price_columns'`

- [ ] **Step 3: Write the implementation**

Append to `expense_form_app/pdf_item_parser.py`:

```python
def _pick_price(qty, price_raws):
    values = [parse_number(v) for v in price_raws]
    if len(values) <= 1:
        return values[0] if values else None
    first, second = values[0], values[1]
    if qty and first is not None and second is not None:
        if abs(first * qty - second) <= max(1.0, second * 0.01):
            return first
        if abs(second * qty - first) <= max(1.0, first * 0.01):
            return second
    return first if first is not None else second


def resolve_duplicate_price_columns(rows):
    resolved = []
    for row in rows:
        qty = parse_number(row["qty_raw"])
        resolved.append({
            "name": row["name"],
            "spec": row["spec"],
            "unit": row["unit"],
            "qty": qty,
            "price": _pick_price(qty, row["price_raws"]),
        })
    return resolved
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: disambiguate duplicate price columns using qty*price match"
```

---

### Task 5: Summary/footer row cleanup

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Consumes: the resolved-row dicts from `resolve_duplicate_price_columns` (Task 4).
- Produces: `clean_item_rows(rows) -> list[dict]` (same shape, filtered). Task 6's `apply_hierarchical_prefix` and Task 9's orchestrator both run this before further processing.

Rule: drop rows whose `name` contains one of the known summary/footer keywords (합계, 소계, 이하, 총액, TOTAL, SUB TOTAL, TAX, REMARK) — these are table footer lines like "합 계", "** 이하여백 **", "Remark", "Sub Total", "Total", "Tax" that `pdfplumber` sometimes keeps as data rows.

- [ ] **Step 1: Write the failing test**

Add to `expense_form_app/test_pdf_item_parser.py` (add `clean_item_rows` to the import):

```python
def test_clean_item_rows_drops_summary_and_footer_rows():
    rows = [
        {"name": "볼트", "spec": "", "unit": "EA", "qty": 10.0, "price": 1000.0},
        {"name": "합 계", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "** 이하여백 **", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "Remark", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "Sub Total", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "너트", "spec": "", "unit": "EA", "qty": 5.0, "price": 500.0},
    ]
    cleaned = clean_item_rows(rows)
    assert [r["name"] for r in cleaned] == ["볼트", "너트"]
    print("OK: test_clean_item_rows_drops_summary_and_footer_rows")


def test_clean_item_rows_keeps_category_like_rows():
    rows = [{"name": "HONEYWELL", "spec": "", "unit": "", "qty": None, "price": None}]
    cleaned = clean_item_rows(rows)
    assert [r["name"] for r in cleaned] == ["HONEYWELL"]
    print("OK: test_clean_item_rows_keeps_category_like_rows")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'clean_item_rows'`

- [ ] **Step 3: Write the implementation**

Append to `expense_form_app/pdf_item_parser.py`:

```python
SUMMARY_KEYWORDS = ["합계", "소계", "이하", "총액", "TOTAL", "SUB TOTAL", "TAX", "REMARK"]


def clean_item_rows(rows):
    cleaned = []
    for row in rows:
        normalized_name = normalize_header(row["name"])
        if any(normalize_header(keyword) in normalized_name for keyword in SUMMARY_KEYWORDS):
            continue
        cleaned.append(row)
    return cleaned
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: drop summary/footer rows from parsed PDF items"
```

---

### Task 6: Hierarchical category-row prefixing

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Consumes: the cleaned rows from `clean_item_rows` (Task 5).
- Produces: `apply_hierarchical_prefix(rows) -> list[dict]` (same shape, category rows removed, subsequent rows' `name` prefixed). Task 9's orchestrator runs this last, right before returning `items`.

Rule (from the design doc, confirmed with the user): a row counts as a category header when `spec`, `unit`, `qty`, and `price` are ALL empty/None. It is removed from the output; every following row (until the next category header) gets `name = f"{category_name} - {name}"`.

- [ ] **Step 1: Write the failing test**

Add to `expense_form_app/test_pdf_item_parser.py` (add `apply_hierarchical_prefix` to the import):

```python
def test_apply_hierarchical_prefix_prefixes_following_rows():
    rows = [
        {"name": "온실제어 INTERFACE", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "외함", "spec": "옥내형", "unit": "EA", "qty": 1.0, "price": 500000.0},
        {"name": "누전차단기", "spec": "EBS33~32", "unit": "식", "qty": 1.0, "price": 250000.0},
        {"name": "제어 CONTROLLER", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "PLC+TOUCH", "spec": "DR16S", "unit": "SET", "qty": 2.0, "price": 1700000.0},
    ]
    result = apply_hierarchical_prefix(rows)
    assert [r["name"] for r in result] == [
        "온실제어 INTERFACE - 외함",
        "온실제어 INTERFACE - 누전차단기",
        "제어 CONTROLLER - PLC+TOUCH",
    ]
    print("OK: test_apply_hierarchical_prefix_prefixes_following_rows")


def test_apply_hierarchical_prefix_passes_through_flat_rows_unchanged():
    rows = [
        {"name": "볼트", "spec": "M12", "unit": "EA", "qty": 10.0, "price": 1000.0},
        {"name": "너트", "spec": "M12", "unit": "EA", "qty": 5.0, "price": 500.0},
    ]
    result = apply_hierarchical_prefix(rows)
    assert result == rows
    print("OK: test_apply_hierarchical_prefix_passes_through_flat_rows_unchanged")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'apply_hierarchical_prefix'`

- [ ] **Step 3: Write the implementation**

Append to `expense_form_app/pdf_item_parser.py`:

```python
def apply_hierarchical_prefix(rows):
    result = []
    prefix = None
    for row in rows:
        is_category = not row["spec"] and not row["unit"] and row["qty"] is None and row["price"] is None
        if is_category:
            prefix = row["name"]
            continue
        if prefix:
            row = dict(row)
            row["name"] = f"{prefix} - {row['name']}"
        result.append(row)
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: prefix hierarchical category rows onto their sub-items"
```

---

### Task 7: Paragraph label:value fallback

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Consumes: `match_field_fuzzy`, `parse_number` (Task 1).
- Produces: `extract_paragraph_fallback(text) -> dict | None`, returning one item dict (`name`/`spec`/`unit`/`qty`/`price`) or `None`. Task 9's orchestrator calls this only when no item table was found on the page.

This handles quotes like `견적서_코랄_수확후.pdf`, which has no item table at all — only lines like `ㅇ. 품 명 : AL- Ingot` and `ㅇ. 단 가 : 6,250,000 원/MT (가단가)`.

- [ ] **Step 1: Write the failing test**

Add to `expense_form_app/test_pdf_item_parser.py` (add `extract_paragraph_fallback` to the import):

```python
def test_extract_paragraph_fallback_finds_labelled_values():
    text = (
        "ㅇ. 품 명 : AL- Ingot\n"
        "ㅇ. 출 고 일 : 2026년 6월 1일\n"
        "ㅇ. 수 량 : 1.950 MT\n"
        "ㅇ. 단 가 : 6,250,000 원/MT (가단가)\n"
        "ㅇ. 공 급 가 액 : 12,187,500 원\n"
        "ㅇ. 부 가 세 : 1,218,750 원\n"
    )
    item = extract_paragraph_fallback(text)
    assert item["name"] == "AL- Ingot"
    assert item["qty"] == 1.95
    assert item["price"] == 6250000.0
    assert item["spec"] == ""
    assert item["unit"] == ""
    print("OK: test_extract_paragraph_fallback_finds_labelled_values")


def test_extract_paragraph_fallback_returns_none_without_name():
    text = "문서번호 : KOR-260601-07\n수 신 : ㈜그린플러스\n"
    assert extract_paragraph_fallback(text) is None
    print("OK: test_extract_paragraph_fallback_returns_none_without_name")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'extract_paragraph_fallback'`

- [ ] **Step 3: Write the implementation**

Append to `expense_form_app/pdf_item_parser.py`:

```python
def extract_paragraph_fallback(text):
    found = {}
    for line in text.split("\n"):
        sep = ":" if ":" in line else ("：" if "：" in line else None)
        if sep is None:
            continue
        label, _, value = line.partition(sep)
        field = match_field_fuzzy(label)
        if not field or field in found:
            continue
        value = value.strip()
        if value:
            found[field] = value
    if "name" not in found:
        return None
    return {
        "name": found.get("name", ""),
        "spec": found.get("spec", ""),
        "unit": found.get("unit", ""),
        "qty": parse_number(found.get("qty")),
        "price": parse_number(found.get("price")),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: add paragraph label:value fallback for table-less PDF quotes"
```

---

### Task 8: Page image rendering

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Produces: `render_page_images(pdf_bytes, zoom=1.5) -> list[str]` (one base64-encoded PNG string per page). Task 9's orchestrator includes this output as `page_images` in its return value; the frontend (Task 11) renders these as `<img src="data:image/png;base64,...">`.

- [ ] **Step 1: Install the new dependencies**

Run: `python -m pip install pdfplumber pymupdf`
Expected: both install successfully (import name for pymupdf is `fitz`).

- [ ] **Step 2: Write the failing test**

Add to `expense_form_app/test_pdf_item_parser.py`:

```python
import base64

import fitz

from pdf_item_parser import render_page_images
```

```python
def test_render_page_images_returns_one_png_per_page():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    images = render_page_images(pdf_bytes)

    assert len(images) == 2
    for img_b64 in images:
        raw = base64.b64decode(img_b64)
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    print("OK: test_render_page_images_returns_one_png_per_page")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'render_page_images'`

- [ ] **Step 4: Write the implementation**

Add near the top of `expense_form_app/pdf_item_parser.py` (with the other imports):

```python
import base64

import fitz
```

Append to `expense_form_app/pdf_item_parser.py`:

```python
def render_page_images(pdf_bytes, zoom=1.5):
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    matrix = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        images.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
    doc.close()
    return images
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` lines then `ALL PASSED`

- [ ] **Step 6: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: render PDF pages to base64 PNG previews"
```

---

### Task 9: Top-level orchestrator (`parse_pdf_items`)

**Files:**
- Modify: `expense_form_app/pdf_item_parser.py`
- Modify: `expense_form_app/test_pdf_item_parser.py`

**Interfaces:**
- Consumes: every function from Tasks 1–8.
- Produces: `parse_pdf_items(pdf_bytes) -> {"items": list[dict], "page_images": list[str], "warnings": list[str]}`. Task 10's Flask route calls this directly and returns its result as JSON.

This wires the whole pipeline together: render preview images (always), find the best-scoring table across all pages, map its columns, extract/resolve/clean/prefix its rows — or, if no usable table was found, fall back to the paragraph label:value scan.

- [ ] **Step 1: Write the failing tests**

Add to `expense_form_app/test_pdf_item_parser.py`:

```python
import os

from pdf_item_parser import parse_pdf_items

SAMPLE_DIR = r"D:\claude_personal\setting_01\PDF_read"


def _load_sample(filename):
    with open(os.path.join(SAMPLE_DIR, filename), "rb") as f:
        return f.read()
```

```python
def test_parse_pdf_items_normal_table_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_normal_table_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_한수_근권부.pdf"))
    names = [it["name"] for it in result["items"]]
    assert names == ["무선 온습도 데이터 로거", "CO2 데이터 로거"]
    assert result["items"][0]["spec"] == "TR-72"
    assert result["items"][0]["unit"] == "SET"
    assert result["items"][0]["qty"] == 13.0
    assert result["items"][0]["price"] == 660000.0
    assert result["warnings"] == []
    assert len(result["page_images"]) == 1
    print("OK: test_parse_pdf_items_normal_table_case")


def test_parse_pdf_items_hierarchical_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_hierarchical_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("2. 견적서(제어)-온실제어장치-26.05_수정.pdf"))
    names = [it["name"] for it in result["items"]]
    assert "온실제어 INTERFACE - 외함" in names
    assert "제어 CONTROLLER - PLC+TOUCH" in names
    assert "배선 자재 - 전선(F-CV)" in names
    print("OK: test_parse_pdf_items_hierarchical_case")


def test_parse_pdf_items_duplicate_header_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_duplicate_header_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("한열사_견적서_북미.pdf"))
    by_name = {it["name"]: it for it in result["items"]}
    assert by_name["HONEYWELL - DR100GF"]["price"] == 520000.0
    assert by_name["HONEYWELL - DR100GF"]["qty"] == 2.0
    print("OK: test_parse_pdf_items_duplicate_header_case")


def test_parse_pdf_items_no_table_fallback_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_no_table_fallback_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_코랄_수확후.pdf"))
    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "AL- Ingot"
    assert result["items"][0]["price"] == 6250000.0
    assert result["warnings"]
    print("OK: test_parse_pdf_items_no_table_fallback_case")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: `ImportError: cannot import name 'parse_pdf_items'`

- [ ] **Step 3: Write the implementation**

Add near the top of `expense_form_app/pdf_item_parser.py`:

```python
import io

import pdfplumber
```

Append to `expense_form_app/pdf_item_parser.py`:

```python
def _find_best_table(pdf):
    best_table, best_score = None, 0
    for page in pdf.pages:
        for table in page.extract_tables():
            score = score_table(table)
            if score > best_score:
                best_table, best_score = table, score
    return best_table


def parse_pdf_items(pdf_bytes):
    warnings = []
    page_images = render_page_images(pdf_bytes)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        best_table = _find_best_table(pdf)
        mapping = map_table_columns(best_table) if best_table else None

        if mapping:
            raw_rows = extract_items_from_table(best_table, mapping)
            resolved_rows = resolve_duplicate_price_columns(raw_rows)
            cleaned_rows = clean_item_rows(resolved_rows)
            items = apply_hierarchical_prefix(cleaned_rows)
        else:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            fallback_item = extract_paragraph_fallback(full_text)
            if fallback_item:
                items = [fallback_item]
                warnings.append("표를 찾지 못해 일부 항목만 인식했습니다. 나머지는 직접 입력해주세요.")
            else:
                items = []
                warnings.append("표를 인식하지 못했습니다. 직접 입력해주세요.")

    return {"items": items, "page_images": page_images, "warnings": warnings}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_pdf_item_parser.py`
Expected: all `OK:` (or `SKIP:` if `D:\claude_personal\setting_01\PDF_read` doesn't exist on the machine running this) lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/pdf_item_parser.py expense_form_app/test_pdf_item_parser.py
git commit -m "feat: wire up parse_pdf_items orchestrator for PDF quote item import"
```

---

### Task 10: Flask route `POST /parse_pdf`

**Files:**
- Modify: `expense_form_app/app.py`
- Create: `expense_form_app/test_parse_pdf_route.py`

**Interfaces:**
- Consumes: `parse_pdf_items` (Task 9).
- Produces: HTTP route `POST /parse_pdf` returning JSON `{"items": [...], "page_images": [...], "warnings": [...]}`. Task 11's frontend JS calls this route with `fetch('/parse_pdf', {method: 'POST', body: formData})` where `formData` has a `file` field holding the selected PDF.

- [ ] **Step 1: Write the failing test**

Create `expense_form_app/test_parse_pdf_route.py`, following the same `app_module.app.test_client()` pattern as `test_app_refresh_route.py`:

```python
import io

import fitz

import app as app_module


def _tiny_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "품명 규격 단위 수량 단가")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_parse_pdf_route_returns_json_with_expected_keys():
    client = app_module.app.test_client()
    data = {"file": (io.BytesIO(_tiny_pdf_bytes()), "quote.pdf")}
    resp = client.post("/parse_pdf", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {"items", "page_images", "warnings"}
    assert isinstance(body["items"], list)
    assert len(body["page_images"]) == 1
    print("OK: test_parse_pdf_route_returns_json_with_expected_keys")


def test_parse_pdf_route_requires_file():
    client = app_module.app.test_client()
    resp = client.post("/parse_pdf", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    print("OK: test_parse_pdf_route_requires_file")


if __name__ == "__main__":
    test_parse_pdf_route_returns_json_with_expected_keys()
    test_parse_pdf_route_requires_file()
    print("ALL PASSED")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd expense_form_app && python test_parse_pdf_route.py`
Expected: 404 status code assertion failure (route doesn't exist yet)

- [ ] **Step 3: Write the implementation**

In `expense_form_app/app.py`, update the import line:

```python
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for
```

Add near the top with the other local imports:

```python
from pdf_item_parser import parse_pdf_items
```

Add this route (e.g. right after the `refresh_read_seed` route):

```python
@app.route("/parse_pdf", methods=["POST"])
def parse_pdf():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "파일이 없습니다."}), 400
    result = parse_pdf_items(file.read())
    return jsonify(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd expense_form_app && python test_parse_pdf_route.py`
Expected: both `OK:` lines then `ALL PASSED`

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/app.py expense_form_app/test_parse_pdf_route.py
git commit -m "feat: add POST /parse_pdf route for PDF quote item import"
```

---

### Task 11: Frontend — upload button, review modal, apply-choice

**Files:**
- Modify: `expense_form_app/templates/index.html`

**Interfaces:**
- Consumes: `POST /parse_pdf` (Task 10), returning `{"items": [{"name","spec","unit","qty","price"}, ...], "page_images": [...], "warnings": [...]}`.
- Consumes the existing `addRow(prefill)` function and `itemsBody` element already defined in this file (see lines 297, 318–337) — reuse them exactly as-is, do not redefine.

Behavior (per the approved design): a button above the item table opens a file picker; on selection, the PDF is uploaded and a same-page modal opens showing the PDF pages (left) next to an editable draft table (right, pre-filled from the parsed items) and any warnings. Clicking "표에 적용" shows two buttons — **삭제 후 작성** (clear existing rows, then add the draft rows) and **유지하고 추가** (just add the draft rows after whatever is already there) — either closes the modal and updates the totals.

- [ ] **Step 1: Add the upload button next to "+ 품목 추가"**

In `expense_form_app/templates/index.html`, replace:

```html
      <div class="row-buttons">
        <button type="button" class="small" id="addRowBtn">+ 품목 추가</button>
      </div>
```

with:

```html
      <div class="row-buttons">
        <button type="button" class="small" id="addRowBtn">+ 품목 추가</button>
        <button type="button" class="small" id="pdfUploadBtn">📄 PDF로 품목 불러오기</button>
        <input type="file" id="pdfFileInput" accept="application/pdf" style="display:none">
      </div>
```

- [ ] **Step 2: Add the modal markup**

Right before the closing `</div>` of `<div class="card">` (i.e. right after the `</form>` closing tag), add:

```html
  <div id="pdfModalOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:100;">
    <div style="background:#fff;max-width:1000px;margin:40px auto;border-radius:10px;padding:20px 24px;max-height:85vh;overflow:auto;">
      <h2 style="font-size:16px;margin:0 0 10px;">PDF에서 품목 불러오기</h2>
      <div id="pdfWarnings" style="color:#b42318;font-size:12.5px;margin-bottom:10px;"></div>
      <div style="display:flex;gap:16px;">
        <div id="pdfImagePane" style="flex:1;overflow:auto;max-height:60vh;border:1px solid var(--border);border-radius:6px;padding:6px;"></div>
        <div style="flex:1;overflow:auto;max-height:60vh;">
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
              <tr>
                <th style="border:1px solid var(--border);padding:6px;">품목</th>
                <th style="border:1px solid var(--border);padding:6px;">규격</th>
                <th style="border:1px solid var(--border);padding:6px;">단위</th>
                <th style="border:1px solid var(--border);padding:6px;">수량</th>
                <th style="border:1px solid var(--border);padding:6px;">단가</th>
                <th style="border:1px solid var(--border);padding:6px;"></th>
              </tr>
            </thead>
            <tbody id="pdfDraftBody"></tbody>
          </table>
        </div>
      </div>
      <div id="pdfApplyChoice" style="display:none;margin-top:14px;padding-top:14px;border-top:1px solid var(--border);">
        <p style="font-size:13px;margin:0 0 8px;">기존에 입력된 품목이 있습니다. 어떻게 반영할까요?</p>
        <button type="button" class="small" id="pdfReplaceBtn">① 기존 삭제 후 업로드 내용으로 작성</button>
        <button type="button" class="small" id="pdfAppendBtn">② 기존 유지 후 업로드 내용 추가</button>
      </div>
      <div class="row-buttons" style="margin-top:14px;">
        <button type="button" class="small" id="pdfCancelBtn">취소</button>
        <button type="button" class="small" id="pdfApplyBtn">표에 적용</button>
      </div>
    </div>
  </div>
```

- [ ] **Step 3: Add the modal JavaScript**

At the end of the `<script>` block in `expense_form_app/templates/index.html` (right before the closing `</script>`), add:

```javascript
const pdfModalOverlay = document.getElementById('pdfModalOverlay');
const pdfDraftBody = document.getElementById('pdfDraftBody');
const pdfImagePane = document.getElementById('pdfImagePane');
const pdfWarnings = document.getElementById('pdfWarnings');
const pdfApplyChoice = document.getElementById('pdfApplyChoice');

function addDraftRow(prefill) {
  prefill = prefill || {};
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="d-name" value="${prefill.name || ''}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="d-spec" value="${prefill.spec || ''}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="d-unit" value="${prefill.unit || ''}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><input type="number" class="d-qty" value="${prefill.qty ?? ''}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><input type="number" class="d-price" value="${prefill.price ?? ''}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><button type="button" class="small removeDraftBtn">삭제</button></td>
  `;
  pdfDraftBody.appendChild(tr);
  tr.querySelector('.removeDraftBtn').addEventListener('click', () => tr.remove());
}

function openPdfModal(result) {
  pdfDraftBody.innerHTML = '';
  pdfImagePane.innerHTML = '';
  pdfWarnings.textContent = (result.warnings || []).join(' ');
  result.page_images.forEach(b64 => {
    const img = document.createElement('img');
    img.src = 'data:image/png;base64,' + b64;
    img.style.width = '100%';
    img.style.marginBottom = '8px';
    pdfImagePane.appendChild(img);
  });
  (result.items || []).forEach(item => addDraftRow(item));
  pdfApplyChoice.style.display = 'none';
  pdfModalOverlay.style.display = 'block';
}

function closePdfModal() {
  pdfModalOverlay.style.display = 'none';
  document.getElementById('pdfFileInput').value = '';
}

function collectDraftItems() {
  return [...pdfDraftBody.querySelectorAll('tr')].map(tr => ({
    name: tr.querySelector('.d-name').value,
    spec: tr.querySelector('.d-spec').value,
    unit: tr.querySelector('.d-unit').value,
    qty: parseFloat(tr.querySelector('.d-qty').value) || 0,
    price: parseFloat(tr.querySelector('.d-price').value) || 0,
  })).filter(item => item.name.trim());
}

function applyDraftItems(mode) {
  const draftItems = collectDraftItems();
  if (mode === 'replace') {
    itemsBody.innerHTML = '';
  }
  draftItems.forEach(item => addRow(item));
  closePdfModal();
  recalc();
}

document.getElementById('pdfUploadBtn').addEventListener('click', () => {
  document.getElementById('pdfFileInput').click();
});

document.getElementById('pdfFileInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/parse_pdf', { method: 'POST', body: fd });
  if (!res.ok) {
    alert('PDF 인식에 실패했습니다.');
    return;
  }
  const result = await res.json();
  openPdfModal(result);
});

document.getElementById('pdfCancelBtn').addEventListener('click', closePdfModal);

document.getElementById('pdfApplyBtn').addEventListener('click', () => {
  const hasExisting = itemsBody.querySelectorAll('tr').length > 0
    && [...itemsBody.querySelectorAll('tr')].some(tr => tr.querySelector('.f-name').value.trim());
  if (hasExisting) {
    pdfApplyChoice.style.display = 'block';
  } else {
    applyDraftItems('append');
  }
});

document.getElementById('pdfReplaceBtn').addEventListener('click', () => applyDraftItems('replace'));
document.getElementById('pdfAppendBtn').addEventListener('click', () => applyDraftItems('append'));
```

- [ ] **Step 4: Manually verify in the browser**

Run: `cd expense_form_app && python app.py`

Then in the opened browser:
1. Click "📄 PDF로 품목 불러오기", select `D:\claude_personal\setting_01\PDF_read\견적서_한수_근권부.pdf`.
2. Confirm the modal opens with the PDF page image on the left and 2 draft rows (무선 온습도 데이터 로거 / CO2 데이터 로거) on the right.
3. Click "표에 적용" — since the main table already has one blank default row, confirm the "① / ②" choice buttons appear.
4. Click "① 기존 삭제 후 업로드 내용으로 작성" — confirm the main item table now shows exactly the 2 rows from the PDF and totals recalculate.
5. Repeat and click "② 기존 유지 후 업로드 내용 추가" instead — confirm the 2 PDF rows are appended after whatever was already in the table.

Expected: both apply modes work as described, no console errors.

- [ ] **Step 5: Commit**

```bash
git add expense_form_app/templates/index.html
git commit -m "feat: add PDF item import button, review modal, and apply-choice UI"
```

---

### Task 12: Manual verification against all 8 real samples

**Files:** none (verification-only task)

**Interfaces:** none — this is the final sanity pass over Tasks 1–11 combined.

- [ ] **Step 1: Start the app**

Run: `cd expense_form_app && python app.py`

- [ ] **Step 2: Upload each of the remaining samples not already covered by automated tests**

For each of `2. 견적서.pdf`, `2. 견적서_세화볼트.pdf`, `2. 그린플러스_광센서_견적서.pdf`, `견적서_일신_북미.pdf` in `D:\claude_personal\setting_01\PDF_read`:
1. Upload it via "📄 PDF로 품목 불러오기".
2. Confirm the PDF image renders on the left.
3. Confirm the draft table on the right roughly matches the item rows visible in the PDF image (exact wording may need minor manual cleanup — that's expected and fine per the design; the goal is "close enough to edit", not pixel-perfect).
4. Apply with either mode and confirm the main table updates and totals recalculate correctly.

- [ ] **Step 3: Confirm graceful failure still reads clearly**

Upload `견적서_코랄_수확후.pdf` again through the actual UI (not just the unit test) and confirm the warning message ("표를 찾지 못해...") is visible in the modal and the one recovered row (AL- Ingot / 6,250,000) is editable.

- [ ] **Step 4: Run the full test suite one more time**

Run each of these from `expense_form_app/` and confirm every one prints `ALL PASSED` with no tracebacks:

```bash
python test_generator.py
python test_history_store_merge.py
python test_app_refresh_route.py
python test_template_banner.py
python test_column_layout.py
python test_item_table_layout.py
python test_read_seed.py
python test_pdf_item_parser.py
python test_parse_pdf_route.py
```

No commit for this task — it's verification only. If any step fails, go back to the relevant earlier task and fix it there (with a new commit), then re-run this task from Step 1.
