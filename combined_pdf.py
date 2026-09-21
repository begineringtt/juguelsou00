"""여러 문서(pdf/이미지/xlsx)를 순서대로 하나의 인쇄용 PDF로 병합한다.

견적서 + 지출결의서 + 사업자등록증 + 통장사본처럼 형식이 제각각인 파일들을
한 번에 인쇄할 수 있도록 묶는다. 이미 requirements.txt에 있는 PyMuPDF(fitz)만
사용하고 별도 의존성을 추가하지 않는다.
"""

import os

import fitz

import pdf_convert

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
_XLSX_EXTS = {".xlsx", ".xls"}


def build_combined_pdf(paths, out_path):
    """paths 순서대로 병합한 PDF를 out_path에 저장한다.

    없는 파일이나 지원하지 않는 형식은 건너뛰고 이유와 함께 skipped에 담는다.
    병합할 파일이 하나도 없으면 out_path를 만들지 않고 path=None을 반환한다.

    반환: {"path": out_path|None, "skipped": [(path, reason), ...]}
    """
    out_doc = fitz.open()
    skipped = []
    try:
        for path in paths:
            if not path or not os.path.isfile(path):
                skipped.append((path, "파일 없음"))
                continue
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext == ".pdf":
                    _insert_pdf(out_doc, path)
                elif ext in _IMAGE_EXTS:
                    _insert_image(out_doc, path)
                elif ext in _XLSX_EXTS:
                    converted = pdf_convert.xlsx_to_pdf(path)
                    _insert_pdf(out_doc, converted)
                else:
                    skipped.append((path, f"지원하지 않는 형식: {ext}"))
            except Exception as e:
                skipped.append((path, str(e)))

        if out_doc.page_count == 0:
            return {"path": None, "skipped": skipped}

        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        out_doc.save(out_path)
        return {"path": out_path, "skipped": skipped}
    finally:
        out_doc.close()


def _insert_pdf(out_doc, pdf_path):
    with fitz.open(pdf_path) as src:
        out_doc.insert_pdf(src)


def _insert_image(out_doc, image_path):
    with fitz.open(image_path) as img_doc:
        pdf_bytes = img_doc.convert_to_pdf()
    with fitz.open("pdf", pdf_bytes) as img_pdf:
        out_doc.insert_pdf(img_pdf)
