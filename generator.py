"""지출결의서(支出決議書) 엑셀 파일 자동 생성 로직.

template_files/base_template.xlsx 를 원본으로 하여, 사용자가 입력한 값으로
채운 새 엑셀 파일을 만들어 낸다. 품목 개수는 1개 이상 자유롭게 늘어날 수 있다.

주의: openpyxl 의 insert_rows/delete_rows 는 병합 셀(merged cell) 범위를
안정적으로 밀어주지 못한다 (실제 테스트 결과 stale 한 병합 범위가 남는 문제 확인).
그래서 품목 표 아래쪽(품목 행 ~ 하단 각주)은 매번 완전히 지우고, 캡처해 둔
서식을 이용해 필요한 행 수만큼 직접 새로 쌓아 올리는 방식으로 구현한다.
"""

import copy
import datetime
import io
import os

import openpyxl
from openpyxl.styles import Border, Side
from openpyxl.utils import get_column_letter

from paths import bundle_dir

BASE_DIR = bundle_dir()
TEMPLATE_PATH = os.path.join(BASE_DIR, "template_files", "base_template.xlsx")

SHEET_NAME = "지출결의서"

MAX_STYLE_COL = 30  # A ~ AD

# base_template.xlsx 원본 기준 고정 좌표
ITEM_HEADER_ROW = 23
FIRST_ITEM_ROW = 24
REF_ITEM_ROW = 24       # 품목 행 서식 참조
REF_BLANK_ROW = 26      # '이하 여백' 행 서식 참조
REF_TOTAL_ROW = 27      # '합계 금액' 행 서식 참조
REF_GAP1_ROW = 28
REF_GAP2_ROW = 29       # D:V 병합이 있는 여백 행
REF_GAP3_ROW = 30
REF_FOOTER_ROW = 31
OLD_LAST_ROW = 31

TABLE_START_COL = 3   # C
TABLE_END_COL = 22    # V
TABLE_WIDTH = TABLE_END_COL - TABLE_START_COL + 1  # 20

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


def _capture_row_style(ws, row):
    styles = []
    for col in range(1, MAX_STYLE_COL + 1):
        c = ws.cell(row=row, column=col)
        styles.append(
            {
                "font": copy.copy(c.font),
                "border": copy.copy(c.border),
                "fill": copy.copy(c.fill),
                "alignment": copy.copy(c.alignment),
                "number_format": c.number_format,
                "protection": copy.copy(c.protection),
            }
        )
    height = ws.row_dimensions[row].height
    return {"cells": styles, "height": height}


def _apply_row_style(ws, row, row_style):
    for idx, st in enumerate(row_style["cells"]):
        col = idx + 1
        c = ws.cell(row=row, column=col)
        c.font = st["font"]
        c.border = st["border"]
        c.fill = st["fill"]
        c.alignment = st["alignment"]
        c.number_format = st["number_format"]
        c.protection = st["protection"]
    ws.row_dimensions[row].height = row_style["height"]


_THIN_SIDE = Side(style="thin")
_NO_SIDE = Side(style=None)


def _capture_field_styles(ws, row):
    """해당 행의 '앵커 서식'과 '빈 칸 서식'을 캡처한다.

    품목 표는 필드(규격/단위/수량/단가 등)마다 병합 구간의 첫 컬럼(앵커)에만
    폰트/배경/정렬/서식이 지정되고, 나머지 컬럼은 테두리만 다른 빈 칸 서식을
    쓰는 구조다. 앵커는 항상 '품목' 필드의 시작 컬럼(TABLE_START_COL)과 같고,
    빈 칸 서식은 그 다음 컬럼에서 그대로 가져올 수 있다 (품목 필드는 옵션이
    아니라서 폭이 항상 2 이상이라 이 컬럼은 항상 같은 역할을 유지한다).
    """

    def _style_at(col):
        c = ws.cell(row=row, column=col)
        return {
            "font": copy.copy(c.font),
            "fill": copy.copy(c.fill),
            "alignment": copy.copy(c.alignment),
            "number_format": c.number_format,
        }

    return _style_at(TABLE_START_COL), _style_at(TABLE_START_COL + 1)


def _style_field_span(ws, row, start_col, end_col, anchor_style, blank_style):
    """필드의 병합 구간(start_col~end_col)에 테두리/앵커 서식을 다시 적용한다.

    체크박스 조합에 따라 필드마다 컬럼 폭이 달라지므로, 원본 템플릿의 절대
    좌표 서식을 그대로 복사하면 앵커가 다른 열로 밀렸을 때 테두리·배경색·
    가운데 정렬이 깨진다. 그래서 병합 범위가 확정된 뒤 항상 이 함수로 역할
    (앵커/빈 칸) 기준 서식을 새로 그린다.
    """
    for col in range(start_col, end_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.border = Border(
            left=_THIN_SIDE if col == start_col else _NO_SIDE,
            right=_THIN_SIDE if col == end_col else _NO_SIDE,
            top=_THIN_SIDE,
            bottom=_THIN_SIDE,
        )
        style = anchor_style if col == start_col else blank_style
        cell.font = style["font"]
        cell.fill = style["fill"]
        cell.alignment = style["alignment"]
        cell.number_format = style["number_format"]


def _add_item_row_merges(ws, row, layout):
    for start, end, _label in layout.values():
        if end > start:
            ws.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)


def _col_letter(layout, key):
    return get_column_letter(layout[key][0])


def _rebuild_header_row(ws, layout):
    anchor_style, blank_style = _capture_field_styles(ws, ITEM_HEADER_ROW)

    stale_merges = [
        m for m in list(ws.merged_cells.ranges)
        if m.min_row == ITEM_HEADER_ROW and m.max_row == ITEM_HEADER_ROW
        and m.min_col >= TABLE_START_COL and m.max_col <= TABLE_END_COL
    ]
    for m in stale_merges:
        ws.unmerge_cells(str(m))

    for col in range(TABLE_START_COL, TABLE_END_COL + 1):
        ws.cell(row=ITEM_HEADER_ROW, column=col).value = None

    for start, end, label in layout.values():
        if end > start:
            ws.merge_cells(start_row=ITEM_HEADER_ROW, start_column=start,
                            end_row=ITEM_HEADER_ROW, end_column=end)
        ws.cell(row=ITEM_HEADER_ROW, column=start).value = label
        _style_field_span(ws, ITEM_HEADER_ROW, start, end, anchor_style, blank_style)


def _rebuild_item_section(ws, items):
    """품목 표 이하(헤더 행 ~ 하단 각주)를 완전히 새로 그린다.

    반환값: total_row (합계 금액 행 번호)
    """
    # 1) 서식 캡처 (원본 위치 기준)
    style_item = _capture_row_style(ws, REF_ITEM_ROW)
    item_anchor_style, item_blank_style = _capture_field_styles(ws, REF_ITEM_ROW)
    style_blank = _capture_row_style(ws, REF_BLANK_ROW)
    style_total = _capture_row_style(ws, REF_TOTAL_ROW)
    total_anchor_style, total_blank_style = _capture_field_styles(ws, REF_TOTAL_ROW)
    style_gap1 = _capture_row_style(ws, REF_GAP1_ROW)
    style_gap2 = _capture_row_style(ws, REF_GAP2_ROW)
    style_gap3 = _capture_row_style(ws, REF_GAP3_ROW)
    style_footer = _capture_row_style(ws, REF_FOOTER_ROW)

    # 2) 품목 행 ~ 하단 각주 영역의 기존 병합을 모두 해제한 뒤 행 자체를 삭제
    for mc in list(ws.merged_cells.ranges):
        if mc.min_row >= FIRST_ITEM_ROW:
            ws.unmerge_cells(str(mc))
    ws.delete_rows(FIRST_ITEM_ROW, OLD_LAST_ROW - FIRST_ITEM_ROW + 1)

    # 2.5) 활성 필드에 맞춰 헤더 행의 컬럼 폭을 재계산
    flags = _infer_flags(items)
    layout = _compute_column_layout(flags)
    _rebuild_header_row(ws, layout)
    supply_letter = _col_letter(layout, "supply")

    # 3) 필요한 행 수만큼 새로 채워 넣기
    row = FIRST_ITEM_ROW
    for item in items:
        _apply_row_style(ws, row, style_item)
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
            _style_field_span(ws, row, start, end, item_anchor_style, item_blank_style)
        row += 1

    blank_row = row
    _apply_row_style(ws, blank_row, style_blank)
    ws[f"C{blank_row}"] = "이하 여백"
    ws.merge_cells(f"C{blank_row}:V{blank_row}")
    row += 1

    total_row = row
    _apply_row_style(ws, total_row, style_total)
    ws[f"C{total_row}"] = "합계 금액"
    ws[f"{supply_letter}{total_row}"] = f"=SUM({supply_letter}{FIRST_ITEM_ROW}:V{blank_row})"
    supply_start_col = layout["supply"][0]
    label_end_letter = get_column_letter(supply_start_col - 1)
    ws.merge_cells(f"C{total_row}:{label_end_letter}{total_row}")
    ws.merge_cells(f"{supply_letter}{total_row}:V{total_row}")
    _style_field_span(ws, total_row, TABLE_START_COL, supply_start_col - 1,
                       total_anchor_style, total_blank_style)
    _style_field_span(ws, total_row, supply_start_col, TABLE_END_COL,
                       total_anchor_style, total_blank_style)
    row += 1

    gap1_row = row
    _apply_row_style(ws, gap1_row, style_gap1)
    row += 1

    gap2_row = row
    _apply_row_style(ws, gap2_row, style_gap2)
    ws.merge_cells(f"D{gap2_row}:V{gap2_row}")
    row += 1

    gap3_row = row
    _apply_row_style(ws, gap3_row, style_gap3)
    row += 1

    footer_row = row
    _apply_row_style(ws, footer_row, style_footer)
    ws[f"A{footer_row}"] = "[GP-A-001]"
    ws[f"N{footer_row}"] = "주식회사 그린플러스"
    ws.merge_cells(f"A{footer_row}:M{footer_row}")
    ws.merge_cells(f"N{footer_row}:Z{footer_row}")

    ws["S8"] = f"={supply_letter}{total_row}"

    return total_row


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

    ws["D9"] = data.get("company", "")
    ws["Q9"] = data.get("doc_number") or None

    propose_date = _to_excel_date(data.get("propose_date"))
    if propose_date:
        ws["D10"] = propose_date
        ws["D10"].number_format = "yyyy-mm-dd"

    spend_date = _to_excel_date(data.get("spend_date"))
    if spend_date:
        ws["D11"] = spend_date
        ws["D11"].number_format = "yyyy-mm-dd"

    ws["Q10"] = data.get("department", "그린연구소")
    ws["Q11"] = data.get("requester", "")
    ws["D12"] = data.get("title", "")
    ws["B14"] = data.get("detail", "")

    agency = data.get("agency", "")
    org = data.get("org", "")
    project_name = data.get("project_name", "")
    ws["B16"] = f"중앙행정기관 : {agency}" if agency else ""
    ws["B17"] = f"전문기관 : {org}" if org else ""
    ws["B18"] = f"과제명 : {project_name}" if project_name else ""
    ws["B20"] = data.get("execution_note", "")

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
