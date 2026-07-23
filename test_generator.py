import io
import openpyxl
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


def make_items(n):
    return [
        {"name": f"품목{i+1}", "spec": f"규격{i+1}", "unit": "EA", "qty": i + 1, "price": 1000 * (i + 1)}
        for i in range(n)
    ]


def inspect(n):
    data = dict(BASE_DATA)
    data["items"] = make_items(n)
    buf = build_expense_report(data)
    wb = openpyxl.load_workbook(buf)
    ws = wb.worksheets[0]
    print(f"\n===== n={n} items =====")
    print("dims:", ws.dimensions)
    print("merges around item area:")
    for mc in sorted(ws.merged_cells.ranges, key=lambda m: (m.min_row, m.min_col)):
        if 22 <= mc.min_row <= 33:
            print(" ", mc)
    print("formulas:")
    for r in range(23, 33):
        vals = []
        for col in ["C", "G", "J", "L", "N", "Q", "T"]:
            v = ws[f"{col}{r}"].value
            if v is not None:
                vals.append(f"{col}{r}={v!r}")
        if vals:
            print(" ", " | ".join(vals))
    print("S8:", ws["S8"].value, "D8:", ws["D8"].value)
    for coord in ["A31", "N31"]:
        pass
    # find footer text wherever it landed
    for row in ws.iter_rows():
        for cell in row:
            if cell.value == "[GP-A-001]" or cell.value == "주식회사 그린플러스":
                print("footer:", cell.coordinate, cell.value)


for n in [1, 2, 3, 5]:
    inspect(n)
