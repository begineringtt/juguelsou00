import base64
import io
import os
import re

import fitz
import pdfplumber
import pytesseract
from PIL import Image

import paths

OCR_LANG = "kor+eng"

_tesseract_configured = False


def _configure_tesseract():
    """번들된 Tesseract(tesseract_bin/)가 있으면 그걸 쓰고, 없으면 시스템 PATH에
    설치된 tesseract를 그대로 쓴다(개발 환경에서 시스템 설치본으로 테스트할 때 대비)."""
    global _tesseract_configured
    if _tesseract_configured:
        return
    bundled_dir = os.path.join(paths.bundle_dir(), "tesseract_bin")
    exe_path = os.path.join(bundled_dir, "tesseract.exe")
    if os.path.isfile(exe_path):
        pytesseract.pytesseract.tesseract_cmd = exe_path
        os.environ["TESSDATA_PREFIX"] = os.path.join(bundled_dir, "tessdata")
    _tesseract_configured = True


class OCRUnavailableError(Exception):
    """Tesseract 실행 파일을 찾을 수 없을 때."""

HEADER_SYNONYMS = {
    "name": ["품명", "품 명", "공사명/품명", "물품명", "ITEM", "DESCRIPTION"],
    "spec": ["규격", "규 격", "SIZE", "형식", "규격/색상", "사양"],
    "unit": ["단위", "단 위", "UNIT"],
    "qty": ["수량", "수 량", "Q'TY", "QTY", "QUANTITY"],
    "price": ["단가", "단 가", "UNIT PRICE", "PRICE"],
    "weight": ["중량", "중 량", "중량(KG)", "무게", "WEIGHT", "W'T", "WT"],
}

_NUMBER_RE = re.compile(r"[0-9][0-9,.\s]*[0-9]|[0-9]")

# 견적서 PDF에서 업체명(공급자)을 추정할 때 쓰는 패턴들.
# 그린플러스는 견적서를 받는 우리 회사라서, 후보에서 항상 제외해야 공급자명과
# 헷갈리지 않는다 ("수신 : ㈜그린플러스 貴下" 같은 문구가 공급자명 자리에
# 오인식되는 걸 방지).
_OUR_COMPANY_MARKERS = ["그린플러스", "GREENPLUS", "GREEN PLUS", "GREEN-PLUS"]

_COMPANY_LABEL_PATTERNS = [
    r"상\s*호",
    r"업\s*체\s*(?:명|/\s*대표)?",
    r"회\s*사\s*명",
    r"발\s*신(?:\s*처)?",
    r"공\s*급\s*자",
]

_COMPANY_STOP_LABELS = re.compile(
    r"(대\s*표\s*자|대\s*표|사업자\s*등록\s*번호|사업자\s*번호|등록\s*번호|"
    r"업\s*태|종\s*목|주\s*소|전\s*화|담당자|담\s*당|TEL|FAX)"
)

_COMPANY_NAME_TOKEN = r"[가-힣A-Za-z0-9&\.\-]"

# OCR 결과는 "주 식 회 사"처럼 한 글자씩 띄어 나오는 경우가 흔해서, 트리거
# 문구("(주)"/"㈜"/"주식회사") 내부에도 \s*를 넣어 이런 스캔본에서도 매칭되게 한다.
_COMPANY_PATTERNS = [
    re.compile(rf"(?:\(\s*주\s*\)|㈜)\s*((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}})"),
    re.compile(rf"((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}}?)\s*(?:\(\s*주\s*\)|㈜)"),
    re.compile(rf"주\s*식\s*회\s*사\s*((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}})"),
    re.compile(rf"((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}}?)\s*주\s*식\s*회\s*사"),
]


def _collapse_spaced_tokens(text):
    """'(주) 일 신 폴 리 캠' 처럼 한 글자씩 띄어 쓴 PDF 추출 결과를 붙여준다."""
    tokens = text.split()
    if tokens and all(len(t) == 1 for t in tokens):
        return "".join(tokens)
    return text.strip()


def _is_our_company(text):
    normalized = text.replace(" ", "").upper()
    return any(marker.replace(" ", "").upper() in normalized for marker in _OUR_COMPANY_MARKERS)


def _clean_company_candidate(text):
    text = _COMPANY_STOP_LABELS.split(text)[0]
    text = text.strip().strip(":：").strip()
    text = re.sub(r"(貴下|귀하)$", "", text).strip()
    return _collapse_spaced_tokens(text)


def extract_company_name(text):
    """견적서 전체 텍스트에서 공급자(업체명)로 추정되는 이름을 뽑아낸다.

    1) "상호"/"업체"/"회사명"/"발신"/"공급자" 같은 라벨이 붙은 값을 우선 사용하되,
       그린플러스(수신처)를 가리키는 경우는 건너뛴다.
    2) 라벨을 못 찾으면 문서 전체에서 "(주)"/"㈜"/"주식회사"가 붙은 이름을 모아
       가장 많이 반복되는 것을 고른다 (공급자명은 머리글/도장/계좌 예금주 등에
       반복 등장하는 경우가 많다).
    실패하면 None을 반환한다 (직접 입력하도록 둔다).
    """
    lines = text.split("\n")

    for line in lines:
        for pattern in _COMPANY_LABEL_PATTERNS:
            m = re.search(pattern + r"\s*[:：]?\s*(.+)", line)
            if not m:
                continue
            value = re.split(r"[\|/]", m.group(1).strip())[0]
            value = _clean_company_candidate(value)
            if value and not _is_our_company(value) and len(value) <= 20:
                return value

    counts = {}
    first_seen = {}
    for idx, line in enumerate(lines):
        if _is_our_company(line):
            continue
        for pattern in _COMPANY_PATTERNS:
            for m in pattern.finditer(line):
                candidate = _clean_company_candidate(m.group(1))
                if not candidate or _is_our_company(candidate):
                    continue
                counts[candidate] = counts.get(candidate, 0) + 1
                first_seen.setdefault(candidate, idx)

    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))[0][0]


# 견적서 PDF의 "내용"/"물품명"/"견적명"/"제목"에 해당하는 라벨들 (한글/한문/영문
# 표기가 뒤섞여 있어 전부 나열해 둔다). 지출결의서의 "내용(제목)" 칸에 그대로
# 옮겨 적을 수 있도록 값만 뽑아낸다.
_TITLE_LABEL_PATTERNS = [
    r"내\s*용",
    r"물\s*품\s*명",
    r"견\s*적\s*명",
    r"제\s*목",
    r"見\s*積\s*名",  # 견적명 (한문 표기)
    r"品\s*名",       # 품명 (한문 표기)
    r"SUBJECT",
    r"TITLE",
]

# 라벨 값 뒤에 주소/연락처 등이 공백만 두고 바로 이어붙는 PDF가 많아서,
# 이런 표시가 나오면 그 앞까지만 값으로 인정한다.
_TITLE_STOP_WORDS = re.compile(
    r"(특별자치시|특별자치도|광역시|특별시|[가-힣]{2,4}시\s|[가-힣]{2,4}군\s|[가-힣]{2,4}구\s|"
    r"TEL|FAX|담당자|담\s*당|전\s*화|주\s*소|연락처|연\s*락)"
)

_TITLE_MAX_LEN = 40


def _clean_title_candidate(text):
    text = text.split("|")[0]
    text = _TITLE_STOP_WORDS.split(text)[0]
    text = text.strip().strip(":：").strip()
    if len(text) > _TITLE_MAX_LEN:
        text = text[:_TITLE_MAX_LEN].strip()
    return text


_TITLE_CASE_SUFFIX = "의 건"


def _ensure_case_suffix(title):
    """지출결의서 "내용" 칸 관례대로 "~의 건"으로 끝나도록 붙여준다.

    이미 "건"으로 끝나는 문구(예: "...발송의 건")는 중복으로 붙지 않게 둔다.
    """
    if title.rstrip(" .!").endswith("건"):
        return title
    return f"{title}{_TITLE_CASE_SUFFIX}"


def extract_title(text):
    """견적서 전체 텍스트에서 "내용(제목)"으로 옮겨 적을 문구를 찾는다.

    "내용"/"물품명"/"견적명"/"제목"(한문 표기 見積名/品名, 영문 SUBJECT/TITLE 포함)
    라벨 뒤에 콜론(:/：)이 붙은 값만 인정한다 - 콜론이 없으면 품목 표의 열 제목
    ("DESCRIPTION" 등)과 헷갈릴 수 있어서다. 못 찾으면 None (직접 입력하도록 둔다).
    지출결의서 관례에 맞춰 끝에 "의 건"을 붙여서 반환한다.
    """
    for line in text.split("\n"):
        for pattern in _TITLE_LABEL_PATTERNS:
            m = re.search(pattern + r"\s*[:：]\s*(.+)", line)
            if not m:
                continue
            value = _clean_title_candidate(m.group(1))
            if value:
                return _ensure_case_suffix(value)
    return None


def normalize_header(text):
    if text is None:
        return ""
    text = str(text).replace("\n", " ")
    text = re.sub(r"\s+", "", text)
    return text.strip().upper()


def _merge_synonyms(synonyms):
    """synonyms는 기존 HEADER_SYNONYMS에 "추가"되는 커스텀 동의어로 취급한다
    (완전히 대체하는 게 아니라 병합한다) - 그래야 extra_fields로 커스텀 필드
    하나만 넘겨도 품명/수량/단가 같은 기본 필드 인식이 사라지지 않는다."""
    if not synonyms:
        return HEADER_SYNONYMS
    merged = dict(HEADER_SYNONYMS)
    merged.update(synonyms)
    return merged


def match_field(header_text, synonyms=None):
    if not header_text:
        return None
    synonyms = _merge_synonyms(synonyms)
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
    synonyms = _merge_synonyms(synonyms)
    best_field, best_len = None, 0
    for field, syns in synonyms.items():
        for syn in syns:
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


# max_scan is unused by any current caller (both call sites scan the whole
# table) — kept as an escape hatch if a future table ever needs capping.
def find_header_row(table, max_scan=None, synonyms=None):
    best_idx, best_score = None, 0
    rows = table[:max_scan] if max_scan is not None else table
    for idx, row in enumerate(rows):
        score = sum(1 for cell in row if match_field(cell, synonyms=synonyms) or match_field_fuzzy(cell, synonyms=synonyms))
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
        field = match_field(cell, synonyms=synonyms) or match_field_fuzzy(cell, synonyms=synonyms)
        if field:
            columns.setdefault(field, []).append(idx)
    if "name" not in columns or ("qty" not in columns and "price" not in columns):
        return None
    return {"columns": columns, "data_start": header_idx + 1}


def _header_cell_leftover(cell_text, synonyms=None):
    if not cell_text:
        return ""
    lines = str(cell_text).split("\n")
    last_label_idx = -1
    for idx, line in enumerate(lines):
        if match_field(line, synonyms=synonyms):
            last_label_idx = idx
    return "\n".join(lines[last_label_idx + 1:]).strip()


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


SUMMARY_KEYWORDS = ["합계", "소계", "이하", "총액", "TOTAL", "SUB TOTAL", "TAX", "REMARK"]


def clean_item_rows(rows):
    cleaned = []
    for row in rows:
        normalized_name = normalize_header(row["name"])
        if any(normalize_header(keyword) in normalized_name for keyword in SUMMARY_KEYWORDS):
            continue
        cleaned.append(row)
    return cleaned


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


def render_page_images(pdf_bytes, zoom=1.5):
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        matrix = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            images.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
    finally:
        doc.close()
    return images


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


def _find_best_table(pdf, synonyms=None):
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
            score = score_table(table, synonyms=synonyms)
            if score > best_score:
                best_table, best_score = table, score
    return best_table


def _render_pages_for_ocr(pdf_bytes, zoom=3.0):
    """OCR용으로 미리보기(zoom=1.5)보다 더 높은 해상도로 각 페이지를 렌더링한다."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        matrix = fitz.Matrix(zoom, zoom)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            images.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("L"))
        return images
    finally:
        doc.close()


def ocr_page_text(pil_image):
    _configure_tesseract()
    try:
        return pytesseract.image_to_string(pil_image, lang=OCR_LANG, config="--psm 6")
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError(str(exc)) from exc


def _ocr_words(pil_image):
    data = pytesseract.image_to_data(
        pil_image, lang=OCR_LANG, config="--psm 6", output_type=pytesseract.Output.DICT
    )
    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if conf < 0:
            continue
        words.append({
            "text": text,
            "left": data["left"][i],
            "top": data["top"][i],
            "height": data["height"][i],
        })
    return words


def _cluster_words_into_rows(words):
    """단어들을 y좌표 기준으로 묶어서 표의 "행"처럼 재구성한다.

    Tesseract가 매기는 line_num은 표 셀 배치를 신뢰성 있게 반영하지 않는 경우가
    많아서, 대신 단어 중심 y좌표가 서로 가까우면(평균 글자 높이의 60% 이내) 같은
    행으로 묶는 방식을 쓴다.
    """
    if not words:
        return []
    words = sorted(words, key=lambda w: w["top"])
    avg_height = sum(w["height"] for w in words) / len(words)
    tolerance = max(avg_height * 0.6, 5)

    rows = []
    for w in words:
        center = w["top"] + w["height"] / 2
        for row in rows:
            if abs(row["center"] - center) <= tolerance:
                row["center"] = (row["center"] * row["count"] + center) / (row["count"] + 1)
                row["count"] += 1
                row["words"].append(w)
                break
        else:
            rows.append({"center": center, "count": 1, "words": [w]})

    rows.sort(key=lambda r: r["center"])
    for row in rows:
        row["words"].sort(key=lambda w: w["left"])
    return rows


# Tesseract는 표 테두리/얼룩을 "_", "|", "." 같은 구두점 전용 "단어"로 잡아내는
# 경우가 많다. 라벨 토큰을 이어붙일 때 이런 잡음은 건너뛴다(예: "품" "_" "명"
# 세 단어를 "품명"으로 이어붙일 수 있게).
_NOISE_TOKEN_RE = re.compile(r"^[|_.,:;·•\-~`'\"]+$")


def _could_seed_label(token_text, synonyms=None):
    """이 토큰이 실제 라벨(품명/규격/...)의 일부일 가능성이 있는지 본다.

    행 번호("No")처럼 라벨과 무관한 토큰이 이어붙이기 시작점이 되어, 뒤따르는
    진짜 라벨 토큰까지 함께 삼켜서 잘못된 위치를 라벨 열로 오인하는 것을
    막기 위한 필터다 (예: "No"+"품"+"명" -> "No품명"도 "품명"을 부분 문자열로
    포함하므로 필터 없이는 "No" 위치가 품명 열로 오인식된다).
    """
    synonyms = _merge_synonyms(synonyms)
    normalized = normalize_header(token_text)
    if not normalized:
        return False
    for syns in synonyms.values():
        for syn in syns:
            if normalized in normalize_header(syn):
                return True
    return False


def _label_field_for_prefix(normalized_prefix, synonyms=None):
    """normalized_prefix가 어떤 라벨과 (접두사로) 정확히 일치하는지 본다.

    match_field_fuzzy의 "부분 문자열 포함" 판정은 여기서는 쓰지 않는다 - 그
    판정을 쓰면 예를 들어 "명"(품명의 뒤 글자)에서 이어붙이기를 시작했을 때
    다음 라벨의 글자들을 더 삼켜서 "명규격"이 "규격"을 부분 문자열로 포함해
    버리는 오탐이 생긴다. 접두사 일치로 제한하면 이어붙이기가 실제로 시작
    지점(seed)에 해당하는 라벨만 완성했을 때만 매칭된다.
    """
    synonyms = _merge_synonyms(synonyms)
    best_field, best_len = None, 0
    for field, syns in synonyms.items():
        for syn in syns:
            syn_norm = normalize_header(syn)
            if syn_norm and normalized_prefix.startswith(syn_norm) and len(syn_norm) > best_len:
                best_field, best_len = field, len(syn_norm)
    return best_field


def _match_row_labels(words, max_window=3, synonyms=None):
    """행의 OCR 단어들 중 품명/규격/수량/단가 등 헤더 라벨을 찾는다.

    Tesseract가 한글 라벨을 음절 단위로 쪼개 별도 "단어"로 인식하는 경우가
    많아서(예: "품명" -> "품", "명"), 단어 하나만 보는 정확/부분 일치로는
    라벨을 못 찾는다. 그래서 인접한 단어 여러 개(최대 max_window개, 잡음
    토큰은 건너뛰고)를 이어붙인 문자열도 함께 검사한다.
    """
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
    """행들 중 품명/규격/수량/단가 등 라벨이 가장 많이 매칭되는 행을 찾는다.

    OCR 결과는 오탈자가 섞이기 쉬워서 정확 일치(match_field)가 아니라 부분 일치
    (match_field_fuzzy)로 라벨을 찾는다.
    """
    best_idx, best_fields, best_score = None, None, 0
    for idx, row in enumerate(rows):
        fields = _match_row_labels(row["words"], synonyms=synonyms)
        if "name" in fields and len(fields) > best_score:
            best_idx, best_fields, best_score = idx, fields, len(fields)
    return best_idx, best_fields


def _build_table_from_ocr_rows(rows, header_idx, header_fields):
    """헤더 라벨의 x좌표를 열 기준점으로 삼아, 이후 행의 단어들을 가장 가까운
    기준점에 배정한다. 결과는 기존 pdfplumber 표 처리 로직(map_table_columns 이후
    단계)이 그대로 재사용 가능한 2차원 셀 리스트 형태다.
    """
    anchors = sorted(
        (left, field) for field, lefts in header_fields.items() for left in lefts
    )
    col_count = len(anchors)

    def assign_row(row_words):
        cells = [""] * col_count
        for w in row_words:
            col = min(range(col_count), key=lambda i: abs(anchors[i][0] - w["left"]))
            cells[col] = f"{cells[col]} {w['text']}".strip()
        return cells

    table = [assign_row(row["words"]) for row in rows[header_idx:]]
    columns = {}
    for col_idx, (_, field) in enumerate(anchors):
        columns.setdefault(field, []).append(col_idx)
    return table, {"columns": columns, "data_start": 1}


def ocr_extract_items(pil_image, synonyms=None):
    """스캔 페이지 이미지에서 OCR로 품목 표를 재구성해본다. 헤더 라벨을 못 찾거나
    수량/단가 열이 전혀 없으면 None (표를 못 찾은 것으로 보고 상위에서 다른 방법으로
    대체하도록 한다)."""
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

    # extract_items_from_table()의 "헤더 셀에 다음 데이터가 같이 붙어 있으면
    # 살려낸다" 로직은 pdfplumber가 뽑아낸, 노이즈 없는 표 셀을 전제로 한다.
    # OCR로 재구성한 헤더 행 텍스트는 잡음이 섞여 알려진 라벨과 정확히 일치하는
    # 경우가 거의 없어서, 그 로직이 노이즈투성이 라벨 전체를 가짜 품목 행으로
    # 만들어버린다. OCR 표에는 이 융합 케이스가 없으므로 헤더 행을 비워서 막는다.
    table[0] = ["" for _ in table[0]]

    raw_rows = extract_items_from_table(table, mapping, synonyms=synonyms)
    resolved_rows = resolve_duplicate_price_columns(raw_rows)
    cleaned_rows = clean_item_rows(resolved_rows)
    return apply_hierarchical_prefix(cleaned_rows)


def _extract_large_embedded_images(pdf_bytes, min_area_ratio=0.15):
    """일부 스캔 PDF는 전체 페이지를 저해상도 배경(JPEG)으로 깔고, 실제 글자는
    고해상도 1비트 스캔 이미지(팩스 CCITT 등)를 별도 객체로 그 위에 얹는다.
    이런 문서는 페이지 전체를 한 번에 렌더링하면 확대(zoom)를 얼마나 올리든
    리샘플링 과정에서 작은 글자(표 헤더/품목)가 뭉개져 OCR이 거의 불가능해
    진다 - 반면 그 원본 이미지를 리샘플링 없이 그대로 추출해서 OCR하면 훨씬
    정확하다. 페이지 면적의 상당 부분(기본 15% 이상)을 덮는 임베드 이미지가
    있으면 그걸 별도 OCR 후보로 반환한다."""
    images = []
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page in doc:
            page_area = page.rect.width * page.rect.height
            if not page_area:
                continue
            for img in page.get_images(full=True):
                xref = img[0]
                for rect in page.get_image_rects(xref):
                    if (rect.width * rect.height) / page_area < min_area_ratio:
                        continue
                    try:
                        base = doc.extract_image(xref)
                        pil_img = Image.open(io.BytesIO(base["image"])).convert("L")
                    except Exception:
                        continue
                    images.append(pil_img)
    finally:
        doc.close()
    return images


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


def _detect_field_order(mapping):
    """mapping["columns"]에 기록된 열 인덱스(왼쪽->오른쪽) 순서대로 필드 키 목록을
    돌려준다 (품명 제외). 화면에서 품목 표 열 순서를 PDF와 맞추는 데 쓴다."""
    if not mapping:
        return None
    columns = mapping.get("columns") or {}
    fields = [field for field in columns if field != "name"]
    return sorted(fields, key=lambda field: min(columns[field]))


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
                "field_order": None,
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

        field_order = _detect_field_order(mapping)

    return {
        "items": items,
        "page_images": page_images,
        "warnings": warnings,
        "company": company,
        "title": title,
        "field_order": field_order,
    }
