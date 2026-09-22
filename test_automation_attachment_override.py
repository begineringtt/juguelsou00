import os
import shutil
import tempfile

import openpyxl

import automation


def _make_quote_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["품명", "수량", "단가"])
    ws.append(["테스트자재", 2, 1000])
    wb.save(path)


def test_attachment_company_override_is_used_for_repo_lookup_instead_of_company():
    # 견적서에서 인식된 업체명("대한")이 색인 폴더명("대한중공업")과 정확히
    # 일치하지 않아도(부분 포함일 뿐), 사용자가 확인 화면에서 후보를 확정하면
    # 그 확정된 이름으로 첨부를 찾아야 한다.
    tmp_dir = tempfile.mkdtemp()
    try:
        setting03_root = os.path.join(tmp_dir, "setting_03")
        repo_dir = os.path.join(setting03_root, "고온성", "대한중공업")
        os.makedirs(repo_dir)
        open(os.path.join(repo_dir, "통장사본.jpg"), "w").close()

        quote_path = os.path.join(tmp_dir, "견적서.xlsx")
        _make_quote_xlsx(quote_path)

        manifest = automation.run(
            quote_path, "고온성", "대한", setting03_root,
            attachment_company_override="대한중공업",
            update_checklist=False, write_report=False, place=False,
        )

        assert manifest["attachments_from_repo"].get("통장사본")
        print("OK: test_attachment_company_override_is_used_for_repo_lookup_instead_of_company")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_without_override_a_non_exact_company_name_does_not_auto_attach():
    tmp_dir = tempfile.mkdtemp()
    try:
        setting03_root = os.path.join(tmp_dir, "setting_03")
        repo_dir = os.path.join(setting03_root, "고온성", "대한중공업")
        os.makedirs(repo_dir)
        open(os.path.join(repo_dir, "통장사본.jpg"), "w").close()

        quote_path = os.path.join(tmp_dir, "견적서.xlsx")
        _make_quote_xlsx(quote_path)

        manifest = automation.run(
            quote_path, "고온성", "대한", setting03_root,
            update_checklist=False, write_report=False, place=False,
        )

        assert not manifest["attachments_from_repo"]
        print("OK: test_without_override_a_non_exact_company_name_does_not_auto_attach")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_attachment_company_override_is_used_for_repo_lookup_instead_of_company()
    test_without_override_a_non_exact_company_name_does_not_auto_attach()
    print("ALL PASSED")
