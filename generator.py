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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

ITEM_COL_MERGES = [
    ("C", "F"),  # 품목
    ("G", "I"),  # 규격
    ("J", "K"),  # 단위
    ("L", "M"),  # 수량
    ("N", "P"),  # 단가
    ("Q", "S"),  # 공급가
    ("T", "V"),  # 부가세
]


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


def _add_item_row_merges(ws, row):
    for start_col, end_col in ITEM_COL_MERGES:
        ws.merge_cells(f"{start_col}{row}:{end_col}{row}")


def _rebuild_item_section(ws, items):
    """품목 표 이하(품목 행들 ~ 하단 각주)를 완전히 새로 그린다.

    반환값: total_row (합계 금액 행 번호)
    """
    # 1) 서식 캡처 (원본 위치 기준)
    style_item = _capture_row_style(ws, REF_ITEM_ROW)
    style_blank = _capture_row_style(ws, REF_BLANK_ROW)
    style_total = _capture_row_style(ws, REF_TOTAL_ROW)
    style_gap1 = _capture_row_style(ws, REF_GAP1_ROW)
    style_gap2 = _capture_row_style(ws, REF_GAP2_ROW)
    style_gap3 = _capture_row_style(ws, REF_GAP3_ROW)
    style_footer = _capture_row_style(ws, REF_FOOTER_ROW)

    # 2) 품목 행 ~ 하단 각주 영역의 기존 병합을 모두 해제한 뒤 행 자체를 삭제
    for mc in list(ws.merged_cells.ranges):
        if mc.min_row >= FIRST_ITEM_ROW:
            ws.unmerge_cells(str(mc))
    ws.delete_rows(FIRST_ITEM_ROW, OLD_LAST_ROW - FIRST_ITEM_ROW + 1)

    # 3) 필요한 행 수만큼 새로 채워 넣기
    row = FIRST_ITEM_ROW
    for item in items:
        _apply_row_style(ws, row, style_item)
        ws[f"C{row}"] = item["name"]
        if item.get("spec"):
            ws[f"G{row}"] = item["spec"]
        if item.get("unit"):
            ws[f"J{row}"] = item["unit"]

        use_qty = item.get("qty") is not None
        use_price = item.get("price") is not None
        if use_qty:
            ws[f"L{row}"] = item["qty"]
        if use_price:
            ws[f"N{row}"] = item["price"]
            ws[f"Q{row}"] = f"=L{row}*N{row}" if use_qty else f"=N{row}"
        else:
            ws[f"Q{row}"] = item.get("supply", 0)
        ws[f"T{row}"] = f"=Q{row}/10"
        _add_item_row_merges(ws, row)
        row += 1

    blank_row = row
    _apply_row_style(ws, blank_row, style_blank)
    ws[f"C{blank_row}"] = "이하 여백"
    ws.merge_cells(f"C{blank_row}:V{blank_row}")
    row += 1

    total_row = row
    _apply_row_style(ws, total_row, style_total)
    ws[f"C{total_row}"] = "합계 금액"
    ws[f"Q{total_row}"] = f"=SUM(Q{FIRST_ITEM_ROW}:V{blank_row})"
    ws.merge_cells(f"C{total_row}:P{total_row}")
    ws.merge_cells(f"Q{total_row}:V{total_row}")
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

    ws["S8"] = f"=Q{total_row}"

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
