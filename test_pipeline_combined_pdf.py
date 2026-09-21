import os
import shutil
import tempfile

import fitz
import openpyxl
from PIL import Image

import pdf_convert
import pipeline


def _make_quote_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["품명", "수량", "단가"])
    ws.append(["테스트자재", 2, 1000])
    wb.save(path)


def _make_image(path):
    Image.new("RGB", (200, 100), color="white").save(path)


def test_process_quote_builds_combined_pdf_with_available_docs():
    tmp_dir = tempfile.mkdtemp()
    try:
        quote_path = os.path.join(tmp_dir, "견적서.xlsx")
        biz_path = os.path.join(tmp_dir, "사업자등록증.jpg")
        bank_path = os.path.join(tmp_dir, "통장사본.jpg")
        _make_quote_xlsx(quote_path)
        _make_image(biz_path)
        _make_image(bank_path)

        out_dir = os.path.join(tmp_dir, "out")
        manifest = pipeline.process_quote(
            quote_path, "고온성", "테스트업체",
            out_dir=out_dir,
            attachments={"사업자등록증": biz_path, "통장사본": bank_path},
        )

        assert manifest["combined_pdf"], "이미지 첨부만으로도 병합 PDF는 생성돼야 한다"
        merged = fitz.open(manifest["combined_pdf"])
        try:
            if pdf_convert.available():
                # 견적서(xlsx) + 지출결의서(pdf) + 사업자등록증 + 통장사본
                assert merged.page_count == 4
                assert manifest["combined_pdf_skipped"] == []
            else:
                # 견적서/지출결의서는 LibreOffice 없이 변환 불가 -> 건너뜀, 이미지 2장만 병합
                assert merged.page_count == 2
                assert len(manifest["combined_pdf_skipped"]) == 2
                reasons = " ".join(r for _, r in manifest["combined_pdf_skipped"])
                assert "LibreOffice" in reasons
        finally:
            merged.close()
        print("OK: test_process_quote_builds_combined_pdf_with_available_docs")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_process_quote_combined_pdf_is_none_without_any_mergeable_file():
    tmp_dir = tempfile.mkdtemp()
    try:
        quote_path = os.path.join(tmp_dir, "견적서.xlsx")
        _make_quote_xlsx(quote_path)
        out_dir = os.path.join(tmp_dir, "out")

        manifest = pipeline.process_quote(
            quote_path, "고온성", "테스트업체", out_dir=out_dir,
        )

        if pdf_convert.available():
            assert manifest["combined_pdf"]
        else:
            assert manifest["combined_pdf"] is None
            assert len(manifest["combined_pdf_skipped"]) == 2
        print("OK: test_process_quote_combined_pdf_is_none_without_any_mergeable_file")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_process_quote_skips_combined_pdf_when_disabled():
    tmp_dir = tempfile.mkdtemp()
    try:
        quote_path = os.path.join(tmp_dir, "견적서.xlsx")
        biz_path = os.path.join(tmp_dir, "사업자등록증.jpg")
        bank_path = os.path.join(tmp_dir, "통장사본.jpg")
        _make_quote_xlsx(quote_path)
        _make_image(biz_path)
        _make_image(bank_path)
        out_dir = os.path.join(tmp_dir, "out")

        manifest = pipeline.process_quote(
            quote_path, "고온성", "테스트업체",
            out_dir=out_dir,
            attachments={"사업자등록증": biz_path, "통장사본": bank_path},
            make_combined_pdf=False,
        )

        assert manifest["combined_pdf"] is None
        assert manifest["combined_pdf_skipped"] == []
        print("OK: test_process_quote_skips_combined_pdf_when_disabled")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_process_quote_builds_combined_pdf_with_available_docs()
    test_process_quote_combined_pdf_is_none_without_any_mergeable_file()
    test_process_quote_skips_combined_pdf_when_disabled()
    print("ALL PASSED")
