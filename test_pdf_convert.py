import os
import shutil
import tempfile

import openpyxl

import pdf_convert


def test_xlsx_to_pdf_converts_without_hanging():
    if not pdf_convert.available():
        print("SKIP: LibreOffice(soffice)가 설치돼 있지 않음")
        return
    tmp_dir = tempfile.mkdtemp()
    try:
        xlsx_path = os.path.join(tmp_dir, "test.xlsx")
        wb = openpyxl.Workbook()
        wb.active.append(["a", "b"])
        wb.save(xlsx_path)

        pdf_path = pdf_convert.xlsx_to_pdf(xlsx_path, out_dir=tmp_dir, timeout=30)

        assert os.path.isfile(pdf_path)
        print("OK: test_xlsx_to_pdf_converts_without_hanging")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_xlsx_to_pdf_converts_without_hanging()
    print("ALL PASSED")
