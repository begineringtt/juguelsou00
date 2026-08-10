import base64
import io
import re

import fitz
import pdfplumber

HEADER_SYNONYMS = {
    "name": ["품명", "품 명", "공사명/품명", "물품명", "ITEM", "DESCRIPTION"],
    "spec": ["규격", "규 격", "SIZE", "형식", "규격/색상", "사양"],
    "unit": ["단위", "단 위", "UNIT"],
    "qty": ["수량", "수 량", "Q'TY", "QTY"],
    "price": ["단가", "단 가", "UNIT PRICE"],
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

_COMPANY_PATTERNS = [
    re.compile(rf"(?:\(주\)|㈜)\s*((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}})"),
    re.compile(rf"((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}}?)\s*(?:\(주\)|㈜)"),
    re.compile(rf"주식회사\s*((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}})"),
    re.compile(rf"((?:{_COMPANY_NAME_TOKEN}\s?){{2,20}}?)\s*주식회사"),
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


# max_scan is unused by any current caller (both call sites scan the whole
# table) — kept as an escape hatch if a future table ever needs capping.
def find_header_row(table, max_scan=None):
    best_idx, best_score = None, 0
    rows = table[:max_scan] if max_scan is not None else table
    for idx, row in enumerate(rows):
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


def _header_cell_leftover(cell_text):
    if not cell_text:
        return ""
    lines = str(cell_text).split("\n")
    last_label_idx = -1
    for idx, line in enumerate(lines):
        if match_field(line):
            last_label_idx = idx
    return "\n".join(lines[last_label_idx + 1:]).strip()


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

    header_row = table[mapping["data_start"] - 1]
    leftover = {}
    for indices in columns.values():
        for idx in indices:
            text = _header_cell_leftover(header_row[idx] if idx < len(header_row) else "")
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
        rows.append({
            "name": name,
            "spec": cell(raw_row, spec_col),
            "unit": cell(raw_row, unit_col),
            "qty_raw": cell(raw_row, qty_col),
            "price_raws": [cell(raw_row, c) for c in price_cols],
        })
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
        resolved.append({
            "name": row["name"],
            "spec": row["spec"],
            "unit": row["unit"],
            "qty": qty,
            "price": _pick_price(qty, row["price_raws"]),
        })
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
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        company = extract_company_name(full_text)
        title = extract_title(full_text)

        best_table = _find_best_table(pdf)
        mapping = map_table_columns(best_table) if best_table else None

        if mapping:
            raw_rows = extract_items_from_table(best_table, mapping)
            resolved_rows = resolve_duplicate_price_columns(raw_rows)
            cleaned_rows = clean_item_rows(resolved_rows)
            items = apply_hierarchical_prefix(cleaned_rows)
        else:
            fallback_item = extract_paragraph_fallback(full_text)
            if fallback_item:
                items = [fallback_item]
                warnings.append("표를 찾지 못해 일부 항목만 인식했습니다. 나머지는 직접 입력해주세요.")
            else:
                items = []
                warnings.append("표를 인식하지 못했습니다. 직접 입력해주세요.")

    return {"items": items, "page_images": page_images, "warnings": warnings, "company": company, "title": title}
