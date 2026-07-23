import glob
import os

import openpyxl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
READ_DIR = os.path.join(BASE_DIR, "..", "read")

HISTORY_LABEL_FIELDS = ["company", "requester", "title", "detail", "execution_note"]

MAX_SCAN_ROW = 30
MAX_SCAN_COL = 20


def scan_read_folder(folder=None):
    folder = folder or READ_DIR
    result = {"history": {field: [] for field in HISTORY_LABEL_FIELDS}, "projects": []}
    seen_history = {field: set() for field in HISTORY_LABEL_FIELDS}
    seen_projects = set()

    for path in sorted(glob.glob(os.path.join(folder, "*.xlsx"))):
        if os.path.basename(path).startswith("~$"):
            continue
        try:
            wb = openpyxl.load_workbook(path, data_only=True)
        except Exception:
            continue
        for ws in wb.worksheets:
            try:
                _scan_sheet(ws, result, seen_history, seen_projects)
            except Exception:
                continue

    return result


def _cell_text(ws, row, col):
    value = ws.cell(row=row, column=col).value
    if value is None:
        return ""
    return str(value).strip()


def _first_value_after(ws, row, start_col):
    for col in range(start_col + 1, MAX_SCAN_COL + 10):
        text = _cell_text(ws, row, col)
        if text:
            return text
    return ""


def _find_label_cell(ws, label):
    for row in range(1, MAX_SCAN_ROW + 1):
        for col in range(1, MAX_SCAN_COL + 1):
            if _cell_text(ws, row, col) == label:
                return row, col
    return None, None


def _add_history(result, seen_history, field, value):
    value = (value or "").strip()
    if value and value not in seen_history[field]:
        seen_history[field].add(value)
        result["history"][field].append(value)


def _scan_detail(ws, result, seen_history, detail_row):
    stop_prefixes = ("중앙행정기관", "전문기관", "과제명")
    for row in range(detail_row, detail_row + 4):
        for col in range(1, MAX_SCAN_COL):
            text = _cell_text(ws, row, col)
            if not text or text == "상세내용":
                continue
            if text.startswith(stop_prefixes):
                return
            _add_history(result, seen_history, "detail", text)
            return


def _scan_project_and_execution(ws, result, seen_history, seen_projects):
    agency = org = project_name = ""
    for row in range(1, MAX_SCAN_ROW):
        for col in range(1, MAX_SCAN_COL):
            text = _cell_text(ws, row, col)
            if not text:
                continue
            if "연구재료비 집행" in text or "집행의 건" in text:
                _add_history(result, seen_history, "execution_note", text)
            if ":" not in text:
                continue
            label_part, _, value_part = text.partition(":")
            label_part = label_part.strip()
            value_part = value_part.strip()
            if label_part == "중앙행정기관" and value_part:
                agency = value_part
            elif label_part == "전문기관" and value_part:
                org = value_part
            elif label_part == "과제명" and value_part:
                project_name = value_part

    if project_name:
        key = (agency, org, project_name)
        if key not in seen_projects:
            seen_projects.add(key)
            result["projects"].append({"agency": agency, "org": org, "project_name": project_name})


def _scan_sheet(ws, result, seen_history, seen_projects):
    row, col = _find_label_cell(ws, "업체명")
    if row:
        _add_history(result, seen_history, "company", _first_value_after(ws, row, col))

    row, col = _find_label_cell(ws, "청 구 인")
    if row:
        _add_history(result, seen_history, "requester", _first_value_after(ws, row, col))

    title_row, title_col = _find_label_cell(ws, "내  용")
    detail_row, _ = _find_label_cell(ws, "상세내용")
    if title_row and (not detail_row or title_row < detail_row):
        _add_history(result, seen_history, "title", _first_value_after(ws, title_row, title_col))

    if detail_row:
        _scan_detail(ws, result, seen_history, detail_row)

    _scan_project_and_execution(ws, result, seen_history, seen_projects)
