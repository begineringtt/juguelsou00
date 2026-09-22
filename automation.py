"""상위 오케스트레이션: 견적서 1건 -> 문서 생성 + PDF + setting_03 폴더 배치 +
체크리스트 갱신 + 처리이력 보고서까지 한 번에.

로컬 PC(앱 실행 환경)에서 setting_03 에 직접 파일을 쓰는 것을 전제로 한다.
(파일 생성 자체는 pipeline.process_quote 가 임시 out_dir 에 만들고, 여기서
목표 폴더로 이동한다.)
"""

import os
import shutil
import tempfile

import attachment_finder
import checklist_updater
import folder_router
import pipeline
import report_writer

CHECKLIST_DIRNAME = "체크리스트"


def _list_siblings(category_root):
    if not os.path.isdir(category_root):
        return []
    return [n for n in os.listdir(category_root)
            if os.path.isdir(os.path.join(category_root, n))]


def _safe_move(src, dst_dir):
    """dst_dir 로 이동. 같은 이름이 있으면 덮어쓰지 않고 (n) 붙여 보존."""
    os.makedirs(dst_dir, exist_ok=True)
    base = os.path.basename(src)
    dst = os.path.join(dst_dir, base)
    if os.path.exists(dst):
        stem, ext = os.path.splitext(base)
        n = 2
        while os.path.exists(os.path.join(dst_dir, f"{stem} ({n}){ext}")):
            n += 1
        dst = os.path.join(dst_dir, f"{stem} ({n}){ext}")
    shutil.move(src, dst)
    return dst


def run(quote_path, category, company, setting03_root, *,
        inspector="", inspect_date=None, requester="",
        attachments=None, product=None, place=True, update_checklist=True,
        write_report=True, extra_docs_done=None,
        auto_find_attachments=True, find_doc_types=("통장사본", "사업자등록증"),
        attachment_company_override=None,
        **pipeline_opts):
    """전체 자동화 1건 실행.

    place=False 이면 파일을 목표 폴더로 옮기지 않고 임시 폴더 경로만 매니페스트에 담아
    반환한다(미리보기/드라이런 용).

    auto_find_attachments=True 이면, 직접 넘기지 않은 통장사본·사업자등록증을
    setting_03 기존 폴더("서버")에서 업체명으로 찾아 자동 복사한다 - 단, 정확히
    일치하는 업체일 때만이다.

    attachment_company_override: 배치 화면에서 "유사 업체" 후보를 사용자가
    확정했을 때, 그 확정된 업체명. 주어지면 company 대신 이 이름으로 첨부를
    찾는다(company는 문서 내용/폴더명에 그대로 쓰이고, 첨부 조회에만 영향).
    """
    category_root = folder_router.category_root(setting03_root, category)
    siblings = _list_siblings(category_root)

    # 통장사본·사업자등록증을 setting_03 에서 자동 검색 (직접 준 것이 우선)
    attachments = dict(attachments or {})
    found_from_repo = {}
    if auto_find_attachments:
        index = attachment_finder.build_index(setting03_root)
        found, matched_display = attachment_finder.find_documents(
            index, attachment_company_override or company, doc_types=find_doc_types)
        for doc_type, path in found.items():
            if path and doc_type not in attachments:
                attachments[doc_type] = path
                found_from_repo[doc_type] = path

    tmp = tempfile.mkdtemp(prefix="gp_auto_")
    manifest = pipeline.process_quote(
        quote_path, category, company,
        out_dir=tmp, sibling_folders=siblings,
        inspector=inspector, inspect_date=inspect_date, requester=requester,
        attachments=attachments, product=product, **pipeline_opts)

    target_dir = os.path.join(category_root, manifest["target_folder_name"])
    manifest["target_dir"] = target_dir

    combined_pdf_files = [manifest["combined_pdf"]] if manifest.get("combined_pdf") else []
    placed = []
    if place:
        for path in (manifest["generated_xlsx"] + manifest["generated_pdf"]
                     + list(manifest["attachments_copied"].values())
                     + combined_pdf_files):
            if os.path.isfile(path):
                placed.append(_safe_move(path, target_dir))
        manifest["placed_files"] = placed

    # 체크리스트 갱신
    if update_checklist:
        checklist_dir = os.path.join(setting03_root, CHECKLIST_DIRNAME)
        src = _find_checklist(checklist_dir)
        if src:
            docs_done = list(manifest["docs_done"])
            if extra_docs_done:
                docs_done += list(extra_docs_done)
            cres = checklist_updater.update_checklist(src, category, company, docs_done)
            manifest["checklist"] = cres
        else:
            manifest["checklist"] = {"misses": ["체크리스트 원본 파일을 찾지 못했습니다."], "marked": []}

    # 처리이력 보고서
    if write_report:
        report_path = os.path.join(setting03_root, CHECKLIST_DIRNAME, "처리이력_보고서.xlsx")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        report_writer.append_entry(report_path, {
            "category": category, "company": company,
            "folder": f"{manifest['category_folder']} / {manifest['target_folder_name']}",
            "generated": ["지출결의서(xlsx+pdf)", "검수확인서(xlsx+pdf)"],
            "attachments": list(manifest["attachments_copied"].keys()),
            "total_amount": manifest["total_supply"],
            "item_count": manifest["item_count"],
            "source": manifest["quote_source"],
            "note": "; ".join(manifest["warnings"]) if manifest["warnings"] else "",
            "combined_pdf": bool(manifest.get("combined_pdf")),
        })
        manifest["report_path"] = report_path

    manifest["attachments_from_repo"] = found_from_repo
    return manifest


def _find_checklist(checklist_dir):
    """체크리스트 폴더에서 '업로드 체크용' 원본(자동갱신본 제외)을 찾는다."""
    if not os.path.isdir(checklist_dir):
        return None
    cands = [n for n in os.listdir(checklist_dir)
             if n.endswith(".xlsx") and "체크용" in n and "자동갱신" not in n and not n.startswith("~$")]
    if not cands:
        return None
    # 파일명에 최신 날짜가 있으면 그걸 우선
    cands.sort(reverse=True)
    return os.path.join(checklist_dir, cands[0])
