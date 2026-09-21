import os
import shutil
import tempfile

import fitz
from PIL import Image

import combined_pdf


def _make_pdf(path, text):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def _make_image(path):
    Image.new("RGB", (200, 100), color="white").save(path)


def test_merges_two_pdfs_in_order():
    tmp_dir = tempfile.mkdtemp()
    try:
        pdf_a = os.path.join(tmp_dir, "a.pdf")
        pdf_b = os.path.join(tmp_dir, "b.pdf")
        _make_pdf(pdf_a, "FIRST")
        _make_pdf(pdf_b, "SECOND")
        out_path = os.path.join(tmp_dir, "combined.pdf")

        result = combined_pdf.build_combined_pdf([pdf_a, pdf_b], out_path)

        assert result["path"] == out_path
        assert result["skipped"] == []
        merged = fitz.open(out_path)
        try:
            assert merged.page_count == 2
            assert "FIRST" in merged[0].get_text()
            assert "SECOND" in merged[1].get_text()
        finally:
            merged.close()
        print("OK: test_merges_two_pdfs_in_order")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_merges_pdf_and_image():
    tmp_dir = tempfile.mkdtemp()
    try:
        pdf_a = os.path.join(tmp_dir, "a.pdf")
        image_b = os.path.join(tmp_dir, "b.png")
        _make_pdf(pdf_a, "FIRST")
        _make_image(image_b)
        out_path = os.path.join(tmp_dir, "combined.pdf")

        result = combined_pdf.build_combined_pdf([pdf_a, image_b], out_path)

        assert result["path"] == out_path
        assert result["skipped"] == []
        merged = fitz.open(out_path)
        try:
            assert merged.page_count == 2
        finally:
            merged.close()
        print("OK: test_merges_pdf_and_image")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_skips_missing_file_and_continues():
    tmp_dir = tempfile.mkdtemp()
    try:
        pdf_a = os.path.join(tmp_dir, "a.pdf")
        _make_pdf(pdf_a, "FIRST")
        missing = os.path.join(tmp_dir, "missing.jpg")
        out_path = os.path.join(tmp_dir, "combined.pdf")

        result = combined_pdf.build_combined_pdf([pdf_a, missing], out_path)

        assert result["path"] == out_path
        assert len(result["skipped"]) == 1
        assert result["skipped"][0][0] == missing
        merged = fitz.open(out_path)
        try:
            assert merged.page_count == 1
        finally:
            merged.close()
        print("OK: test_skips_missing_file_and_continues")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_returns_none_path_when_nothing_to_merge():
    tmp_dir = tempfile.mkdtemp()
    try:
        missing = os.path.join(tmp_dir, "missing.pdf")
        out_path = os.path.join(tmp_dir, "combined.pdf")

        result = combined_pdf.build_combined_pdf([missing, None], out_path)

        assert result["path"] is None
        assert len(result["skipped"]) == 2
        assert not os.path.isfile(out_path)
        print("OK: test_returns_none_path_when_nothing_to_merge")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_merges_two_pdfs_in_order()
    test_merges_pdf_and_image()
    test_skips_missing_file_and_continues()
    test_returns_none_path_when_nothing_to_merge()
    print("ALL PASSED")
