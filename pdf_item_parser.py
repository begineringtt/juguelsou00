import base64
import io
import re

import fitz
import pdfplumber

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
    matrix = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        images.append(base64.b64encode(pix.tobytes("png")).decode("ascii"))
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
