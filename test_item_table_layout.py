import openpyxl
from openpyxl.utils import get_column_letter

from generator import ITEM_HEADER_ROW, TABLE_START_COL, TABLE_END_COL, FIRST_ITEM_ROW, _compute_column_layout
from generator import build_expense_report

BASE_DATA = {
    "company": "주식회사 테스트",
    "propose_date": "2026-07-22",
    "spend_date": "2026-07-22",
    "department": "그린연구소",
    "requester": "홍길동 연구원",
    "title": "테스트 구매의 건",
    "detail": "테스트 상세내용입니다.",
    "agency": "농림축산식품부",
    "org": "농림식품기술기획평가원",
    "project_name": "테스트 과제명",
    "execution_note": "연구재료비 집행의 건",
}


def _header_merges(ws):
    return sorted(
        (m.min_col, m.max_col)
        for m in ws.merged_cells.ranges
        if m.min_row == ITEM_HEADER_ROW and m.max_row == ITEM_HEADER_ROW
        and m.min_col >= TABLE_START_COL and m.max_col <= TABLE_END_COL
    )


def _header_labels(ws):
    labels = {}
    for col in range(TABLE_START_COL, TABLE_END_COL + 1):
        v = ws.cell(row=ITEM_HEADER_ROW, column=col).value
        if v:
            labels[get_column_letter(col)] = v
    return labels


def test_all_columns_regression():
    data = dict(BASE_DATA)
    data["items"] = [{"name": "품목1", "spec": "규격1", "unit": "EA", "qty": 2, "price": 1000}]
    buf = build_expense_report(data)
    wb = openpyxl.load_workbook(buf)
    ws = wb.worksheets[0]

    assert _header_labels(ws) == {
        "B": "품목", "H": "규격", "L": "단위", "O": "수량", "R": "단가", "V": "공급가", "Z": "부가세",
    }
    assert _header_merges(ws) == sorted([(2, 7), (8, 11), (12, 14), (15, 17), (18, 21), (22, 25), (26, 29)])
    print("OK: test_all_columns_regression")


def test_spec_dropped_compacts_header():
    data = dict(BASE_DATA)
    data["items"] = [{"name": "품목1", "unit": "EA", "qty": 2, "price": 1000}]
    buf = build_expense_report(data)
    wb = openpyxl.load_workbook(buf)
    ws = wb.worksheets[0]

    labels = _header_labels(ws)
    assert "규격" not in labels.values()
    assert set(labels.values()) == {"품목", "단위", "수량", "단가", "공급가", "부가세"}

    merges = _header_merges(ws)
    assert merges[0][0] == 2
    assert merges[-1][1] == 29
    total_span = sum(end - start + 1 for start, end in merges)
    assert total_span == 28
    print("OK: test_spec_dropped_compacts_header")


def test_total_row_boundary_matches_supply_start():
    data = dict(BASE_DATA)
    data["items"] = [{"name": "품목1", "unit": "EA", "qty": 2, "price": 1000}]
    flags = {"use_spec": False, "use_unit": True, "use_qty": True, "use_price": True}
    layout = _compute_column_layout(flags)
    supply_start = layout["supply"][0]

    buf = build_expense_report(data)
    wb = openpyxl.load_workbook(buf)
    ws = wb.worksheets[0]

    total_row = None
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == "합계 금액":
                total_row = cell.row
                break
        if total_row:
            break
    assert total_row is not None

    row_merges = [
        (m.min_col, m.max_col) for m in ws.merged_cells.ranges
        if m.min_row == total_row and m.max_row == total_row
    ]
    label_merge = next(mc for mc in row_merges if mc[0] == TABLE_START_COL)
    amount_merge = next(mc for mc in row_merges if mc[0] == supply_start)
    assert label_merge[1] == supply_start - 1
    assert amount_merge[1] == TABLE_END_COL
    print("OK: test_total_row_boundary_matches_supply_start")


def test_supply_direct_entry_when_price_off():
    data = dict(BASE_DATA)
    data["items"] = [{"name": "품목1", "spec": "규격1", "unit": "EA", "supply": 12345}]
    buf = build_expense_report(data)
    wb = openpyxl.load_workbook(buf)
    ws = wb.worksheets[0]
    layout = _compute_column_layout({"use_spec": True, "use_unit": True, "use_qty": False, "use_price": False})
    supply_letter = get_column_letter(layout["supply"][0])
    assert ws[f"{supply_letter}{FIRST_ITEM_ROW}"].value == 12345
    print("OK: test_supply_direct_entry_when_price_off")


def test_qty_price_supply_cells_populated():
    data = dict(BASE_DATA)
    data["items"] = [{"name": "품목1", "spec": "규격1", "unit": "EA", "qty": 2, "price": 1000}]
    buf = build_expense_report(data)
    wb = openpyxl.load_workbook(buf)
    ws = wb.worksheets[0]

    layout = _compute_column_layout({"use_spec": True, "use_unit": True, "use_qty": True, "use_price": True})
    qty_letter = get_column_letter(layout["qty"][0])
    price_letter = get_column_letter(layout["price"][0])
    supply_letter = get_column_letter(layout["supply"][0])

    assert ws[f"{qty_letter}{FIRST_ITEM_ROW}"].value == 2
    assert ws[f"{price_letter}{FIRST_ITEM_ROW}"].value == 1000
    assert ws[f"{supply_letter}{FIRST_ITEM_ROW}"].value == f"={qty_letter}{FIRST_ITEM_ROW}*{price_letter}{FIRST_ITEM_ROW}"
    print("OK: test_qty_price_supply_cells_populated")


def test_too_many_items_raises():
    data = dict(BASE_DATA)
    data["items"] = [{"name": f"품목{i+1}", "unit": "EA", "qty": 1, "price": 100} for i in range(10)]
    try:
        build_expense_report(data)
    except ValueError:
        print("OK: test_too_many_items_raises")
        return
    raise AssertionError("expected ValueError for too many items")


if __name__ == "__main__":
    test_all_columns_regression()
    test_spec_dropped_compacts_header()
    test_total_row_boundary_matches_supply_start()
    test_supply_direct_entry_when_price_off()
    test_qty_price_supply_cells_populated()
    test_too_many_items_raises()
    print("ALL PASSED")
