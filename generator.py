"""지출결의서(支出決議書) 엑셀 파일 자동 생성 로직.

template_files/base_template.xlsx 를 원본으로 하여, 사용자가 입력한 값으로
채운 새 엑셀 파일을 만들어 낸다. 품목 개수는 1개 이상 자유롭게 늘어날 수 있다
(단, 새 양식(rev.2)은 결재란/회사명 각주가 고정 위치라 품목 칸 수에 상한이 있다.
MAX_ITEM_ROWS 참고).

rev.2 양식은 품목 표/과제 정보 영역(11~27행)이 완전히 빈 캔버스로 제공되어
서식을 캡처할 참조 행이 없다. 그래서 폰트/테두리를 코드에서 직접 구성해서
매번 새로 그리는 방식으로 구현한다.
"""

import datetime
import io
import os

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter

from paths import bundle_dir

BASE_DIR = bundle_dir()
TEMPLATE_PATH = os.path.join(BASE_DIR, "template_files", "base_template.xlsx")

SHEET_NAME = "지출결의서"

FONT_NAME = "굴림"
FONT_REGULAR = Font(name=FONT_NAME, size=10)
FONT_BOLD = Font(name=FONT_NAME, size=10, bold=True)
ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_LEFT = Alignment(horizontal="left", vertical="center")

_THIN_SIDE = Side(style="thin")
_NO_SIDE = Side(style=None)

# base_template.xlsx (rev.2) 기준 고정 좌표
PROJECT_INFO_ROWS = {
    "agency": 11,
    "org": 12,
    "project_name": 13,
    "execution_note": 14,
}
PROJECT_INFO_START_COL = 2  # B
PROJECT_INFO_END_COL = 29   # AC

ITEM_HEADER_ROW = 16
FIRST_ITEM_ROW = 17
LAST_USABLE_ROW = 27  # 이 아래(28행)부터는 재무부서 결재란이 고정되어 있어 침범 불가

TABLE_START_COL = 2   # B
TABLE_END_COL = 28    # AB
TABLE_WIDTH = TABLE_END_COL - TABLE_START_COL + 1  # 27

# 품목 헤더(1) + 이하 여백(1) + 합계 금액(1) 을 제외한 나머지가 품목 최대 개수
MAX_ITEM_ROWS = LAST_USABLE_ROW - FIRST_ITEM_ROW - 1  # 9

ITEM_FIELDS = [
    ("name", "품목", 4, None),
    ("spec", "규격", 3, "use_spec"),
    ("unit", "단위", 2, "use_unit"),
    ("qty", "수량", 2, "use_qty"),
    ("price", "단가", 3, "use_price"),
    ("supply", "공급가", 3, None),
    ("vat", "부가세", 3, None),
]


def _largest_remainder_allocation(weights, total):
    weight_sum = sum(weights)
    raw = [w / weight_sum * total for w in weights]
    floors = [int(x) for x in raw]
    remainder = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:remainder]:
        floors[i] += 1
    return floors


def _infer_flags(items):
    return {
        "use_spec": any("spec" in item for item in items),
        "use_unit": any("unit" in item for item in items),
        "use_qty": any("qty" in item for item in items),
        "use_price": any("price" in item for item in items),
    }


def _compute_column_layout(flags):
    active = [f for f in ITEM_FIELDS if f[3] is None or flags.get(f[3])]
    weights = [f[2] for f in active]
    spans = _largest_remainder_allocation(weights, TABLE_WIDTH)

    layout = {}
    col = TABLE_START_COL
    for (key, label, _weight, _flag), span in zip(active, spans):
        layout[key] = (col, col + span - 1, label)
        col += span
    return layout


def _col_letter(layout, key):
    return get_column_letter(layout[key][0])


def _style_span(ws, row, start_col, end_col, font, alignment=ALIGN_CENTER):
    """병합 구간(start_col~end_col)에 테두리(바깥쪽 thin)와 폰트/정렬을 적용한다."""
    for col in range(start_col, end_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.border = Border(
            left=_THIN_SIDE if col == start_col else _NO_SIDE,
            right=_THIN_SIDE if col == end_col else _NO_SIDE,
            top=_THIN_SIDE,
            bottom=_THIN_SIDE,
        )
        cell.font = font
        cell.alignment = alignment


def _add_item_row_merges(ws, row, layout):
    for start, end, _label in layout.values():
        if end > start:
            ws.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)


def _rebuild_header_row(ws, layout):
    for start, end, label in layout.values():
        if end > start:
            ws.merge_cells(start_row=ITEM_HEADER_ROW, start_column=start,
                            end_row=ITEM_HEADER_ROW, end_column=end)
        ws.cell(row=ITEM_HEADER_ROW, column=start).value = label
        _style_span(ws, ITEM_HEADER_ROW, start, end, FONT_BOLD)


def _write_item_row(ws, row, layout, item, supply_letter):
    ws[f"{_col_letter(layout, 'name')}{row}"] = item["name"]
    if "spec" in layout and item.get("spec"):
        ws[f"{_col_letter(layout, 'spec')}{row}"] = item["spec"]
    if "unit" in layout and item.get("unit"):
        ws[f"{_col_letter(layout, 'unit')}{row}"] = item["unit"]

    use_qty = "qty" in layout and item.get("qty") is not None
    use_price = "price" in layout and item.get("price") is not None
    if use_qty:
        ws[f"{_col_letter(layout, 'qty')}{row}"] = item["qty"]
    if use_price:
        price_letter = _col_letter(layout, "price")
        ws[f"{price_letter}{row}"] = item["price"]
        if use_qty:
            qty_letter = _col_letter(layout, "qty")
            ws[f"{supply_letter}{row}"] = f"={qty_letter}{row}*{price_letter}{row}"
        else:
            ws[f"{supply_letter}{row}"] = f"={price_letter}{row}"
    else:
        ws[f"{supply_letter}{row}"] = item.get("supply", 0)
    ws[f"{_col_letter(layout, 'vat')}{row}"] = f"={supply_letter}{row}/10"

    _add_item_row_merges(ws, row, layout)
    for start, end, _label in layout.values():
        _style_span(ws, row, start, end, FONT_REGULAR)


def _rebuild_item_section(ws, items):
    """품목 표(헤더~합계 금액)를 11~27행 사이의 빈 캔버스에 새로 그린다.

    반환값: total_row (합계 금액 행 번호)
    """
    if len(items) > MAX_ITEM_ROWS:
        raise ValueError(
            f"품목이 너무 많습니다 (최대 {MAX_ITEM_ROWS}개, 입력 {len(items)}개). "
            "새 지출결의서 양식은 품목 칸이 고정되어 있어 여러 건으로 나눠서 작성해주세요."
        )

    flags = _infer_flags(items)
    layout = _compute_column_layout(flags)
    supply_letter = _col_letter(layout, "supply")

    _rebuild_header_row(ws, layout)

    row = FIRST_ITEM_ROW
    for item in items:
        _write_item_row(ws, row, layout, item, supply_letter)
        row += 1

    table_start_letter = get_column_letter(TABLE_START_COL)

    blank_row = row
    table_end_letter = get_column_letter(TABLE_END_COL)
    ws.merge_cells(f"{table_start_letter}{blank_row}:{table_end_letter}{blank_row}")
    ws[f"{table_start_letter}{blank_row}"] = "이하 여백"
    _style_span(ws, blank_row, TABLE_START_COL, TABLE_END_COL, FONT_REGULAR)
    row += 1

    total_row = row
    ws[f"{table_start_letter}{total_row}"] = "합계 금액"
    ws[f"{supply_letter}{total_row}"] = f"=SUM({supply_letter}{FIRST_ITEM_ROW}:{table_end_letter}{blank_row})"
    supply_start_col = layout["supply"][0]
    label_end_letter = get_column_letter(supply_start_col - 1)
    ws.merge_cells(f"{table_start_letter}{total_row}:{label_end_letter}{total_row}")
    ws.merge_cells(f"{supply_letter}{total_row}:{table_end_letter}{total_row}")
    _style_span(ws, total_row, TABLE_START_COL, supply_start_col - 1, FONT_BOLD)
    _style_span(ws, total_row, supply_start_col, TABLE_END_COL, FONT_BOLD)

    ws["S5"] = f"={supply_letter}{total_row}"

    return total_row


def _write_project_info_line(ws, row, text):
    end_letter = get_column_letter(PROJECT_INFO_END_COL)
    ws.merge_cells(f"B{row}:{end_letter}{row}")
    cell = ws.cell(row=row, column=PROJECT_INFO_START_COL)
    cell.value = text
    cell.font = FONT_BOLD
    cell.alignment = ALIGN_LEFT


def _to_excel_date(value):
    if not value:
        return None
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def build_expense_report(data):
    """입력 데이터(dict)를 받아 완성된 워크북을 BytesIO 로 반환한다.

    data 예시는 모듈 하단 __main__ 참고.
    """
    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    ws = wb.worksheets[0]
    ws.title = SHEET_NAME

    ws["D6"] = data.get("company", "")
    ws["Q6"] = data.get("doc_number") or None

    propose_date = _to_excel_date(data.get("propose_date"))
    if propose_date:
        ws["D7"] = propose_date
        ws["D7"].number_format = "yyyy-mm-dd"

    spend_date = _to_excel_date(data.get("spend_date"))
    if spend_date:
        ws["D8"] = spend_date
        ws["D8"].number_format = "yyyy-mm-dd"

    ws["Q7"] = data.get("department", "그린연구소")
    ws["Q8"] = data.get("requester", "")
    ws["D9"] = data.get("title", "")
    ws["D10"] = data.get("detail", "")

    agency = data.get("agency", "")
    org = data.get("org", "")
    project_name = data.get("project_name", "")
    _write_project_info_line(ws, PROJECT_INFO_ROWS["agency"], f"중앙행정기관 : {agency}" if agency else "")
    _write_project_info_line(ws, PROJECT_INFO_ROWS["org"], f"전문기관 : {org}" if org else "")
    _write_project_info_line(ws, PROJECT_INFO_ROWS["project_name"], f"과제명 : {project_name}" if project_name else "")
    _write_project_info_line(ws, PROJECT_INFO_ROWS["execution_note"], data.get("execution_note", ""))

    items = data.get("items") or []
    if not items:
        raise ValueError("품목이 최소 1개 이상 필요합니다.")
    _rebuild_item_section(ws, items)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


def suggest_filename(data):
    company = (data.get("company") or "업체명미상").replace(" ", "")
    date_str = (data.get("propose_date") or "").replace("-", "")
    if not date_str:
        date_str = "00000000"
    return f"지출결의서_{company}_{date_str}.xlsx"
