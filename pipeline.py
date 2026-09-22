"""견적서 1건 -> 지출결의서 + 검수확인서 생성, PDF 변환, 파일 정리 매니페스트 작성.

이 모듈은 파일을 '로컬 출력 폴더(out_dir)'에 만들고, 각 파일이 사용자 기기의 어느
폴더로 가야 하는지(target_folder)를 매니페스트로 돌려준다. 실제 기기 폴더 쓰기/
차수 감지에 필요한 '형제 폴더 목록'은 호출자가 넣어준다(모듈은 기기에 접근하지 않음).
"""

import datetime
import os
import shutil

import combined_pdf
import folder_router
import history_store
import inspection_generator
import pdf_convert
import quote_reader
from generator import build_expense_report

# 표준 문구
DEFAULT_EXECUTION_NOTE = "연구재료비 집행의 건 (연구개발계획서 상 계상되어 있는 건임)"
DEFAULT_DETAIL = "해당 연구개발 과제 수행을 위한 자재를 구매 하오니 결재 승인 요청드립니다."


def project_for_category(category):
    """카테고리에 해당하는 (중앙행정기관, 전문기관, 과제명) 프리셋을 찾는다.

    사용자가 index.html/배치 화면에서 직접 추가·수정한 과제(history_store에 저장된
    실제 목록)를 우선 보고, 없으면 내장 기본값으로 재시도한다.
    """
    label_target = folder_router.folder_for_category(category)
    projects = history_store.load_projects()
    # 사용자가 지정한 축약명(effective_label)으로 매칭
    for p in projects:
        lbl = history_store.effective_label(p)
        if lbl in (category, "중동(IR)" if category in ("중동", "IR") else category):
            return p
    # 카테고리 키워드가 과제명에 들어 있는지로 재시도
    key = {"고효율 광원": "고효율", "IR": "중동", "수확후": "수확", "자동화": "인건비"}.get(label_target, category)
    for p in projects:
        if key and key in p["project_name"]:
            return p
    return {"agency": "", "org": "", "project_name": ""}


def _lead_item_name(items):
    if not items:
        return "자재"
    name = items[0].get("name", "자재")
    return name


def _total_supply(items):
    total = 0
    for it in items:
        total += inspection_generator.item_supply_amount(it)
    return total


def process_quote(
    quote_path,
    category,
    company,
    *,
    out_dir,
    sibling_folders=None,
    inspector="",
    inspect_date=None,
    propose_date=None,
    spend_date=None,
    requester="",
    doc_number="",
    title=None,
    detail=None,
    execution_note=None,
    address="",
    industry="",
    etc="",
    attachments=None,
    product=None,
    make_pdf=True,
    make_combined_pdf=True,
):
    """전체 파이프라인 실행. 반환: manifest dict."""
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(quote_path)[1]
    quote = quote_reader.read_quote(path=quote_path, ext=ext)
    items = quote["items"]
    warnings = list(quote["warnings"])
    if not items:
        warnings.append("견적서에서 품목을 인식하지 못했습니다 - 품목을 직접 확인/입력해야 합니다.")

    # 업체명: 사용자 지정 우선, 없으면 자동 인식
    company = (company or quote.get("company") or "").strip()

    # 과제 프리셋
    proj = project_for_category(category)
    today = datetime.date.today()
    propose_date = propose_date or today.strftime("%Y-%m-%d")

    lead = _lead_item_name(items)
    cat_label = category.strip()
    title = title or f"{cat_label}과제 {lead} 구매의 건."
    detail = detail if detail is not None else DEFAULT_DETAIL
    execution_note = execution_note if execution_note is not None else DEFAULT_EXECUTION_NOTE

    # 1) 지출결의서
    expense_data = {
        "company": company, "doc_number": doc_number,
        "propose_date": propose_date, "spend_date": spend_date or "",
        "department": "그린연구소", "requester": requester,
        "title": title, "detail": detail,
        "agency": proj["agency"], "org": proj["org"],
        "project_name": proj["project_name"], "execution_note": execution_note,
        "items": items,
    }
    expense_buf = build_expense_report(expense_data)
    company_clean = (company or "업체명미상").replace(" ", "")
    datestr = propose_date.replace("-", "")
    expense_xlsx = os.path.join(out_dir, f"지출결의서_{company_clean}_{cat_label}.xlsx")
    with open(expense_xlsx, "wb") as f:
        f.write(expense_buf.getvalue())

    # 2) 검수확인서
    inspection_data = {
        "company": company, "address": address, "industry": industry, "etc": etc,
        "items": items, "inspector": inspector,
        "inspect_date": inspect_date or spend_date or propose_date,
        "department": "그린연구소",
    }
    insp_buf = inspection_generator.build_inspection_report(inspection_data)
    insp_xlsx = os.path.join(out_dir, f"검수확인서_{company_clean}_{cat_label}.xlsx")
    with open(insp_xlsx, "wb") as f:
        f.write(insp_buf.getvalue())

    generated = [expense_xlsx, insp_xlsx]

    # 3) PDF 변환
    expense_pdf = None
    insp_pdf = None
    pdf_error = None
    if make_pdf and pdf_convert.available():
        try:
            expense_pdf = pdf_convert.xlsx_to_pdf(expense_xlsx, out_dir=out_dir)
        except Exception as e:
            pdf_error = str(e)
        try:
            insp_pdf = pdf_convert.xlsx_to_pdf(insp_xlsx, out_dir=out_dir)
        except Exception as e:
            pdf_error = str(e)
    elif make_pdf:
        pdf_error = "LibreOffice 미설치로 PDF 변환을 건너뜀"
    pdfs = [p for p in (expense_pdf, insp_pdf) if p]

    # 4) 첨부문서(견적서/사업자등록증/통장사본/전자세금계산서/거래명세서) 복사
    attachments = attachments or {}
    copied = {}
    # 견적서 원본도 폴더로 함께 정리
    quote_dest = os.path.join(out_dir, f"견적서_{company_clean}{ext}")
    shutil.copy2(quote_path, quote_dest)
    copied["견적서"] = quote_dest
    for label, src in attachments.items():
        if src and os.path.isfile(src):
            dest = os.path.join(out_dir, f"{label}_{company_clean}{os.path.splitext(src)[1]}")
            shutil.copy2(src, dest)
            copied[label] = dest

    # 5) 대상 폴더 결정
    sibling_folders = sibling_folders or []
    folder_name, is_new, pattern = folder_router.propose_company_folder(
        sibling_folders, company, product=product, today=today)

    docs_done = ["견적서", "지출결의서", "검수확인서"] + [k for k in copied if k != "견적서"]

    # 6) 통합 출력용 병합 PDF (견적서 -> 지출결의서 -> 사업자등록증 -> 통장사본, 검수확인서 제외)
    # 제공되지 않은 첨부(None)는 애초에 시도하지 않은 것이므로 skipped에 넣지 않는다.
    if make_combined_pdf:
        combined_inputs = [p for p in (
            quote_dest,
            expense_pdf or expense_xlsx,
            copied.get("사업자등록증"),
            copied.get("통장사본"),
        ) if p]
        combined_result = combined_pdf.build_combined_pdf(
            combined_inputs,
            os.path.join(out_dir, f"통합출력_{company_clean}_{cat_label}.pdf"),
        )
    else:
        combined_result = {"path": None, "skipped": []}

    return {
        "company": company,
        "category": category,
        "category_folder": folder_router.folder_for_category(category),
        "target_folder_name": folder_name,
        "target_folder_is_new": is_new,
        "naming_pattern": pattern,
        "items": items,
        "item_count": len(items),
        "total_supply": _total_supply(items),
        "project": proj,
        "generated_xlsx": generated,
        "generated_pdf": pdfs,
        "pdf_error": pdf_error,
        "attachments_copied": copied,
        "docs_done": docs_done,
        "combined_pdf": combined_result["path"],
        "combined_pdf_skipped": combined_result["skipped"],
        "warnings": warnings,
        "quote_source": quote["source"],
        "title": title,
    }
