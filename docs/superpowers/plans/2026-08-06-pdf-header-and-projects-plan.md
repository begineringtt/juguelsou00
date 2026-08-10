# PDF 헤더 매핑 개선 + 업체명 자동 인식 + 과제 프리셋 정리/CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영문 헤더 견적서(예: `Description/Quantity/Unit/Price`)와 품목명 칸에 셀 경계가 없는 견적서도 품목이 정확히 인식되게 하고, PDF에서 거래처명(업체명)도 자동 인식하며, 과제 프리셋 목록을 10개로 정리하고 페이지 안에서 직접 추가/수정/삭제할 수 있게 한다.

**Architecture:** 백엔드는 `pdf_item_parser.py`(PDF 파싱), `history_store.py`(데이터 영속화), `app.py`(Flask 라우트) 3개 모듈에 기능을 추가한다. 프론트엔드는 `templates/index.html`의 인라인 JS를 확장해 서버와 fetch로 통신하며 페이지 새로고침 없이 갱신한다. 데이터는 `data/projects.json` 한 파일로 유지하되 각 항목에 `id`(안정적 식별자)와 `short_name`(축약어) 필드를 추가한다.

**Tech Stack:** Python 3 / Flask / pdfplumber / PyMuPDF(fitz) / 순수 JS(프레임워크 없음) / JSON 파일 저장소.

## Global Constraints

- 승인된 설계 문서: `docs/superpowers/specs/2026-08-05-pdf-header-and-projects-design.md` (모든 세부 규칙의 근거).
- 샘플 PDF는 git에 커밋하지 않는다 — 테스트는 `D:\claude_personal\setting_01\PDF_read` 로컬 경로를 참조하고, 폴더가 없으면 `if not os.path.isdir(SAMPLE_DIR): print("SKIP: ..."); return` 패턴으로 건너뛴다 (기존 `test_pdf_item_parser.py` 관례 그대로 따름).
- 테스트는 pytest가 아니라 `assert` + `print("OK: ...")` 함수를 만들고 `if __name__ == "__main__":` 블록에서 순서대로 호출하는 기존 관례를 따른다. 실행은 `python <파일명>.py`.
- 기존 8개 샘플 PDF에 대한 `test_pdf_item_parser.py` 테스트가 계속 통과해야 한다 (회귀 금지).
- 자사명(그린플러스) 오인식 방지: 업체명 인식 값이 "그린플러스"를 포함하면 채택하지 않는다.
- 모든 신규 UI 동작은 페이지 새로고침 없이 반영되어야 한다 (fetch 기반).

---

### Task 1: PDF 헤더 동의어 확장 (QUANTITY / PRICE) + 헤더 매칭 fuzzy fallback

**Files:**
- Modify: `pdf_item_parser.py:8-38` (`HEADER_SYNONYMS`, `match_field`)
- Test: `test_pdf_item_parser.py`

**Interfaces:**
- Consumes: 없음 (모듈 최상단 상수/함수 수정)
- Produces: `match_field(header_text)` — 이제 `"Quantity"` → `"qty"`, `"Price(￦/M2)"` → `"price"`, `"Amount(￦)"` → `None` 을 반환. 이후 태스크는 이 동작에 의존한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`test_pdf_item_parser.py`의 `test_match_field_recognizes_description_as_name` 함수 바로 아래에 다음 함수를 추가한다:

```python
def test_match_field_matches_quantity_and_bracketed_price_header():
    assert match_field("Quantity") == "qty"
    assert match_field("Price(￦/M2)") == "price"
    assert match_field("Amount(￦)") is None
    print("OK: test_match_field_matches_quantity_and_bracketed_price_header")
```

그리고 파일 맨 아래 `if __name__ == "__main__":` 블록 안, `test_match_field_recognizes_description_as_name()` 호출 바로 다음 줄에 `test_match_field_matches_quantity_and_bracketed_price_header()` 호출을 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python test_pdf_item_parser.py`
Expected: `AssertionError` (아직 `QUANTITY`/`PRICE` 동의어가 없어 `match_field("Quantity")`가 `None`을 반환하므로 실패).

- [ ] **Step 3: 최소 구현**

`pdf_item_parser.py`의 기존

```python
HEADER_SYNONYMS = {
    "name": ["품명", "품 명", "공사명/품명", "물품명", "ITEM", "DESCRIPTION"],
    "spec": ["규격", "규 격", "SIZE", "형식", "규격/색상", "사양"],
    "unit": ["단위", "단 위", "UNIT"],
    "qty": ["수량", "수 량", "Q'TY", "QTY"],
    "price": ["단가", "단 가", "UNIT PRICE"],
}
```

를 아래로 교체:

```python
HEADER_SYNONYMS = {
    "name": ["품명", "품 명", "공사명/품명", "물품명", "ITEM", "DESCRIPTION"],
    "spec": ["규격", "규 격", "SIZE", "형식", "규격/색상", "사양"],
    "unit": ["단위", "단 위", "UNIT"],
    "qty": ["수량", "수 량", "Q'TY", "QTY", "QUANTITY"],
    "price": ["단가", "단 가", "UNIT PRICE", "PRICE"],
}
```

그리고 기존

```python
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
```

를 아래로 교체 (정확히 일치하는 게 없을 때만 부분 포함 매칭으로 한번 더 시도):

```python
def match_field(header_text):
    if not header_text:
        return None
    lines = str(header_text).split("\n")
    for line in lines:
        normalized = normalize_header(line)
        if not normalized:
            continue
        for field, synonyms in HEADER_SYNONYMS.items():
            for syn in synonyms:
                if normalize_header(syn) == normalized:
                    return field
    for line in lines:
        field = match_field_fuzzy(line)
        if field:
            return field
    return None
```

(`match_field_fuzzy`는 같은 파일에 이미 정의되어 있음 — 파일 내 위치상 `match_field` 아래에 있지만, 파이썬은 호출 시점에 이름을 찾으므로 문제없다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_pdf_item_parser.py`
Expected: `ALL PASSED` (새 테스트 포함 전체 통과).

- [ ] **Step 5: 커밋**

```bash
git add pdf_item_parser.py test_pdf_item_parser.py
git commit -m "feat: recognize QUANTITY/PRICE English headers in PDF item parsing"
```

---

### Task 2: 품목명 칸이 표에서 통째로 누락되는 문제 복구 (좌표 기반 fallback)

**Files:**
- Modify: `pdf_item_parser.py:253-260` (`_find_best_table`)
- Test: `test_pdf_item_parser.py`

**Interfaces:**
- Consumes: Task 1의 `match_field`/`HEADER_SYNONYMS` (헤더가 살아나야 이후 컬럼 매핑이 성공함)
- Produces: `recover_blank_leading_column(table_obj, rows, page, col_index=0)` — 새 함수. `_find_best_table`이 내부적으로 사용. 이후 태스크는 이 함수 이름/시그니처에 의존하지 않음(내부 구현이므로 다른 모듈에서 직접 호출하지 않음).

**배경:** `견적서_20260721(그린플러스_IR Cut_8월).pdf`는 품목명(Description) 칸에 행 구분선이 없어서, pdfplumber의 선 기반 표 추출이 헤더 행과 모든 데이터 행에서 그 칸을 빈 값(`None`)으로 돌려준다. 다른 칸(수량/단위/단가/금액)은 정상 추출된다. 해결책은, 표의 각 행 실제 좌표(top/bottom)와 옆 칸(1번째 칸)의 왼쪽 x좌표를 이용해 그 칸의 x범위를 계산하고, 그 사각형 영역을 `page.crop(...)`해서 텍스트를 뽑아 빈 칸을 채우는 것이다. 이미 값이 있는 칸은 절대 건드리지 않으므로 기존에 정상 동작하던 표(8개 샘플)에는 영향이 없어야 한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`test_pdf_item_parser.py` 맨 위 import 구문은 그대로 두고 (이 테스트는 `parse_pdf_items`만 사용), `test_parse_pdf_items_no_table_fallback_case` 함수 바로 아래에 추가:

```python
def test_parse_pdf_items_recovers_borderless_name_column_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_recovers_borderless_name_column_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_20260721(그린플러스_IR Cut_8월).pdf"))
    items = result["items"]
    etfe_item = next((it for it in items if "ETFE 기재 적용" in it["name"]), None)
    assert etfe_item is not None
    assert etfe_item["unit"] == "days"
    assert etfe_item["qty"] == 2.0
    assert etfe_item["price"] == 6119375.0
    target_mix_item = next((it for it in items if "Target Mix" in it["name"]), None)
    assert target_mix_item is not None
    assert target_mix_item["unit"] == "㎡"
    assert target_mix_item["qty"] == 1300.0
    assert target_mix_item["price"] == 11000.0
    assert result["warnings"] == []
    print("OK: test_parse_pdf_items_recovers_borderless_name_column_case")
```

`if __name__ == "__main__":` 블록에서 `test_parse_pdf_items_no_table_fallback_case()` 호출 다음 줄에 `test_parse_pdf_items_recovers_borderless_name_column_case()` 호출을 추가한다.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python test_pdf_item_parser.py`
Expected: `AssertionError` (`etfe_item is not None` 에서 실패 — 현재 코드는 이 파일에서 품목을 0개 인식함).

- [ ] **Step 3: 최소 구현**

`pdf_item_parser.py`의 기존

```python
def _find_best_table(pdf):
    best_table, best_score = None, 0
    for page in pdf.pages:
        for table in page.extract_tables():
            score = score_table(table)
            if score > best_score:
                best_table, best_score = table, score
    return best_table
```

를 아래로 교체:

```python
def _blank_cell(value):
    return not (value and str(value).strip())


def recover_blank_leading_column(table_obj, rows, page, col_index=0):
    """일부 견적서는 품목명 칸에 행 구분선이 없어 pdfplumber가 그 칸의 텍스트를
    전부 놓친다 (헤더 포함 모든 행이 빈 값으로 나옴). 옆 칸(col_index+1)의 왼쪽
    x좌표와 각 행의 실제 y좌표(top/bottom)를 이용해 그 영역의 텍스트를 좌표
    기반으로 복구한다. 이미 값이 있는 칸은 건드리지 않는다."""
    if not rows or len(rows[0]) <= col_index + 1:
        return rows

    neighbor_lefts = [
        row_cells.cells[col_index + 1][0]
        for row_cells in table_obj.rows
        if len(row_cells.cells) > col_index + 1 and row_cells.cells[col_index + 1]
    ]
    if not neighbor_lefts:
        return rows

    right_x = min(neighbor_lefts)
    left_x = table_obj.bbox[0]
    if right_x - left_x < 10:
        return rows

    changed = False
    patched = []
    for row_cells, row_list in zip(table_obj.rows, rows):
        row_list = list(row_list)
        bbox = row_cells.bbox
        if _blank_cell(row_list[col_index]) and bbox is not None:
            crop = page.crop((left_x, bbox[1], right_x, bbox[3]))
            text = (crop.extract_text() or "").replace("\n", " ").strip()
            if text:
                row_list[col_index] = text
                changed = True
        patched.append(row_list)
    return patched if changed else rows


def _find_best_table(pdf):
    best_table, best_score = None, 0
    for page in pdf.pages:
        for table_obj in page.find_tables():
            rows = recover_blank_leading_column(table_obj, table_obj.extract(), page)
            score = score_table(rows)
            if score > best_score:
                best_table, best_score = rows, score
    return best_table
```

- [ ] **Step 4: 테스트 통과 확인 (신규 + 회귀)**

Run: `python test_pdf_item_parser.py`
Expected: `ALL PASSED` — 신규 테스트뿐 아니라 기존 8개 샘플 관련 테스트(`test_parse_pdf_items_normal_table_case`, `test_parse_pdf_items_hierarchical_case`, `test_parse_pdf_items_duplicate_header_case`, `test_parse_pdf_items_no_table_fallback_case` 등)도 그대로 통과해야 한다. 실패하면 `recover_blank_leading_column`이 기존에 잘 동작하던 표를 잘못 건드리는 것이므로, 어떤 행이 바뀌었는지 `print`로 확인 후 원인을 고칠 것 (예: `right_x - left_x < 10` 임계값 조정).

- [ ] **Step 5: 커밋**

```bash
git add pdf_item_parser.py test_pdf_item_parser.py
git commit -m "fix: recover item-name column when PDF table has no per-row borders there"
```

---

### Task 3: PDF에서 업체명(거래처명) 자동 인식

**Files:**
- Modify: `pdf_item_parser.py` (새 함수 추가, `parse_pdf_items` 반환값에 `company` 키 추가)
- Modify: `test_parse_pdf_route.py:23` (`items/page_images/warnings` → `company` 포함)
- Test: `test_pdf_item_parser.py`, `test_parse_pdf_route.py`

**Interfaces:**
- Consumes: Task 1/2의 `normalize_header`
- Produces: `extract_company_name(pdf_bytes) -> str | None`. `parse_pdf_items(pdf_bytes)`의 반환 딕셔너리에 `"company"` 키 추가 (Task 9의 프론트엔드가 이 키를 사용).

- [ ] **Step 1: 실패하는 테스트 작성**

`test_pdf_item_parser.py` 상단 import 구문

```python
from pdf_item_parser import (
    normalize_header, match_field, match_field_fuzzy, parse_number,
    find_header_row, score_table, map_table_columns, extract_items_from_table,
    resolve_duplicate_price_columns, clean_item_rows, apply_hierarchical_prefix,
    extract_paragraph_fallback, render_page_images, parse_pdf_items,
)
```

를 아래로 교체:

```python
from pdf_item_parser import (
    normalize_header, match_field, match_field_fuzzy, parse_number,
    find_header_row, score_table, map_table_columns, extract_items_from_table,
    resolve_duplicate_price_columns, clean_item_rows, apply_hierarchical_prefix,
    extract_paragraph_fallback, render_page_images, parse_pdf_items,
    extract_company_name, _match_company_label,
)
```

`test_extract_paragraph_fallback_returns_none_without_name` 함수 바로 아래에 추가:

```python
def test_match_company_label_matches_known_synonyms():
    assert _match_company_label("상호") is True
    assert _match_company_label("회사명") is True
    assert _match_company_label("사업자번호") is False
    print("OK: test_match_company_label_matches_known_synonyms")


def test_extract_company_name_reads_from_table_and_skips_self_company():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_extract_company_name_reads_from_table_and_skips_self_company (no sample dir)")
        return
    company = extract_company_name(_load_sample("견적서_20260721(그린플러스_IR Cut_8월).pdf"))
    assert company == "마이크로웍스솔루션즈 주식회사"
    print("OK: test_extract_company_name_reads_from_table_and_skips_self_company")
```

`if __name__ == "__main__":` 블록의 `test_parse_pdf_items_recovers_borderless_name_column_case()` 호출 다음 줄에 두 호출을 추가:

```python
    test_match_company_label_matches_known_synonyms()
    test_extract_company_name_reads_from_table_and_skips_self_company()
```

`test_parse_pdf_route.py`의 기존

```python
    assert set(body.keys()) == {"items", "page_images", "warnings"}
```

를

```python
    assert set(body.keys()) == {"items", "page_images", "warnings", "company"}
```

로 교체.

`test_parse_pdf_route.py` 맨 위 import 구문(`import io`, `import fitz`, `import app as app_module`) 다음 줄에 `import os`를 추가하고, `_tiny_pdf_bytes` 함수 다음, `test_parse_pdf_route_returns_json_with_expected_keys` 함수 앞에 `SAMPLE_DIR = r"D:\claude_personal\setting_01\PDF_read"`를 추가한다. 그리고 `test_parse_pdf_route_returns_400_for_invalid_pdf` 함수 다음에 추가:

```python
def test_parse_pdf_route_returns_recognized_company_for_real_sample():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_route_returns_recognized_company_for_real_sample (no sample dir)")
        return
    client = app_module.app.test_client()
    path = os.path.join(SAMPLE_DIR, "견적서_20260721(그린플러스_IR Cut_8월).pdf")
    with open(path, "rb") as f:
        data = {"file": (f, "quote.pdf")}
        resp = client.post("/parse_pdf", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["company"] == "마이크로웍스솔루션즈 주식회사"
    print("OK: test_parse_pdf_route_returns_recognized_company_for_real_sample")
```

그리고 `if __name__ == "__main__":` 블록에 `test_parse_pdf_route_returns_recognized_company_for_real_sample()` 호출을 추가.

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python test_pdf_item_parser.py`
Expected: `ImportError` (`extract_company_name`, `_match_company_label`이 아직 없음).

Run: `python test_parse_pdf_route.py`
Expected: `AssertionError` (`company` 키가 아직 응답에 없음).

- [ ] **Step 3: 최소 구현**

`pdf_item_parser.py`에서 `extract_paragraph_fallback` 함수 정의 바로 다음, `def render_page_images(...)` 앞에 아래 코드를 추가:

```python
COMPANY_LABEL_SYNONYMS = ["상호", "업체", "거래처명", "발신", "회사명", "COMPANY", "COMPANY NAME"]
SELF_COMPANY_MARKER = "그린플러스"


def _is_self_company(value):
    return normalize_header(SELF_COMPANY_MARKER) in normalize_header(value)


def _match_company_label(cell_text):
    if not cell_text:
        return False
    normalized = normalize_header(cell_text)
    return any(normalize_header(syn) == normalized for syn in COMPANY_LABEL_SYNONYMS)


def _cell_text(value):
    return value.strip() if isinstance(value, str) else ("" if value is None else str(value).strip())


def _find_company_in_tables(pdf):
    for page in pdf.pages:
        for table in page.extract_tables():
            for row in table:
                for idx, cell in enumerate(row):
                    if not _match_company_label(cell):
                        continue
                    for raw_value in row[idx + 1:]:
                        value = _cell_text(raw_value)
                        if not value:
                            continue
                        if not _is_self_company(value):
                            return value
                        break
    return None


def _find_company_in_text(full_text):
    for line in full_text.split("\n"):
        sep = ":" if ":" in line else ("：" if "：" in line else None)
        if sep is None:
            continue
        label, _, value = line.partition(sep)
        if not _match_company_label(label):
            continue
        value = value.strip()
        if value and not _is_self_company(value):
            return value
    return None


def extract_company_name(pdf_bytes):
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        found = _find_company_in_tables(pdf)
        if found:
            return found
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return _find_company_in_text(full_text)
```

그리고 `parse_pdf_items`의 기존

```python
def parse_pdf_items(pdf_bytes):
    warnings = []
    page_images = render_page_images(pdf_bytes)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
```

를

```python
def parse_pdf_items(pdf_bytes):
    warnings = []
    page_images = render_page_images(pdf_bytes)
    company = extract_company_name(pdf_bytes)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
```

로 교체하고, 함수 맨 마지막 줄

```python
    return {"items": items, "page_images": page_images, "warnings": warnings}
```

를

```python
    return {"items": items, "page_images": page_images, "warnings": warnings, "company": company}
```

로 교체.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_pdf_item_parser.py`
Expected: `ALL PASSED`

Run: `python test_parse_pdf_route.py`
Expected: `ALL PASSED`

- [ ] **Step 5: 커밋**

```bash
git add pdf_item_parser.py test_pdf_item_parser.py test_parse_pdf_route.py
git commit -m "feat: auto-detect vendor company name from uploaded PDF quotes"
```

---

### Task 4: 과제 프리셋 데이터 정리 (14개 → 10개, `short_name` 추가)

**Files:**
- Modify: `data/projects.json` (전체 교체)

**Interfaces:**
- Consumes: 없음
- Produces: 10개 항목의 리스트, 각 항목은 `agency`/`org`/`project_name`/`short_name` 키를 가짐 (아직 `id`는 없음 — Task 5의 `history_store.load_projects()`가 로드 시 자동 부여).

- [ ] **Step 1: `data/projects.json` 전체 내용을 아래로 교체**

```json
[
  {
    "agency": "농림축산식품부",
    "org": "농림식품기술기획평가원",
    "project_name": "고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발",
    "short_name": "고효율"
  },
  {
    "agency": "농림축산식품부",
    "org": "농림식품기술기획평가원",
    "project_name": "수확 후 전 과정 무인 자동화 시스템 개발 및 실증",
    "short_name": "수확후"
  },
  {
    "agency": "과학기술정보통신부",
    "org": "정보통신기획평가원",
    "project_name": "농축산시설 탄소 배출량 통합관리를 위한 디지털 트윈 플랫폼 기술 개발",
    "short_name": "탄소"
  },
  {
    "agency": "농림축산식품부",
    "org": "(재)스마트팜연구개발사업단",
    "project_name": "무인 자율형 K-Farm 저온성 작물 데모온실 구축 및 검증",
    "short_name": "저온성"
  },
  {
    "agency": "농림축산식품부",
    "org": "농림식품기술기획평가원",
    "project_name": "북미 북동부 환경 적응 및 특약용 작물 재배용 수직농장 모델 개발",
    "short_name": "북미"
  },
  {
    "agency": "농림축산식품부",
    "org": "농림식품기술기획평가원",
    "project_name": "인건비 절감 및 생산량 극대화를 위한 심화작업 자동화 수직농장 모델 개발",
    "short_name": "자동화"
  },
  {
    "agency": "농림축산식품부",
    "org": "농림식품기술기획평가원",
    "project_name": "중동 등 수출대상국가에 적합한 시설자재 개발 및 현지 실증",
    "short_name": "IR"
  },
  {
    "agency": "농림축산식품부",
    "org": "농림식품기술기획평가원",
    "project_name": "무인 자율형 K-Farm 고온성 작물 데모온실 구축 및 검증",
    "short_name": "고온"
  },
  {
    "agency": "농림축산식품부",
    "org": "(재)스마트팜연구개발사업단",
    "project_name": "시설 과채류 작물별 생리해석 및 근권부 정밀제어를 위한 지능형 의사결정 시스템 상용화",
    "short_name": "근권부"
  },
  {
    "agency": "산업통상자원부",
    "org": "한국산업기술기획평가원",
    "project_name": "수직농장 유연생산을 위한 자율 농수작업 로봇기술 개발",
    "short_name": "로봇"
  }
]
```

- [ ] **Step 2: 유효한 JSON인지, 정확히 10개인지 확인**

Run: `python -c "import json; d=json.load(open('data/projects.json', encoding='utf-8')); print(len(d)); print(all('short_name' in p for p in d))"`
Expected: `10` 그리고 `True` 출력.

- [ ] **Step 3: 커밋**

```bash
git add data/projects.json
git commit -m "data: dedupe project presets from 14 to 10 entries with short_name abbreviations"
```

---

### Task 5: 과제 프리셋 `id` 부여/마이그레이션 + CRUD 함수 (`history_store.py`)

**Files:**
- Modify: `history_store.py` (`DEFAULT_PROJECTS`, `load_projects`, `record_generation`, 새 함수 3개 추가)
- Test: `test_history_store_projects_crud.py` (신규 파일)

**Interfaces:**
- Consumes: Task 4의 `data/projects.json` 스키마
- Produces:
  - `history_store.load_projects() -> list[dict]` — 각 항목에 `id`(문자열)가 반드시 존재하도록 보장 (변경 사항).
  - `history_store.add_project(data: dict) -> dict` — `data`는 `short_name`/`agency`/`org`/`project_name` 키를 담은 딕셔너리. `project_name`이 비어있으면 `ValueError`. 생성된 항목(`id` 포함)을 반환.
  - `history_store.update_project(project_id: str, data: dict) -> dict | None` — 없는 id면 `None`, `project_name`이 비어있으면 `ValueError`.
  - `history_store.delete_project(project_id: str) -> bool` — 성공하면 `True`, 없는 id면 `False`.
  - Task 6의 Flask 라우트가 이 3개 함수를 그대로 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

새 파일 `test_history_store_projects_crud.py` 생성:

```python
import json
import os
import shutil
import tempfile

import history_store


def _with_temp_projects_path(fn):
    tmp_dir = tempfile.mkdtemp()
    original_path = history_store.PROJECTS_PATH
    try:
        history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")
        fn()
    finally:
        history_store.PROJECTS_PATH = original_path
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_load_projects_assigns_ids_to_entries_missing_them():
    def run():
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([{"agency": "A부처", "org": "A기관", "project_name": "과제1"}], f)
        projects = history_store.load_projects()
        assert len(projects) == 1
        assert projects[0]["id"]

        with open(history_store.PROJECTS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved[0]["id"] == projects[0]["id"]
        print("OK: test_load_projects_assigns_ids_to_entries_missing_them")
    _with_temp_projects_path(run)


def test_add_project_creates_entry_with_new_id():
    def run():
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        created = history_store.add_project({
            "short_name": "테스트", "agency": "A부처", "org": "A기관", "project_name": "새 과제",
        })
        assert created["id"]
        assert created["short_name"] == "테스트"
        projects = history_store.load_projects()
        assert len(projects) == 1
        assert projects[0]["project_name"] == "새 과제"
        print("OK: test_add_project_creates_entry_with_new_id")
    _with_temp_projects_path(run)


def test_add_project_requires_project_name():
    def run():
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        try:
            history_store.add_project({"short_name": "테스트", "agency": "", "org": "", "project_name": "  "})
            assert False, "ValueError를 기대했지만 발생하지 않음"
        except ValueError:
            pass
        print("OK: test_add_project_requires_project_name")
    _with_temp_projects_path(run)


def test_update_project_modifies_existing_entry_by_id():
    def run():
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([{"agency": "A부처", "org": "A기관", "project_name": "과제1"}], f)
        existing_id = history_store.load_projects()[0]["id"]
        updated = history_store.update_project(existing_id, {
            "short_name": "축약", "agency": "B부처", "org": "B기관", "project_name": "과제1-수정",
        })
        assert updated["project_name"] == "과제1-수정"
        assert updated["short_name"] == "축약"
        assert updated["id"] == existing_id
        print("OK: test_update_project_modifies_existing_entry_by_id")
    _with_temp_projects_path(run)


def test_update_project_returns_none_for_unknown_id():
    def run():
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        result = history_store.update_project("no-such-id", {"project_name": "x"})
        assert result is None
        print("OK: test_update_project_returns_none_for_unknown_id")
    _with_temp_projects_path(run)


def test_delete_project_removes_entry_by_id():
    def run():
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([{"agency": "A부처", "org": "A기관", "project_name": "과제1"}], f)
        existing_id = history_store.load_projects()[0]["id"]
        assert history_store.delete_project(existing_id) is True
        assert history_store.load_projects() == []
        assert history_store.delete_project(existing_id) is False
        print("OK: test_delete_project_removes_entry_by_id")
    _with_temp_projects_path(run)


def test_record_generation_preserves_id_and_short_name_on_reuse():
    def run():
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([{"agency": "A부처", "org": "A기관", "project_name": "과제1", "short_name": "축약1"}], f)
        original_id = history_store.load_projects()[0]["id"]

        original_history_path = history_store.HISTORY_PATH
        tmp_dir = os.path.dirname(history_store.PROJECTS_PATH)
        history_store.HISTORY_PATH = os.path.join(tmp_dir, "history.json")
        try:
            history_store.record_generation({
                "company": "테스트업체", "agency": "A부처", "org": "A기관", "project_name": "과제1",
            })
        finally:
            history_store.HISTORY_PATH = original_history_path

        projects = history_store.load_projects()
        assert len(projects) == 1
        assert projects[0]["id"] == original_id
        assert projects[0]["short_name"] == "축약1"
        print("OK: test_record_generation_preserves_id_and_short_name_on_reuse")
    _with_temp_projects_path(run)


if __name__ == "__main__":
    test_load_projects_assigns_ids_to_entries_missing_them()
    test_add_project_creates_entry_with_new_id()
    test_add_project_requires_project_name()
    test_update_project_modifies_existing_entry_by_id()
    test_update_project_returns_none_for_unknown_id()
    test_delete_project_removes_entry_by_id()
    test_record_generation_preserves_id_and_short_name_on_reuse()
    print("ALL PASSED")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python test_history_store_projects_crud.py`
Expected: `AttributeError` (`add_project`/`update_project`/`delete_project`가 아직 없음).

- [ ] **Step 3: 최소 구현**

`history_store.py` 맨 위 `import json` 다음 줄에 `import uuid`를 추가한다 (import 순서는 알파벳순 유지: `import json`, `import os`, `import uuid`).

기존

```python
DEFAULT_PROJECTS = [
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "인건비 절감 및 생산량 극대화를 위한 심화작업 자동화 수직농장 모델 개발",
    },
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발",
    },
]
```

를 Task 4에서 정리한 10개 목록으로 교체 (파일에 없을 때만 쓰이는 기본값이므로 `data/projects.json`과 동일한 10개 항목, `short_name` 포함):

```python
DEFAULT_PROJECTS = [
    {"agency": "농림축산식품부", "org": "농림식품기술기획평가원", "project_name": "고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발", "short_name": "고효율"},
    {"agency": "농림축산식품부", "org": "농림식품기술기획평가원", "project_name": "수확 후 전 과정 무인 자동화 시스템 개발 및 실증", "short_name": "수확후"},
    {"agency": "과학기술정보통신부", "org": "정보통신기획평가원", "project_name": "농축산시설 탄소 배출량 통합관리를 위한 디지털 트윈 플랫폼 기술 개발", "short_name": "탄소"},
    {"agency": "농림축산식품부", "org": "(재)스마트팜연구개발사업단", "project_name": "무인 자율형 K-Farm 저온성 작물 데모온실 구축 및 검증", "short_name": "저온성"},
    {"agency": "농림축산식품부", "org": "농림식품기술기획평가원", "project_name": "북미 북동부 환경 적응 및 특약용 작물 재배용 수직농장 모델 개발", "short_name": "북미"},
    {"agency": "농림축산식품부", "org": "농림식품기술기획평가원", "project_name": "인건비 절감 및 생산량 극대화를 위한 심화작업 자동화 수직농장 모델 개발", "short_name": "자동화"},
    {"agency": "농림축산식품부", "org": "농림식품기술기획평가원", "project_name": "중동 등 수출대상국가에 적합한 시설자재 개발 및 현지 실증", "short_name": "IR"},
    {"agency": "농림축산식품부", "org": "농림식품기술기획평가원", "project_name": "무인 자율형 K-Farm 고온성 작물 데모온실 구축 및 검증", "short_name": "고온"},
    {"agency": "농림축산식품부", "org": "(재)스마트팜연구개발사업단", "project_name": "시설 과채류 작물별 생리해석 및 근권부 정밀제어를 위한 지능형 의사결정 시스템 상용화", "short_name": "근권부"},
    {"agency": "산업통상자원부", "org": "한국산업기술기획평가원", "project_name": "수직농장 유연생산을 위한 자율 농수작업 로봇기술 개발", "short_name": "로봇"},
]
```

기존

```python
def load_projects():
    projects = _load_json(PROJECTS_PATH, None)
    if projects is None:
        projects = list(DEFAULT_PROJECTS)
        _save_json(PROJECTS_PATH, projects)
    return projects
```

를

```python
def _next_project_id(existing_ids):
    new_id = uuid.uuid4().hex[:8]
    while new_id in existing_ids:
        new_id = uuid.uuid4().hex[:8]
    return new_id


def _ensure_project_ids(projects):
    existing_ids = {p["id"] for p in projects if p.get("id")}
    changed = False
    for p in projects:
        if not p.get("id"):
            p["id"] = _next_project_id(existing_ids)
            existing_ids.add(p["id"])
            changed = True
    return changed


def load_projects():
    projects = _load_json(PROJECTS_PATH, None)
    if projects is None:
        projects = [dict(p) for p in DEFAULT_PROJECTS]
        _ensure_project_ids(projects)
        _save_json(PROJECTS_PATH, projects)
        return projects
    if _ensure_project_ids(projects):
        _save_json(PROJECTS_PATH, projects)
    return projects


def add_project(data):
    project_name = (data.get("project_name") or "").strip()
    if not project_name:
        raise ValueError("project_name is required")
    projects = load_projects()
    new_project = {
        "id": _next_project_id({p["id"] for p in projects}),
        "short_name": (data.get("short_name") or "").strip(),
        "agency": (data.get("agency") or "").strip(),
        "org": (data.get("org") or "").strip(),
        "project_name": project_name,
    }
    projects.insert(0, new_project)
    _save_json(PROJECTS_PATH, projects[:MAX_PROJECTS])
    return new_project


def update_project(project_id, data):
    project_name = (data.get("project_name") or "").strip()
    if not project_name:
        raise ValueError("project_name is required")
    projects = load_projects()
    for p in projects:
        if p.get("id") == project_id:
            p["short_name"] = (data.get("short_name") or "").strip()
            p["agency"] = (data.get("agency") or "").strip()
            p["org"] = (data.get("org") or "").strip()
            p["project_name"] = project_name
            _save_json(PROJECTS_PATH, projects)
            return p
    return None


def delete_project(project_id):
    projects = load_projects()
    remaining = [p for p in projects if p.get("id") != project_id]
    if len(remaining) == len(projects):
        return False
    _save_json(PROJECTS_PATH, remaining)
    return True
```

로 교체.

마지막으로 `record_generation` 안의 기존

```python
    project_name = (data.get("project_name") or "").strip()
    if project_name:
        projects = load_projects()
        projects = [p for p in projects if p.get("project_name") != project_name]
        projects.insert(
            0,
            {
                "agency": (data.get("agency") or "").strip(),
                "org": (data.get("org") or "").strip(),
                "project_name": project_name,
            },
        )
        _save_json(PROJECTS_PATH, projects[:MAX_PROJECTS])
```

를

```python
    project_name = (data.get("project_name") or "").strip()
    if project_name:
        projects = load_projects()
        existing = next((p for p in projects if p.get("project_name") == project_name), None)
        projects = [p for p in projects if p.get("project_name") != project_name]
        projects.insert(
            0,
            {
                "id": existing["id"] if existing else _next_project_id({p["id"] for p in projects}),
                "short_name": existing.get("short_name", "") if existing else "",
                "agency": (data.get("agency") or "").strip(),
                "org": (data.get("org") or "").strip(),
                "project_name": project_name,
            },
        )
        _save_json(PROJECTS_PATH, projects[:MAX_PROJECTS])
```

로 교체 (기존 항목을 재생성할 때 `id`/`short_name`이 사라지지 않도록 보존 — 그렇지 않으면 CRUD로 부여한 축약어가 지출결의서 생성할 때마다 리셋됨).

- [ ] **Step 4: 테스트 통과 확인 (신규 + 기존 회귀)**

Run: `python test_history_store_projects_crud.py`
Expected: `ALL PASSED`

Run: `python test_history_store_merge.py`
Expected: `ALL PASSED` (기존 테스트가 `id`/`short_name` 필드 추가로 깨지지 않는지 확인 — 이 테스트는 `project_name` 값만 확인하므로 영향 없어야 함).

Run: `python test_app_refresh_route.py`
Expected: `ALL PASSED`

- [ ] **Step 5: 커밋**

```bash
git add history_store.py test_history_store_projects_crud.py
git commit -m "feat: add stable ids and CRUD functions for project presets"
```

---

### Task 6: 과제 프리셋 CRUD Flask 라우트 (`/api/projects`)

**Files:**
- Modify: `app.py` (라우트 3개 추가)
- Test: `test_projects_api_routes.py` (신규 파일)

**Interfaces:**
- Consumes: Task 5의 `history_store.add_project`/`update_project`/`delete_project`
- Produces: `POST /api/projects`, `PUT /api/projects/<project_id>`, `DELETE /api/projects/<project_id>` — Task 8의 프론트엔드 JS가 이 3개 엔드포인트를 fetch로 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

새 파일 `test_projects_api_routes.py` 생성:

```python
import json
import os
import shutil
import tempfile

import app as app_module
import history_store


def _with_temp_projects_path(fn):
    tmp_dir = tempfile.mkdtemp()
    original_path = history_store.PROJECTS_PATH
    try:
        history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)
        fn()
    finally:
        history_store.PROJECTS_PATH = original_path
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_create_project_route_returns_created_entry_with_id():
    def run():
        client = app_module.app.test_client()
        resp = client.post("/api/projects", json={
            "short_name": "테스트", "agency": "A부처", "org": "A기관", "project_name": "새 과제",
        })
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["id"]
        assert body["project_name"] == "새 과제"
        print("OK: test_create_project_route_returns_created_entry_with_id")
    _with_temp_projects_path(run)


def test_create_project_route_rejects_empty_project_name():
    def run():
        client = app_module.app.test_client()
        resp = client.post("/api/projects", json={"project_name": "  "})
        assert resp.status_code == 400
        print("OK: test_create_project_route_rejects_empty_project_name")
    _with_temp_projects_path(run)


def test_update_project_route_modifies_entry():
    def run():
        client = app_module.app.test_client()
        created = client.post("/api/projects", json={"project_name": "과제A"}).get_json()
        resp = client.put(f"/api/projects/{created['id']}", json={
            "short_name": "축약", "agency": "B부처", "org": "B기관", "project_name": "과제A-수정",
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["project_name"] == "과제A-수정"
        print("OK: test_update_project_route_modifies_entry")
    _with_temp_projects_path(run)


def test_update_project_route_returns_404_for_unknown_id():
    def run():
        client = app_module.app.test_client()
        resp = client.put("/api/projects/no-such-id", json={"project_name": "x"})
        assert resp.status_code == 404
        print("OK: test_update_project_route_returns_404_for_unknown_id")
    _with_temp_projects_path(run)


def test_delete_project_route_removes_entry():
    def run():
        client = app_module.app.test_client()
        created = client.post("/api/projects", json={"project_name": "과제B"}).get_json()
        resp = client.delete(f"/api/projects/{created['id']}")
        assert resp.status_code == 200
        resp2 = client.delete(f"/api/projects/{created['id']}")
        assert resp2.status_code == 404
        print("OK: test_delete_project_route_removes_entry")
    _with_temp_projects_path(run)


if __name__ == "__main__":
    test_create_project_route_returns_created_entry_with_id()
    test_create_project_route_rejects_empty_project_name()
    test_update_project_route_modifies_entry()
    test_update_project_route_returns_404_for_unknown_id()
    test_delete_project_route_removes_entry()
    print("ALL PASSED")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `python test_projects_api_routes.py`
Expected: `404 Not Found` 관련 실패 (라우트가 아직 없음, 첫 테스트에서 `assert resp.status_code == 201` 실패).

- [ ] **Step 3: 최소 구현**

`app.py`의 기존

```python
@app.route("/generate", methods=["POST"])
def generate():
```

바로 앞에 아래 라우트 3개를 추가:

```python
@app.route("/api/projects", methods=["POST"])
def create_project():
    data = request.get_json(silent=True) or {}
    try:
        project = history_store.add_project(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(project), 201


@app.route("/api/projects/<project_id>", methods=["PUT"])
def update_project_route(project_id):
    data = request.get_json(silent=True) or {}
    try:
        project = history_store.update_project(project_id, data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if project is None:
        return jsonify({"error": "존재하지 않는 과제입니다."}), 404
    return jsonify(project)


@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project_route(project_id):
    deleted = history_store.delete_project(project_id)
    if not deleted:
        return jsonify({"error": "존재하지 않는 과제입니다."}), 404
    return jsonify({"deleted": True})


```

(`history_store`는 `app.py` 상단에 이미 import되어 있음.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_projects_api_routes.py`
Expected: `ALL PASSED`

- [ ] **Step 5: 커밋**

```bash
git add app.py test_projects_api_routes.py
git commit -m "feat: add /api/projects CRUD routes"
```

---

### Task 7: 과제 선택 드롭다운 단순화 (축약어 표시, id 기반)

**Files:**
- Modify: `templates/index.html:217-260` (과제 정보 fieldset 마크업)
- Modify: `templates/index.html:335-357` (관련 JS)

**Interfaces:**
- Consumes: Task 5/6에서 각 프로젝트 항목이 `id`/`short_name`을 갖는다는 사실
- Produces: 전역 JS 변수 `let PROJECTS` (기존엔 `const`였음 — Task 8에서 CRUD로 재할당하므로 `let`로 변경), 함수 `renderProjectSelect()`, `renderProjectDatalists()`. Task 8/9가 이 두 함수를 재사용한다.

- [ ] **Step 1: 마크업 수정**

`templates/index.html`의 기존

```html
    <fieldset>
      <legend>과제 정보 (해당 없으면 비워두세요)</legend>
      <div class="preset-row">
        <label>과제 선택 (자동으로 아래 3칸을 채워줍니다)</label>
        <select id="projectPreset">
          <option value="">직접 입력</option>
          {% for p in projects %}
          <option value="{{ loop.index0 }}">{{ p.project_name }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="grid">
        <div>
          <label>중앙행정기관</label>
          <input type="text" name="agency" id="agencyInput" list="agencyList" placeholder="예) 농림축산식품부">
          <datalist id="agencyList">
            {% for v in projects|map(attribute='agency')|unique %}<option value="{{ v }}">{% endfor %}
          </datalist>
        </div>
        <div>
          <label>전문기관</label>
          <input type="text" name="org" id="orgInput" list="orgList" placeholder="예) 농림식품기술기획평가원">
          <datalist id="orgList">
            {% for v in projects|map(attribute='org')|unique %}<option value="{{ v }}">{% endfor %}
          </datalist>
        </div>
      </div>
      <div class="grid full" style="margin-top:12px;">
        <div>
          <label>과제명</label>
          <input type="text" name="project_name" id="projectNameInput" list="projectNameList" placeholder="예) 고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발">
          <datalist id="projectNameList">
            {% for p in projects %}<option value="{{ p.project_name }}">{% endfor %}
          </datalist>
        </div>
        <div>
          <label>집행 문구</label>
          <input type="text" name="execution_note" list="executionNoteList" value="연구재료비 집행의 건 (연구개발계획서 상 계상되어 있는 건임)">
          <datalist id="executionNoteList">
            {% for v in history.execution_note %}<option value="{{ v }}">{% endfor %}
          </datalist>
        </div>
      </div>
    </fieldset>
```

를 아래로 교체:

```html
    <fieldset>
      <legend>과제 정보 (해당 없으면 비워두세요)</legend>
      <div class="preset-row">
        <label>과제 선택 (자동으로 아래 3칸을 채워줍니다)</label>
        <div style="display:flex;gap:6px;align-items:center;">
          <select id="projectPreset" style="flex:1;"></select>
          <button type="button" class="small" id="manageProjectsBtn">⚙ 과제 관리</button>
        </div>
      </div>
      <div id="projectManagePanel" style="display:none;margin-bottom:14px;border:1px solid var(--border);border-radius:8px;padding:12px;">
        <table style="width:100%;border-collapse:collapse;font-size:12.5px;">
          <thead>
            <tr>
              <th style="border:1px solid var(--border);padding:4px;width:12%;">축약어</th>
              <th style="border:1px solid var(--border);padding:4px;width:20%;">중앙행정기관</th>
              <th style="border:1px solid var(--border);padding:4px;width:20%;">전문기관</th>
              <th style="border:1px solid var(--border);padding:4px;">과제명</th>
              <th style="border:1px solid var(--border);padding:4px;width:14%;"></th>
            </tr>
          </thead>
          <tbody id="projectManageBody"></tbody>
        </table>
      </div>
      <div class="grid">
        <div>
          <label>중앙행정기관</label>
          <input type="text" name="agency" id="agencyInput" list="agencyList" placeholder="예) 농림축산식품부">
          <datalist id="agencyList"></datalist>
        </div>
        <div>
          <label>전문기관</label>
          <input type="text" name="org" id="orgInput" list="orgList" placeholder="예) 농림식품기술기획평가원">
          <datalist id="orgList"></datalist>
        </div>
      </div>
      <div class="grid full" style="margin-top:12px;">
        <div>
          <label>과제명</label>
          <input type="text" name="project_name" id="projectNameInput" list="projectNameList" placeholder="예) 고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발">
          <datalist id="projectNameList"></datalist>
        </div>
        <div>
          <label>집행 문구</label>
          <input type="text" name="execution_note" list="executionNoteList" value="연구재료비 집행의 건 (연구개발계획서 상 계상되어 있는 건임)">
          <datalist id="executionNoteList">
            {% for v in history.execution_note %}<option value="{{ v }}">{% endfor %}
          </datalist>
        </div>
      </div>
    </fieldset>
```

- [ ] **Step 2: JS 수정**

기존

```html
<script>
const PROJECTS = {{ projects | tojson }};
const itemsBody = document.getElementById('itemsBody');
const colSpec = document.getElementById('colSpec');
const colUnit = document.getElementById('colUnit');
const colQty = document.getElementById('colQty');
const colPrice = document.getElementById('colPrice');

function todayStr() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
}
document.getElementById('proposeDate').value = todayStr();

document.getElementById('projectPreset').addEventListener('change', (e) => {
  if (e.target.value === '') return;
  const p = PROJECTS[parseInt(e.target.value, 10)];
  document.getElementById('agencyInput').value = p.agency;
  document.getElementById('orgInput').value = p.org;
  document.getElementById('projectNameInput').value = p.project_name;
});
```

를 아래로 교체:

```html
<script>
let PROJECTS = {{ projects | tojson }};
const itemsBody = document.getElementById('itemsBody');
const colSpec = document.getElementById('colSpec');
const colUnit = document.getElementById('colUnit');
const colQty = document.getElementById('colQty');
const colPrice = document.getElementById('colPrice');

function todayStr() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
}
document.getElementById('proposeDate').value = todayStr();

function renderProjectSelect() {
  const select = document.getElementById('projectPreset');
  const prevValue = select.value;
  select.innerHTML = '<option value="">직접 입력</option>';
  PROJECTS.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.short_name || p.project_name;
    opt.title = p.project_name;
    select.appendChild(opt);
  });
  if (PROJECTS.some(p => p.id === prevValue)) select.value = prevValue;
}

function renderProjectDatalists() {
  const agencyList = document.getElementById('agencyList');
  const orgList = document.getElementById('orgList');
  const projectNameList = document.getElementById('projectNameList');
  agencyList.innerHTML = '';
  orgList.innerHTML = '';
  projectNameList.innerHTML = '';
  const seenAgency = new Set(), seenOrg = new Set();
  PROJECTS.forEach(p => {
    if (p.agency && !seenAgency.has(p.agency)) {
      seenAgency.add(p.agency);
      const opt = document.createElement('option');
      opt.value = p.agency;
      agencyList.appendChild(opt);
    }
    if (p.org && !seenOrg.has(p.org)) {
      seenOrg.add(p.org);
      const opt = document.createElement('option');
      opt.value = p.org;
      orgList.appendChild(opt);
    }
    const nameOpt = document.createElement('option');
    nameOpt.value = p.project_name;
    projectNameList.appendChild(nameOpt);
  });
}

document.getElementById('projectPreset').addEventListener('change', (e) => {
  if (e.target.value === '') return;
  const p = PROJECTS.find(x => x.id === e.target.value);
  if (!p) return;
  document.getElementById('agencyInput').value = p.agency;
  document.getElementById('orgInput').value = p.org;
  document.getElementById('projectNameInput').value = p.project_name;
});

renderProjectSelect();
renderProjectDatalists();
```

- [ ] **Step 3: 수동 확인 (자동 테스트로는 렌더링된 HTML 존재 여부만 확인 가능)**

새 파일 `test_index_page_markup.py` 생성:

```python
import app as app_module


def test_index_page_contains_project_management_markup():
    client = app_module.app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="projectManagePanel"' in html
    assert 'id="manageProjectsBtn"' in html
    assert 'id="projectPreset" style="flex:1;"></select>' in html
    print("OK: test_index_page_contains_project_management_markup")


if __name__ == "__main__":
    test_index_page_contains_project_management_markup()
    print("ALL PASSED")
```

Run: `python test_index_page_markup.py`
Expected: `ALL PASSED`

- [ ] **Step 4: 커밋**

```bash
git add templates/index.html test_index_page_markup.py
git commit -m "feat: show project short names in dropdown, render project fields via JS"
```

---

### Task 8: 과제 프리셋 관리 패널 (추가/수정/삭제, 즉시 반영)

**Files:**
- Modify: `templates/index.html` (Task 7에서 만든 JS 블록 뒤에 추가)
- Modify: `test_index_page_markup.py` (마크업 확인 추가)

**Interfaces:**
- Consumes: Task 6의 `/api/projects` 라우트, Task 7의 `renderProjectSelect()`/`renderProjectDatalists()`/전역 `PROJECTS`
- Produces: 없음 (최종 사용자 기능)

- [ ] **Step 1: JS 추가**

`templates/index.html`에서 (Task 7 이후 상태 기준) 기존

```html
document.getElementById('projectPreset').addEventListener('change', (e) => {
  if (e.target.value === '') return;
  const p = PROJECTS.find(x => x.id === e.target.value);
  if (!p) return;
  document.getElementById('agencyInput').value = p.agency;
  document.getElementById('orgInput').value = p.org;
  document.getElementById('projectNameInput').value = p.project_name;
});

renderProjectSelect();
renderProjectDatalists();
```

를 아래로 교체 (관리 패널 관련 함수를 마지막 두 호출 사이에 삽입):

```html
document.getElementById('projectPreset').addEventListener('change', (e) => {
  if (e.target.value === '') return;
  const p = PROJECTS.find(x => x.id === e.target.value);
  if (!p) return;
  document.getElementById('agencyInput').value = p.agency;
  document.getElementById('orgInput').value = p.org;
  document.getElementById('projectNameInput').value = p.project_name;
});

function buildProjectManageRow(p) {
  const isNew = !p;
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="pm-short" value="${escapeHtml(p ? p.short_name : '')}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="pm-agency" value="${escapeHtml(p ? p.agency : '')}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="pm-org" value="${escapeHtml(p ? p.org : '')}" style="width:100%;border:none;"></td>
    <td style="border:1px solid var(--border);padding:4px;"><input type="text" class="pm-name" value="${escapeHtml(p ? p.project_name : '')}" style="width:100%;border:none;" placeholder="${isNew ? '새 과제명 입력 후 추가' : ''}"></td>
    <td style="border:1px solid var(--border);padding:4px;white-space:nowrap;">
      ${isNew ? '<button type="button" class="small pm-add">추가</button>' : '<button type="button" class="small pm-save">저장</button> <button type="button" class="small pm-delete">삭제</button>'}
    </td>
  `;
  if (isNew) {
    tr.querySelector('.pm-add').addEventListener('click', async () => {
      const payload = {
        short_name: tr.querySelector('.pm-short').value.trim(),
        agency: tr.querySelector('.pm-agency').value.trim(),
        org: tr.querySelector('.pm-org').value.trim(),
        project_name: tr.querySelector('.pm-name').value.trim(),
      };
      if (!payload.project_name) { alert('과제명을 입력해주세요.'); return; }
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) { alert('추가에 실패했습니다.'); return; }
      const created = await res.json();
      PROJECTS.unshift(created);
      renderProjectSelect();
      renderProjectDatalists();
      renderProjectManagePanel();
    });
  } else {
    tr.querySelector('.pm-save').addEventListener('click', async () => {
      const payload = {
        short_name: tr.querySelector('.pm-short').value.trim(),
        agency: tr.querySelector('.pm-agency').value.trim(),
        org: tr.querySelector('.pm-org').value.trim(),
        project_name: tr.querySelector('.pm-name').value.trim(),
      };
      if (!payload.project_name) { alert('과제명을 입력해주세요.'); return; }
      const res = await fetch(`/api/projects/${p.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) { alert('저장에 실패했습니다.'); return; }
      const updated = await res.json();
      const idx = PROJECTS.findIndex(x => x.id === p.id);
      PROJECTS[idx] = updated;
      renderProjectSelect();
      renderProjectDatalists();
      renderProjectManagePanel();
    });
    tr.querySelector('.pm-delete').addEventListener('click', async () => {
      if (!confirm('이 과제를 삭제할까요? 되돌릴 수 없습니다.')) return;
      const res = await fetch(`/api/projects/${p.id}`, { method: 'DELETE' });
      if (!res.ok) { alert('삭제에 실패했습니다.'); return; }
      PROJECTS = PROJECTS.filter(x => x.id !== p.id);
      renderProjectSelect();
      renderProjectDatalists();
      renderProjectManagePanel();
    });
  }
  return tr;
}

function renderProjectManagePanel() {
  const body = document.getElementById('projectManageBody');
  body.innerHTML = '';
  PROJECTS.forEach(p => body.appendChild(buildProjectManageRow(p)));
  body.appendChild(buildProjectManageRow(null));
}

document.getElementById('manageProjectsBtn').addEventListener('click', () => {
  const panel = document.getElementById('projectManagePanel');
  const willShow = panel.style.display === 'none';
  panel.style.display = willShow ? 'block' : 'none';
  if (willShow) renderProjectManagePanel();
});

renderProjectSelect();
renderProjectDatalists();
```

(`escapeHtml`는 파일 뒤쪽 PDF 모달 스크립트에 이미 `function escapeHtml(value) {...}`로 선언되어 있음 — 함수 선언은 호이스팅되므로 여기서 먼저 참조해도 문제없다.)

- [ ] **Step 2: 마크업 확인 테스트 추가**

`test_index_page_markup.py`의 `test_index_page_contains_project_management_markup` 함수 안, 마지막 `assert` 다음 줄에 추가:

```python
    assert 'function buildProjectManageRow' in html
    assert 'renderProjectManagePanel' in html
```

- [ ] **Step 3: 테스트 통과 확인**

Run: `python test_index_page_markup.py`
Expected: `ALL PASSED`

- [ ] **Step 4: 커밋**

```bash
git add templates/index.html test_index_page_markup.py
git commit -m "feat: add inline add/edit/delete panel for project presets"
```

---

### Task 9: PDF 업체명 자동 인식 → 기본정보 반영 체크박스

**Files:**
- Modify: `templates/index.html` (PDF 모달 마크업 + JS)
- Modify: `test_index_page_markup.py`

**Interfaces:**
- Consumes: Task 3의 `/parse_pdf` 응답 `company` 키
- Produces: 없음 (최종 사용자 기능)

- [ ] **Step 1: 모달 마크업 수정**

기존

```html
  <div id="pdfModalOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:100;">
    <div style="background:#fff;max-width:1000px;margin:40px auto;border-radius:10px;padding:20px 24px;max-height:85vh;overflow:auto;">
      <h2 style="font-size:16px;margin:0 0 10px;">PDF에서 품목 불러오기</h2>
      <div id="pdfWarnings" style="color:#b42318;font-size:12.5px;margin-bottom:10px;"></div>
      <div style="display:flex;gap:16px;">
```

를 아래로 교체:

```html
  <div id="pdfModalOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.45);z-index:100;">
    <div style="background:#fff;max-width:1000px;margin:40px auto;border-radius:10px;padding:20px 24px;max-height:85vh;overflow:auto;">
      <h2 style="font-size:16px;margin:0 0 10px;">PDF에서 품목 불러오기</h2>
      <div id="pdfWarnings" style="color:#b42318;font-size:12.5px;margin-bottom:10px;"></div>
      <div id="pdfCompanyRow" style="display:none;margin-bottom:10px;font-size:13px;">
        <label style="display:flex;align-items:center;gap:6px;">
          <input type="checkbox" id="pdfCompanyApply" checked>
          인식된 업체명: <b id="pdfCompanyValue"></b> — 기본정보에 반영
        </label>
      </div>
      <div style="display:flex;gap:16px;">
```

- [ ] **Step 2: JS 수정**

기존

```html
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
```

를 아래로 교체:

```html
function openPdfModal(result) {
  pdfDraftBody.innerHTML = '';
  pdfImagePane.innerHTML = '';
  pdfWarnings.textContent = (result.warnings || []).join(' ');
  const companyRow = document.getElementById('pdfCompanyRow');
  const companyCheckbox = document.getElementById('pdfCompanyApply');
  if (result.company) {
    document.getElementById('pdfCompanyValue').textContent = result.company;
    companyRow.style.display = 'block';
    companyCheckbox.checked = true;
  } else {
    companyRow.style.display = 'none';
  }
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
  const companyValue = document.getElementById('pdfCompanyValue').textContent;
  const companyCheckbox = document.getElementById('pdfCompanyApply');
  if (companyCheckbox.checked && companyValue) {
    document.querySelector('input[name="company"]').value = companyValue;
  }
  closePdfModal();
  recalc();
}
```

- [ ] **Step 3: 마크업 확인 테스트 추가**

`test_index_page_markup.py`에 새 테스트 함수 추가 (파일 맨 아래, `if __name__ ==` 블록 앞):

```python
def test_index_page_contains_pdf_company_checkbox_markup():
    client = app_module.app.test_client()
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert 'id="pdfCompanyRow"' in html
    assert 'id="pdfCompanyApply"' in html
    assert 'id="pdfCompanyValue"' in html
    print("OK: test_index_page_contains_pdf_company_checkbox_markup")
```

그리고 `if __name__ == "__main__":` 블록에 `test_index_page_contains_pdf_company_checkbox_markup()` 호출을 추가.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python test_index_page_markup.py`
Expected: `ALL PASSED`

- [ ] **Step 5: 커밋**

```bash
git add templates/index.html test_index_page_markup.py
git commit -m "feat: auto-fill company name from PDF via modal checkbox"
```

---

### Task 10: 전체 회귀 테스트 + 실제 브라우저 수동 확인

**Files:** 없음 (검증 전용 태스크)

**Interfaces:**
- Consumes: Task 1~9 전체
- Produces: 없음

- [ ] **Step 1: 전체 자동 테스트 순차 실행**

```bash
python test_pdf_item_parser.py
python test_parse_pdf_route.py
python test_history_store_merge.py
python test_history_store_projects_crud.py
python test_projects_api_routes.py
python test_app_refresh_route.py
python test_index_page_markup.py
python test_generator.py
python test_column_layout.py
python test_item_table_layout.py
python test_template_banner.py
python test_read_seed.py
```

Expected: 전부 `ALL PASSED`.

- [ ] **Step 2: `run` 스킬로 앱을 실제로 띄워 브라우저에서 수동 확인**

- `python app.py` 실행 (또는 `run` 스킬 사용) → 자동으로 브라우저가 열림.
- **PDF 헤더/업체명**: `PDF_read\견적서_20260721(그린플러스_IR Cut_8월).pdf`를 "PDF로 품목 불러오기"로 업로드 → 품목 2개(ETFE 관련, Target Mix 관련) 이상이 수량/단위/단가와 함께 채워지는지, 모달 상단에 "인식된 업체명: 마이크로웍스솔루션즈 주식회사" 체크박스가 뜨는지, "표에 적용" 후 업체명 입력란에 실제로 반영되는지 확인.
- **과제 선택**: "과제 선택" 드롭다운을 열어 10개 축약어(고효율/수확후/탄소/저온성/북미/자동화/IR/고온/근권부/로봇)만 보이는지, 하나를 선택하면 중앙행정기관/전문기관/과제명이 채워지는지 확인.
- **과제 관리**: "⚙ 과제 관리" 클릭 → 패널이 펼쳐지는지, 아무 항목이나 수정 후 "저장"을 누르면 새로고침 없이 드롭다운 텍스트도 즉시 바뀌는지, 맨 아래 빈 행에 값을 넣고 "추가"하면 목록에 즉시 나타나는지, "삭제"가 확인창 후 즉시 반영되는지 확인.
- **기존 8개 샘플**: 최소 2~3개(`한열사_견적서_북미.pdf`, `견적서_코랄_수확후.pdf` 등)를 업로드해서 기존 파싱 결과가 그대로인지(회귀 없는지) 확인.
- 이상 없으면 완료. 문제 발견 시 어떤 태스크의 코드가 원인인지 특정해서 그 태스크의 산출물만 수정 (새 태스크로 기록하지 말고 해당 파일을 바로 고치고 별도 커밋).

- [ ] **Step 3: 최종 커밋 (필요 시)**

Step 2에서 수정한 내용이 있다면:

```bash
git add -A
git commit -m "fix: address issues found during manual end-to-end verification"
```

없다면 이 태스크는 커밋 없이 종료.
