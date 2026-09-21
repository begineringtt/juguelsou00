"""setting_03 전체를 스캔해, 각 과제·업체 폴더에 실제로 어떤 문서가 있는지 파악하고
그 '진짜 현황'을 체크리스트에 반영한다(무엇이 됐고 무엇이 빠졌는지 = 현황판).

- scan_status(setting03_root): 모든 과제/업체 폴더의 보유 문서 집합을 수집.
- sync_to_checklist(...): 체크리스트 사본에 실제 보유 문서만 O 로 표시(없으면 빈칸).
- missing_report(...): 과제·업체별로 빠진 필수 문서를 정리.

체크리스트의 카테고리 행-블록과 업체 열은 checklist_updater 의 로직을 재사용한다.
"""

import os

import openpyxl
from openpyxl.utils import get_column_letter

import checklist_updater as CU
from attachment_finder import classify, clean_company

# 카테고리 폴더명 -> 체크리스트 카테고리 표기 (수확후->수화후 오타 포함)
FOLDER_TO_CHECKLIST_CAT = {
    "고온성": "고온성", "고효율 광원": "고효율", "근권부": "근권부", "북미": "북미",
    "수확후": "수화후", "자동화": "자동화", "저온성": "저온성", "팁스": "팁스", "IR": "중동",
}

# "완성"으로 보는 문서(검수확인서까지). 세트 완성도 판정 기준.
REQUIRED_DOCS = ["견적서", "사업자등록증", "통장사본", "지출결의서", "검수확인서"]
OPTIONAL_DOCS = ["전자세금계산서", "거래명세서"]


def scan_status(setting03_root, categories=None):
    """반환: [ {category_folder, checklist_cat, company_folder, company, docs:set}, ... ]"""
    out = []
    cats = categories or list(FOLDER_TO_CHECKLIST_CAT.keys())
    for cat in cats:
        cat_path = os.path.join(setting03_root, cat)
        if not os.path.isdir(cat_path):
            continue
        for comp_folder in os.listdir(cat_path):
            comp_path = os.path.join(cat_path, comp_folder)
            if not os.path.isdir(comp_path):
                continue
            docs = set()
            for root, _d, files in os.walk(comp_path):
                for fn in files:
                    if fn.startswith("~$"):
                        continue
                    d = classify(fn)
                    if d:
                        docs.add(d)
            out.append({
                "category_folder": cat,
                "checklist_cat": FOLDER_TO_CHECKLIST_CAT.get(cat, cat),
                "company_folder": comp_folder,
                "company": clean_company(comp_folder),
                "docs": docs,
            })
    return out


def missing_report(statuses):
    """과제·업체별 누락 문서 목록. 반환: [ {category_folder, company, missing_required, missing_optional} ]"""
    rows = []
    for s in statuses:
        miss_req = [d for d in REQUIRED_DOCS if d not in s["docs"]]
        miss_opt = [d for d in OPTIONAL_DOCS if d not in s["docs"]]
        rows.append({
            "category_folder": s["category_folder"],
            "company": s["company"],
            "company_folder": s["company_folder"],
            "have": sorted(s["docs"]),
            "missing_required": miss_req,
            "missing_optional": miss_opt,
            "complete": not miss_req,
        })
    return rows


def sync_to_checklist(src_path, statuses, out_path=None, include_payment_sheets=False,
                      mark_optional=True):
    """체크리스트 사본에 실제 보유 문서를 O 로 반영한다(없으면 그대로 빈칸).

    반환: {out_path, marked_count, matched, unmatched}
      matched   : (category, company) 중 체크리스트에서 찾아 표시한 것
      unmatched : 체크리스트에서 열/블록을 못 찾은 것(신규 업체 등)
    """
    wb = openpyxl.load_workbook(src_path)
    doc_set = REQUIRED_DOCS + (OPTIONAL_DOCS if mark_optional else [])

    # 시트별 (업체열, 카테고리블록) 인덱스 미리 구축
    sheet_info = []
    for ws in wb.worksheets:
        if not include_payment_sheets and ws.title.startswith("결제"):
            continue
        cols, _hr = CU._company_columns(ws)
        cats = CU._category_rows(ws)
        sheet_info.append((ws, cols, cats))

    marked_count = 0
    matched, unmatched = [], []
    for s in statuses:
        cat_label = s["checklist_cat"]
        present = [d for d in doc_set if d in s["docs"]]
        if not present:
            continue
        hit_any = False
        for ws, cols, cats in sheet_info:
            if cat_label not in cats:
                continue
            col = CU._match_company_column(cols, s["company"])
            if col is None:
                continue
            hit_any = True
            base = cats[cat_label]
            for d in present:
                off = CU.DOC_OFFSETS.get(d)
                if off is None:
                    continue
                ws.cell(row=base + off, column=col).value = CU.MARK
                marked_count += 1
        (matched if hit_any else unmatched).append(f"{s['category_folder']}/{s['company']}")

    if out_path is None:
        import datetime
        stamp = datetime.date.today().strftime("%y%m%d")
        out_path = os.path.join(os.path.dirname(src_path),
                                f"연구비 파일 업로드 체크용_현황반영_{stamp}.xlsx")
    wb.save(out_path)
    return {"out_path": out_path, "marked_count": marked_count,
            "matched": matched, "unmatched": unmatched}
