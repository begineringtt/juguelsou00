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
