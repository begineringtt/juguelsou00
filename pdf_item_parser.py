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
