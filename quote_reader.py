"""통합 견적서 리더 (PDF / JPG·PNG / XLSX).

기존 pdf_item_parser.parse_pdf_items() 를 1순위로 쓰되, 다음 세 가지 실제 상황을
보강한다.

1. 텍스트 레이어는 있으나 표 격자선이 없어 pdfplumber 가 품목 표를 못 잡는 견적서
   (예: 유진철강 각파이프 견적서) -> 단어 좌표(x/top)로 열을 복원하는 폴백.
2. JPG/PNG 견적서 -> 이미지 렌더 후 기존 OCR 품목 추출 로직 재사용.
3. XLSX 견적서 -> 시트에서 헤더 행을 찾아 품목을 직접 읽는다.

반환 스키마는 어느 경로든 동일하다:
    {
      "items": [ {name, spec?, unit?, qty?, weight?, price?, supply?, ...}, ... ],
      "company": str|None,
      "title": str|None,
      "warnings": [str, ...],
      "source": "pdf-table" | "pdf-coords" | "pdf-ocr" | "image-ocr" | "xlsx",
    }

items 의 각 dict 는 generator.build_expense_report() / inspection_generator 가
그대로 소비할 수 있는 형태다(수량/단가/중량은 float, 공급가는 supply).
"""

import io
import os
import re

import pdfplumber

import pdf_item_parser as P


# ------------------------------------------------------------------ #
# 좌표 기반 텍스트-레이어 폴백
# ------------------------------------------------------------------ #

# 이 필드들만 품목 dict 에 실어 보낸다(generator 가 아는 키).
_NUMERIC_FIELDS = {"qty", "weight", "price"}


def _cluster_rows_by_top(words, tol=4.0):
    """extract_words 결과를 top 좌표 기준으로 같은 줄끼리 묶는다."""
    rows = []
    for w in sorted(words, key=lambda x: (round(x["top"]), x["x0"])):
        placed = False
        for row in rows:
            if abs(row["top"] - w["top"]) <= tol:
                row["words"].append(w)
                row["top"] = (row["top"] * row["n"] + w["top"]) / (row["n"] + 1)
                row["n"] += 1
                placed = True
                break
        if not placed:
            rows.append({"top": w["top"], "n": 1, "words": [w]})
    for row in rows:
        row["words"].sort(key=lambda x: x["x0"])
    rows.sort(key=lambda r: r["top"])
    return rows


def _join(words):
    return "".join(w["text"] for w in words)


# 헤더 라벨을 개별 문자(char) 좌표로 찾기 위한 한글 우선 동의어.
# (영문 ITEM/PRICE 등은 본문 다른 곳과 오탐 위험이 있어 좌표 탐색에서는 제외)
_HEADER_LABELS_KO = [
    ("name", ["품명", "품목", "물품명", "공사명", "공사명/품명", "제품명"]),
    ("spec", ["규격", "사양", "형식", "규격/색상"]),
    ("unit", ["단위"]),
    ("qty", ["수량"]),
    ("weight", ["중량", "무게"]),
    ("price", ["단가"]),
    ("printed_supply", ["공급가액", "공급가", "금액"]),
]


def _row_char_string(row_chars):
    """문자들을 x 순으로 정렬해 (문자열, [x중심,...]) 를 만든다(공백 문자는 제거)."""
    items = sorted(row_chars, key=lambda c: c["x0"])
    text_chars, centers = [], []
    for c in items:
        t = c.get("text", "")
        if t is None or t.strip() == "":
            continue
        text_chars.append(t)
        centers.append((c["x0"] + c["x1"]) / 2)
    return "".join(text_chars), centers


def _locate_labels_in_header(header_str, centers):
    """헤더 문자열에서 각 필드 라벨을 찾아 (field, x_center) 목록을 만든다."""
    found = {}
    for field, labels in _HEADER_LABELS_KO:
        for label in labels:
            idx = header_str.find(label)
            if idx >= 0:
                span = centers[idx:idx + len(label)]
                if span:
                    found[field] = sum(span) / len(span)
                break
    return found


def _find_header_row_coords(rows, char_rows):
    """char_rows: top 기준으로 묶은 (top, [char,...]) 목록. rows(word 기준)와 top 로 매칭.

    반환: (word_row_index, [(field, x_center), ...])  헤더가 없으면 None.
    """
    best = None  # (score, top, fields)
    for top, chars in char_rows:
        header_str, centers = _row_char_string(chars)
        if not header_str:
            continue
        found = _locate_labels_in_header(header_str, centers)
        keys = set(found)
        core = keys & {"name", "qty", "price", "printed_supply", "spec", "weight"}
        if "name" in keys and len(core) >= 2:
            score = len(found)
            if best is None or score > best[0]:
                best = (score, top, found)
    if best is None:
        return None
    _, htop, fields = best
    # word 기준 행에서 같은 top 의 행 인덱스를 찾는다
    hidx = min(range(len(rows)), key=lambda i: abs(rows[i]["top"] - htop))
    ordered = sorted(fields.items(), key=lambda kv: kv[1])
    return hidx, ordered


def _column_bounds(header_fields):
    """헤더 (field, x_center) 목록을 인접 중점으로 잘라 각 열의 [x_lo, x_hi) 범위로."""
    xs = [xc for _, xc in header_fields]
    bounds = []
    for i, (field, xc) in enumerate(header_fields):
        lo = -1e9 if i == 0 else (xs[i - 1] + xc) / 2
        hi = 1e9 if i == len(header_fields) - 1 else (xc + xs[i + 1]) / 2
        bounds.append((field, lo, hi))
    return bounds


_STOP_ROW_TOKENS = ("계", "합계", "소계", "이하여백", "이하 여백", "비고")


def _cluster_chars_by_top(chars, tol=4.0):
    """page.chars 를 top 기준으로 같은 줄끼리 묶어 [(top, [char,...]), ...]."""
    rows = []
    for c in sorted(chars, key=lambda x: (round(x["top"]), x["x0"])):
        placed = False
        for row in rows:
            if abs(row["top"] - c["top"]) <= tol:
                row["chars"].append(c)
                row["top"] = (row["top"] * row["n"] + c["top"]) / (row["n"] + 1)
                row["n"] += 1
                placed = True
                break
        if not placed:
            rows.append({"top": c["top"], "n": 1, "chars": [c]})
    rows.sort(key=lambda r: r["top"])
    return [(r["top"], r["chars"]) for r in rows]


def _extract_items_by_coords(page):
    """텍스트 레이어 단어 좌표로 품목 표를 복원한다. 실패 시 []"""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    rows = _cluster_rows_by_top(words)
    char_rows = _cluster_chars_by_top(page.chars)
    found = _find_header_row_coords(rows, char_rows)
    if not found:
        return []
    header_idx, header_fields = found
    bounds = _column_bounds(header_fields)

    items = []
    for row in rows[header_idx + 1:]:
        line_text = _join(row["words"])
        # 합계/소계/비고 줄에서 멈춘다
        stripped = line_text.replace(" ", "")
        if any(stripped.startswith(tok.replace(" ", "")) for tok in _STOP_ROW_TOKENS):
            break
        if not stripped:
            continue
        # 각 열 버킷에 단어를 담는다
        buckets = {field: [] for field, _, _ in bounds}
        for w in row["words"]:
            xc = (w["x0"] + w["x1"]) / 2
            for field, lo, hi in bounds:
                if lo <= xc < hi:
                    buckets[field].append(w["text"])
                    break
        name_tokens = [t for t in buckets.get("name", []) if t and t.strip()]
        # 순번 열(1,2,..)이 별도 헤더 없이 품명 왼쪽에 붙는 경우: 맨 앞 순수 숫자 토큰 제거
        if len(name_tokens) >= 2 and re.fullmatch(r"\d{1,3}[\.\)]?", name_tokens[0].strip()):
            name_tokens = name_tokens[1:]
        name = " ".join(name_tokens).strip()
        name = _strip_leading_index(name)
        if not name:
            continue
        item = {"name": name}
        for field in ("spec", "unit"):
            val = "".join(buckets.get(field, [])).strip()
            if val:
                item[field] = val
        for field in ("qty", "weight", "price"):
            num = P.parse_number(" ".join(buckets.get(field, [])))
            if num is not None:
                item[field] = num
        # printed_supply(금액)만 있고 price/qty 계산이 불가하면 supply 로 넣는다
        if "price" not in item:
            amt = P.parse_number(" ".join(buckets.get("printed_supply", [])))
            if amt is not None:
                item["supply"] = amt
        items.append(item)
    return items


def _strip_leading_index(name):
    """'1 각파이프' / '1.각파이프' 처럼 앞에 붙은 순번을 떼어낸다."""
    import re
    m = re.match(r"^\s*\d{1,3}[\.\)]?\s+(.+)$", name)
    if m and m.group(1).strip():
        # 순번만 있는 게 아니라 뒤에 실제 이름이 있을 때만
        return m.group(1).strip()
    return name.strip()


# ------------------------------------------------------------------ #
# XLSX 견적서
# ------------------------------------------------------------------ #

def _read_xlsx_quote(data_bytes, extra_fields=None):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data_bytes), data_only=True)
    warnings = []
    best = None  # (score, sheet, header_row_idx, colmap, grid)
    for ws in wb.worksheets:
        grid = [[c.value for c in row] for row in ws.iter_rows()]
        hit = _find_header_in_grid(grid, extra_fields)
        if hit:
            score, hidx, colmap = hit
            if best is None or score > best[0]:
                best = (score, ws.title, hidx, colmap, grid)
    if best is None:
        return {"items": [], "company": _guess_company_from_grid_all(wb),
                "title": None, "warnings": ["엑셀에서 품목 표를 찾지 못했습니다. 직접 확인해주세요."],
                "source": "xlsx"}
    _, sheet, hidx, colmap, grid = best
    items = _extract_items_from_grid(grid, hidx, colmap)
    company = _guess_company_from_grid_all(wb)
    return {"items": items, "company": company, "title": None,
            "warnings": warnings, "source": "xlsx"}


def _norm(v):
    return P.normalize_header("" if v is None else str(v))


def _find_header_in_grid(grid, extra_fields=None):
    best = None
    for r, row in enumerate(grid[:40]):
        colmap = {}
        for c, val in enumerate(row):
            field = P.match_field(val, synonyms=extra_fields) or P.match_field_fuzzy(val, synonyms=extra_fields)
            if field and field not in colmap:
                colmap[field] = c
        keys = set(colmap)
        core = keys & {"name", "qty", "price", "printed_supply", "spec", "weight"}
        if "name" in keys and len(core) >= 2:
            score = len(colmap)
            if best is None or score > best[0]:
                best = (score, r, colmap)
    return best


def _extract_items_from_grid(grid, hidx, colmap):
    items = []
    name_c = colmap.get("name")
    for row in grid[hidx + 1:]:
        if name_c is None or name_c >= len(row):
            continue
        name = row[name_c]
        name = "" if name is None else str(name).strip()
        sn = name.replace(" ", "")
        if not name:
            continue
        if any(sn.startswith(t.replace(" ", "")) for t in _STOP_ROW_TOKENS):
            break
        item = {"name": _strip_leading_index(name)}
        for field in ("spec", "unit"):
            c = colmap.get(field)
            if c is not None and c < len(row) and row[c] not in (None, ""):
                item[field] = str(row[c]).strip()
        for field in ("qty", "weight", "price"):
            c = colmap.get(field)
            if c is not None and c < len(row):
                num = P.parse_number(row[c])
                if num is not None:
                    item[field] = num
        if "price" not in item:
            c = colmap.get("printed_supply")
            if c is not None and c < len(row):
                num = P.parse_number(row[c])
                if num is not None:
                    item["supply"] = num
        items.append(item)
    return items


def _guess_company_from_grid_all(wb):
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for val in row:
                if val is None:
                    continue
                name = P.extract_company_name(str(val))
                if name:
                    return name
    return None


# ------------------------------------------------------------------ #
# 공개 진입점
# ------------------------------------------------------------------ #

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def read_quote(path=None, data_bytes=None, ext=None, extra_fields=None):
    """견적서 파일을 읽어 통합 스키마 dict 를 반환한다.

    path 또는 (data_bytes+ext) 중 하나를 준다.
    """
    if data_bytes is None:
        with open(path, "rb") as f:
            data_bytes = f.read()
    if ext is None and path:
        ext = os.path.splitext(path)[1]
    ext = (ext or "").lower()

    if ext in (".xlsx", ".xlsm", ".xls"):
        return _read_xlsx_quote(data_bytes, extra_fields=extra_fields)

    if ext in _IMAGE_EXTS:
        return _read_image_quote(data_bytes, extra_fields=extra_fields)

    # 기본: PDF
    return _read_pdf_quote(data_bytes, extra_fields=extra_fields)


def _read_pdf_quote(data_bytes, extra_fields=None):
    res = P.parse_pdf_items(data_bytes, extra_fields=extra_fields)
    items = res.get("items") or []
    warnings = list(res.get("warnings") or [])
    source = "pdf-table"

    if not items:
        # 텍스트 레이어가 있으면 좌표 폴백을 시도
        try:
            with pdfplumber.open(io.BytesIO(data_bytes)) as pdf:
                full_text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                if full_text.strip():
                    coord_items = []
                    for page in pdf.pages:
                        coord_items.extend(_extract_items_by_coords(page))
                    if coord_items:
                        items = coord_items
                        source = "pdf-coords"
                        warnings = [w for w in warnings if "표를" not in w]
                else:
                    source = "pdf-ocr"
        except Exception:
            pass
    return {
        "items": items,
        "company": res.get("company"),
        "title": res.get("title"),
        "warnings": warnings,
        "source": source,
    }


def _read_image_quote(data_bytes, extra_fields=None):
    from PIL import Image
    synonyms = None
    if extra_fields:
        synonyms = extra_fields
    img = Image.open(io.BytesIO(data_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    # _parse_scanned_pdf()(스캔 PDF 경로)와 동일하게, 회전 보정 후 그레이스케일->
    # 이진화->deskew->노이즈제거 전처리를 거친 이미지로 OCR한다.
    img = P._preprocess_for_ocr(P.fix_image_orientation(img))
    warnings = ["이미지(JPG/PNG) 견적서는 OCR로 인식했습니다. 인식 결과를 원본과 꼭 대조해주세요."]
    try:
        items, _mapping = P.ocr_extract_items(img, synonyms=synonyms)
        items = items or []
    except Exception as e:
        items = []
        warnings.append(f"OCR 품목 인식에 실패했습니다: {type(e).__name__}")
    company = None
    try:
        text = P.ocr_page_text(img)
        company = P.extract_company_name(text)
    except Exception:
        pass
    return {"items": items, "company": company, "title": None,
            "warnings": warnings, "source": "image-ocr"}
