import io
import os
import unittest
from unittest import mock

from PIL import Image

import pdf_item_parser as P
import quote_reader

# 실제로 90도 회전된 상태로 촬영된 견적서 사진(사용자 제보 샘플). 이 환경에 없으면
# 스킵한다.
SAMPLE_ROTATED_QUOTE = (
    r"D:\claude_personal\setting_03\인식률 테스트\관수작업 비교견적서.jpg"
)


class FixImageOrientationTest(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(SAMPLE_ROTATED_QUOTE), "회전된 실제 샘플 사진 없음")
    def test_fix_image_orientation_corrects_sideways_photo(self):
        img = Image.open(SAMPLE_ROTATED_QUOTE).convert("RGB")
        fixed = P._preprocess_for_ocr(P.fix_image_orientation(img))
        text = P.ocr_page_text(fixed)
        self.assertIn("상호", text)


class ReadImageQuoteOrientationWiringTest(unittest.TestCase):
    def test_read_image_quote_corrects_orientation_before_ocr(self):
        img = Image.new("RGB", (20, 20), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        with mock.patch.object(
            quote_reader.P, "fix_image_orientation", wraps=quote_reader.P.fix_image_orientation
        ) as spy:
            quote_reader.read_quote(data_bytes=buf.getvalue(), ext=".png")

        spy.assert_called_once()


class ReadImageQuotePreprocessingTest(unittest.TestCase):
    def test_read_image_quote_runs_item_ocr_on_the_preprocessed_image(self):
        # _parse_scanned_pdf()(스캔 PDF 경로)와 똑같이, 이미지 업로드 경로도 품목 OCR
        # 전에 그레이스케일->이진화->deskew->노이즈제거 전처리를 거쳐야 한다.
        img = Image.new("RGB", (20, 20), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        sentinel = Image.new("L", (20, 20), 0)
        with mock.patch.object(quote_reader.P, "_preprocess_for_ocr", return_value=sentinel), \
             mock.patch.object(quote_reader.P, "ocr_extract_items", return_value=([], None)) as items_spy:
            quote_reader.read_quote(data_bytes=buf.getvalue(), ext=".png")

        items_spy.assert_called_once()
        self.assertIs(items_spy.call_args.args[0], sentinel)


class ReadImageQuoteCompanyOnlyTest(unittest.TestCase):
    def test_company_only_skips_the_expensive_item_table_ocr(self):
        # ocr_extract_items()는 표 셀마다 별도 Tesseract 프로세스를 띄워서 큰
        # 사진에서는 몇 분씩 걸릴 수 있다. 배치 화면의 "업체명 자동 인식" 미리보기는
        # company/title만 쓰므로, company_only=True일 때는 이 비싼 경로를 아예
        # 타지 않아야 한다.
        img = Image.new("RGB", (20, 20), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        with mock.patch.object(quote_reader.P, "ocr_extract_items") as items_spy, \
             mock.patch.object(quote_reader.P, "ocr_page_text", return_value="상호: 테스트상사"):
            result = quote_reader.read_quote(
                data_bytes=buf.getvalue(), ext=".png", company_only=True
            )

        items_spy.assert_not_called()
        self.assertEqual(result["items"], [])
        self.assertEqual(result["company"], "테스트상사")


class ReadImageQuoteItemsShapeTest(unittest.TestCase):
    def test_read_image_quote_returns_items_as_a_list_not_a_tuple(self):
        img = Image.new("RGB", (20, 20), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")

        result = quote_reader.read_quote(data_bytes=buf.getvalue(), ext=".png")

        self.assertIsInstance(result["items"], list)


if __name__ == "__main__":
    unittest.main()
