import base64
import os

import fitz
import numpy as np
import pytesseract

import pdf_item_parser
from pdf_item_parser import (
    normalize_header, match_field, match_field_fuzzy, parse_number,
    find_header_row, score_table, map_table_columns, extract_items_from_table,
    resolve_duplicate_price_columns, clean_item_rows, apply_hierarchical_prefix,
    extract_paragraph_fallback, render_page_images, parse_pdf_items,
    extract_company_name, extract_title, _recover_missing_name_column,
)

SAMPLE_DIR = r"D:\claude_personal\setting_01\PDF_read"


def _load_sample(filename):
    with open(os.path.join(SAMPLE_DIR, filename), "rb") as f:
        return f.read()


def test_normalize_header_strips_whitespace_and_uppercases():
    assert normalize_header("품 명") == "품명"
    assert normalize_header("Unit Price") == "UNITPRICE"
    assert normalize_header(None) == ""
    print("OK: test_normalize_header_strips_whitespace_and_uppercases")


def test_match_field_exact_single_line():
    assert match_field("품명") == "name"
    assert match_field("규 격") == "spec"
    assert match_field("UNIT") == "unit"
    assert match_field("Q'TY") == "qty"
    assert match_field("단가") == "price"
    assert match_field("비고") is None
    print("OK: test_match_field_exact_single_line")


def test_match_field_multiline_header_checks_each_line():
    assert match_field("품 명\nDESCRIPTION") == "name"
    assert match_field("공사명/품명\nDESCRIPTION") == "name"
    assert match_field("단가\nUNIT PRICE") == "price"
    print("OK: test_match_field_multiline_header_checks_each_line")


def test_match_field_recognizes_description_as_name():
    assert match_field("DESCRIPTION") == "name"
    assert match_field("품 명\nDESCRIPTION") == "name"
    print("OK: test_match_field_recognizes_description_as_name")


def test_match_field_fuzzy_matches_substring_with_bullet_prefix():
    assert match_field_fuzzy("ㅇ. 품 명 ") == "name"
    assert match_field_fuzzy("ㅇ. 단 가 ") == "price"
    # 공급가액/부가세는 printed_supply/printed_vat로 인식된다 (OCR 검산용).
    assert match_field_fuzzy("ㅇ. 공 급 가 액") == "printed_supply"
    assert match_field_fuzzy("ㅇ. 부 가 세") == "printed_vat"
    print("OK: test_match_field_fuzzy_matches_substring_with_bullet_prefix")


def test_match_field_exact_recognizes_quantity_synonym():
    assert match_field("Quantity") == "qty"
    print("OK: test_match_field_exact_recognizes_quantity_synonym")


def test_find_header_row_uses_fuzzy_fallback_for_unmatched_exact_labels():
    # "Price(￦/M2)"는 "UNIT PRICE"/"단가"와 정확히 일치하지 않지만 "PRICE"를
    # 부분 문자열로 포함하므로 fuzzy fallback으로 매칭돼야 한다.
    table = [
        ["Description", "Quantity", "Unit", "Price(￦/M2)"],
        ["ETFE film", "2.0", "days", "6,119,375"],
    ]
    idx, score = find_header_row(table)
    assert idx == 0
    assert score == 4
    print("OK: test_find_header_row_uses_fuzzy_fallback_for_unmatched_exact_labels")


def test_map_table_columns_maps_quantity_and_bracketed_price_headers():
    table = [
        ["Description", "Quantity", "Unit", "Price(￦/M2)"],
        ["ETFE film", "2.0", "days", "6,119,375"],
    ]
    result = map_table_columns(table)
    assert result["columns"] == {"name": [0], "qty": [1], "unit": [2], "price": [3]}
    print("OK: test_map_table_columns_maps_quantity_and_bracketed_price_headers")


def _words(*text_left_pairs):
    return [{"text": text, "left": left} for text, left in text_left_pairs]


def test_match_row_labels_merges_split_syllables():
    # Tesseract가 "품명"을 음절 단위로 쪼개 "품", "명" 두 단어로 인식하는 경우가
    # 흔한데, 단어 하나만 보면 2글자 라벨을 절대 못 찾는다.
    fields = pdf_item_parser._match_row_labels(_words(("품", 0), ("명", 40)))
    assert fields == {"name": [0]}
    print("OK: test_match_row_labels_merges_split_syllables")


def test_match_row_labels_skips_noise_tokens_between_syllables():
    # 표 테두리 등이 "_"/"|" 같은 잡음 단어로 잡혀 음절 사이에 끼어드는 경우.
    fields = pdf_item_parser._match_row_labels(_words(("품", 0), ("_", 30), ("명", 60)))
    assert fields == {"name": [0]}
    print("OK: test_match_row_labels_skips_noise_tokens_between_syllables")


def test_match_row_labels_unrelated_seed_does_not_swallow_next_label():
    # "No"(행 번호)가 이어붙이기 시작점이 되어 뒤따르는 "품"+"명"까지 삼켜서
    # "No품명"을 "품명"의 부분 문자열로 오인식하면 안 된다 - 앵커 위치가
    # "No"(0)가 아니라 "품"(50)이어야 한다.
    fields = pdf_item_parser._match_row_labels(_words(("No", 0), ("품", 50), ("명", 90)))
    assert fields == {"name": [50]}
    print("OK: test_match_row_labels_unrelated_seed_does_not_swallow_next_label")


def test_match_row_labels_does_not_cross_into_next_label():
    # "명"(품명의 뒷글자)에서 시작해 다음 라벨 "규"+"격"까지 이어붙이면
    # "명규격"이 "규격"을 부분 문자열로 포함해버려 spec이 중복/오탐된다 -
    # 접두사 일치만 허용해서 이걸 막아야 한다.
    fields = pdf_item_parser._match_row_labels(
        _words(("품", 0), ("명", 40), ("규", 90), ("격", 130))
    )
    assert fields == {"name": [0], "spec": [90]}
    print("OK: test_match_row_labels_does_not_cross_into_next_label")


def test_parse_number_handles_currency_and_stray_spaces():
    assert parse_number("550,000") == 550000.0
    assert parse_number("2 ,100,000") == 2100000.0
    assert parse_number("₩1,040,000") == 1040000.0
    assert parse_number("1.950 MT") == 1.95
    assert parse_number("-") is None
    assert parse_number("") is None
    assert parse_number(None) is None
    assert parse_number("TCP/IP") is None
    print("OK: test_parse_number_handles_currency_and_stray_spaces")


def test_find_header_row_at_index_zero():
    table = [
        ["품명", "수량", "단가"],
        ["볼트", "10", "1000"],
    ]
    idx, score = find_header_row(table)
    assert idx == 0
    assert score == 3
    print("OK: test_find_header_row_at_index_zero")


def test_find_header_row_scans_past_summary_row():
    table = [
        ["합계금액 안내문", None, None],
        ["No", "품 명", "규 격", "단위", "수량", "단 가", "금 액"],
        ["1", "볼트", "M12", "EA", "10", "1000", "10000"],
    ]
    idx, score = find_header_row(table)
    assert idx == 1
    # 품명/규격/단위/수량/단가/금액(printed_supply) 6개 라벨이 매칭된다.
    assert score == 6
    print("OK: test_find_header_row_scans_past_summary_row")


def test_find_header_row_scans_past_five_metadata_rows():
    table = [
        ["사업자 번호", "311-09-25603"],
        ["업체 / 대표", "세화볼트"],
        ["주 소", "경기 화성시"],
        ["업 종", "도소매"],
        ["전화 / 팩스", "031-000-0000"],
        ["순번", "품 명", "규 격", "단 위", "수량", "단 가", "공급가액", "비 고"],
        ["1", "볼트", "M12", "EA", "10", "1000", "10000", ""],
    ]
    idx, score = find_header_row(table)
    assert idx == 5
    # 품명/규격/단위/수량/단가/공급가액(printed_supply) 6개 라벨이 매칭된다.
    assert score == 6
    print("OK: test_find_header_row_scans_past_five_metadata_rows")


def test_score_table_counts_matched_fields():
    assert score_table([["품명", "수량", "단가"]]) == 3
    assert score_table([["회 사 명", "값"]]) == 0
    assert score_table([]) == 0
    print("OK: test_score_table_counts_matched_fields")


def test_map_table_columns_basic():
    table = [
        ["품명", "규격", "단위", "수량", "단가", "비고"],
        ["볼트", "M12", "EA", "10", "1000", ""],
    ]
    result = map_table_columns(table)
    assert result["data_start"] == 1
    assert result["columns"] == {"name": [0], "spec": [1], "unit": [2], "qty": [3], "price": [4]}
    print("OK: test_map_table_columns_basic")


def test_map_table_columns_finds_header_not_at_row_zero():
    table = [
        ["합계금액 안내문", None, None],
        ["품명", "수량", "단가"],
        ["볼트", "10", "1000"],
    ]
    result = map_table_columns(table)
    assert result["data_start"] == 2
    assert result["columns"]["name"] == [0]
    print("OK: test_map_table_columns_finds_header_not_at_row_zero")


def test_map_table_columns_detects_duplicate_price_header():
    table = [
        ["품 명", "형식", "수 량", "단가", "단가", "납기"],
        ["DR100GF", "", "2", "520000", "1040000", "2-3일"],
    ]
    result = map_table_columns(table)
    assert result["columns"]["price"] == [3, 4]
    print("OK: test_map_table_columns_detects_duplicate_price_header")


def test_map_table_columns_returns_none_without_name_column():
    table = [["회 사 명", "주식회사 쉘파스페이스"]]
    assert map_table_columns(table) is None
    print("OK: test_map_table_columns_returns_none_without_name_column")


def test_map_table_columns_returns_none_without_qty_or_price():
    table = [["품명", "규격", "단위"], ["볼트", "M12", "EA"]]
    assert map_table_columns(table) is None
    print("OK: test_map_table_columns_returns_none_without_qty_or_price")


def test_extract_items_from_table_basic():
    table = [
        ["품명", "규격", "단위", "수량", "단가"],
        ["볼트", "M12", "EA", "10", "1,000"],
        ["", "", "", "", ""],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert rows == [
        {"name": "볼트", "spec": "M12", "unit": "EA", "qty_raw": "10", "price_raws": ["1,000"]},
    ]
    print("OK: test_extract_items_from_table_basic")


def test_extract_items_from_table_keeps_both_duplicate_price_columns():
    table = [
        ["품 명", "형식", "수 량", "단가", "단가"],
        ["DR100GF", "", "2", "520000", "1040000"],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert rows[0]["price_raws"] == ["520000", "1040000"]
    print("OK: test_extract_items_from_table_keeps_both_duplicate_price_columns")


def test_extract_items_from_table_skips_rows_without_name():
    table = [
        ["품명", "수량", "단가"],
        [None, "1", "100"],
        ["볼트", "10", "1000"],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert len(rows) == 1
    assert rows[0]["name"] == "볼트"
    print("OK: test_extract_items_from_table_skips_rows_without_name")


def test_extract_items_from_table_recovers_data_fused_into_header_row():
    table = [
        ["품 명\nDESCRIPTION\n온습도검출기", "규격\nSIZE\n범위 -20~80", "단위\nUNIT\nEA", "수량\nQ'TY\n3", "단가\nUNIT PRICE\n550,000"],
        ["온도검출기", "범위 -40~60", "EA", "2", "258,000"],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert rows[0] == {"name": "온습도검출기", "spec": "범위 -20~80", "unit": "EA", "qty_raw": "3", "price_raws": ["550,000"]}
    assert rows[1]["name"] == "온도검출기"
    assert len(rows) == 2
    print("OK: test_extract_items_from_table_recovers_data_fused_into_header_row")


def test_extract_items_from_table_no_phantom_row_for_bilingual_header_without_fused_data():
    table = [
        ["공사명/품명\nDESCRIPTION", "규격\nSIZE", "수량\nQ'TY", "단위\nUNIT", "단가\nUNIT PRICE"],
        ["외함", "옥내형", "1", "EA", "500000"],
    ]
    mapping = map_table_columns(table)
    rows = extract_items_from_table(table, mapping)
    assert len(rows) == 1
    assert rows[0]["name"] == "외함"
    print("OK: test_extract_items_from_table_no_phantom_row_for_bilingual_header_without_fused_data")


def test_resolve_single_price_column():
    rows = [{"name": "볼트", "spec": "M12", "unit": "EA", "qty_raw": "10", "price_raws": ["1,000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved == [{"name": "볼트", "spec": "M12", "unit": "EA", "qty": 10.0, "price": 1000.0}]
    print("OK: test_resolve_single_price_column")


def test_resolve_duplicate_price_picks_column_matching_qty_times_price():
    rows = [{"name": "DR100GF", "spec": "", "unit": "", "qty_raw": "2", "price_raws": ["520000", "1040000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved[0]["price"] == 520000.0
    assert resolved[0]["qty"] == 2.0
    print("OK: test_resolve_duplicate_price_picks_column_matching_qty_times_price")


def test_resolve_duplicate_price_handles_swapped_columns():
    rows = [{"name": "X", "spec": "", "unit": "", "qty_raw": "2", "price_raws": ["1040000", "520000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved[0]["price"] == 520000.0
    print("OK: test_resolve_duplicate_price_handles_swapped_columns")


def test_resolve_duplicate_price_defaults_to_first_when_qty_missing():
    rows = [{"name": "X", "spec": "", "unit": "", "qty_raw": "", "price_raws": ["520000", "1040000"]}]
    resolved = resolve_duplicate_price_columns(rows)
    assert resolved[0]["price"] == 520000.0
    assert resolved[0]["qty"] is None
    print("OK: test_resolve_duplicate_price_defaults_to_first_when_qty_missing")


def test_clean_item_rows_drops_summary_and_footer_rows():
    rows = [
        {"name": "볼트", "spec": "", "unit": "EA", "qty": 10.0, "price": 1000.0},
        {"name": "합 계", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "** 이하여백 **", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "Remark", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "Sub Total", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "너트", "spec": "", "unit": "EA", "qty": 5.0, "price": 500.0},
    ]
    cleaned = clean_item_rows(rows)
    assert [r["name"] for r in cleaned] == ["볼트", "너트"]
    print("OK: test_clean_item_rows_drops_summary_and_footer_rows")


def test_clean_item_rows_keeps_category_like_rows():
    rows = [{"name": "HONEYWELL", "spec": "", "unit": "", "qty": None, "price": None}]
    cleaned = clean_item_rows(rows)
    assert [r["name"] for r in cleaned] == ["HONEYWELL"]
    print("OK: test_clean_item_rows_keeps_category_like_rows")


def test_apply_hierarchical_prefix_prefixes_following_rows():
    rows = [
        {"name": "온실제어 INTERFACE", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "외함", "spec": "옥내형", "unit": "EA", "qty": 1.0, "price": 500000.0},
        {"name": "누전차단기", "spec": "EBS33~32", "unit": "식", "qty": 1.0, "price": 250000.0},
        {"name": "제어 CONTROLLER", "spec": "", "unit": "", "qty": None, "price": None},
        {"name": "PLC+TOUCH", "spec": "DR16S", "unit": "SET", "qty": 2.0, "price": 1700000.0},
    ]
    result = apply_hierarchical_prefix(rows)
    assert [r["name"] for r in result] == [
        "온실제어 INTERFACE - 외함",
        "온실제어 INTERFACE - 누전차단기",
        "제어 CONTROLLER - PLC+TOUCH",
    ]
    print("OK: test_apply_hierarchical_prefix_prefixes_following_rows")


def test_apply_hierarchical_prefix_passes_through_flat_rows_unchanged():
    rows = [
        {"name": "볼트", "spec": "M12", "unit": "EA", "qty": 10.0, "price": 1000.0},
        {"name": "너트", "spec": "M12", "unit": "EA", "qty": 5.0, "price": 500.0},
    ]
    result = apply_hierarchical_prefix(rows)
    assert result == rows
    print("OK: test_apply_hierarchical_prefix_passes_through_flat_rows_unchanged")


def test_extract_paragraph_fallback_finds_labelled_values():
    text = (
        "ㅇ. 품 명 : AL- Ingot\n"
        "ㅇ. 출 고 일 : 2026년 6월 1일\n"
        "ㅇ. 수 량 : 1.950 MT\n"
        "ㅇ. 단 가 : 6,250,000 원/MT (가단가)\n"
        "ㅇ. 공 급 가 액 : 12,187,500 원\n"
        "ㅇ. 부 가 세 : 1,218,750 원\n"
    )
    item = extract_paragraph_fallback(text)
    assert item["name"] == "AL- Ingot"
    assert item["qty"] == 1.95
    assert item["price"] == 6250000.0
    assert item["spec"] == ""
    assert item["unit"] == ""
    print("OK: test_extract_paragraph_fallback_finds_labelled_values")


def test_extract_paragraph_fallback_returns_none_without_name():
    text = "문서번호 : KOR-260601-07\n수 신 : ㈜그린플러스\n"
    assert extract_paragraph_fallback(text) is None
    print("OK: test_extract_paragraph_fallback_returns_none_without_name")


def test_render_pages_for_ocr_uses_ocr_dpi_by_default():
    doc = fitz.open()
    doc.new_page(width=72, height=72)  # 72pt = 1inch @ 72dpi
    pdf_bytes = doc.tobytes()
    doc.close()

    images = pdf_item_parser._render_pages_for_ocr(pdf_bytes)
    assert len(images) == 1
    # 1인치 x 1인치 페이지를 OCR_DPI(기본 350)로 렌더링하면 각 변이 350px 근방이어야
    # 한다 (반올림 오차 몇 px 정도는 허용).
    w, h = images[0].size
    assert abs(w - pdf_item_parser.OCR_DPI) <= 2
    assert abs(h - pdf_item_parser.OCR_DPI) <= 2
    print("OK: test_render_pages_for_ocr_uses_ocr_dpi_by_default")


def test_cluster_positions_groups_consecutive_active_regions_by_center():
    projection = np.array([0, 0, 5, 5, 5, 0, 0, 0, 3, 3, 0])
    positions = pdf_item_parser._cluster_positions(projection, min_count=1)
    assert positions == [3, 8]
    print("OK: test_cluster_positions_groups_consecutive_active_regions_by_center")


def test_cluster_positions_empty_projection_returns_empty_list():
    assert pdf_item_parser._cluster_positions(np.array([]), min_count=1) == []
    assert pdf_item_parser._cluster_positions(np.array([0, 0, 0]), min_count=1) == []
    print("OK: test_cluster_positions_empty_projection_returns_empty_list")


def test_deskew_straightens_rotated_horizontal_lines():
    import cv2
    from PIL import Image, ImageDraw

    img = Image.new("L", (600, 400), color=255)
    draw = ImageDraw.Draw(img)
    for y in range(150, 260, 20):
        draw.line([(60, y), (540, y)], fill=0, width=6)
    rotated = img.rotate(6, expand=True, fillcolor=255, resample=Image.BICUBIC)

    binary = np.array(rotated)
    _, binary = cv2.threshold(binary, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    deskewed = pdf_item_parser._deskew(binary)

    # 보정 후 다시 기울기를 재보면 원래(6도)보다 훨씬 0에 가까워야 한다.
    inverted = cv2.bitwise_not(deskewed)
    coords = np.column_stack(np.where(inverted > 0))
    angle = cv2.minAreaRect(coords)[-1]
    residual = angle if angle >= -45 else 90 + angle
    assert abs(residual) < 2.0
    print("OK: test_deskew_straightens_rotated_horizontal_lines")


def test_preprocess_for_ocr_returns_grayscale_image_same_size():
    from PIL import Image

    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    result = pdf_item_parser._preprocess_for_ocr(img)
    assert result.mode == "L"
    assert result.size == (200, 100)
    print("OK: test_preprocess_for_ocr_returns_grayscale_image_same_size")


def test_ocr_cell_numeric_config_includes_whitelist():
    captured = {}

    def fake_image_to_string(image, lang=None, config=None):
        captured["config"] = config
        return "1,234"

    original = pytesseract.image_to_string
    pytesseract.image_to_string = fake_image_to_string
    try:
        from PIL import Image
        img = Image.new("L", (100, 40), color=255)

        pdf_item_parser._ocr_cell(img, (0, 0, 100, 40), numeric=True)
        assert "tessedit_char_whitelist=0123456789,." in captured["config"]

        pdf_item_parser._ocr_cell(img, (0, 0, 100, 40), numeric=False)
        assert "tessedit_char_whitelist" not in captured["config"]
    finally:
        pytesseract.image_to_string = original
    print("OK: test_ocr_cell_numeric_config_includes_whitelist")


def test_ocr_cell_strips_border_noise_characters():
    def fake_image_to_string(image, lang=None, config=None):
        return "| 품 명 ["

    original = pytesseract.image_to_string
    pytesseract.image_to_string = fake_image_to_string
    try:
        from PIL import Image
        img = Image.new("L", (100, 40), color=255)
        text = pdf_item_parser._ocr_cell(img, (0, 0, 100, 40))
        assert text == "품 명"
    finally:
        pytesseract.image_to_string = original
    print("OK: test_ocr_cell_strips_border_noise_characters")


def test_flag_arithmetic_mismatches_flags_incorrect_printed_supply():
    items = [
        {"name": "정상", "qty": 2.0, "price": 1000.0, "printed_supply": "2,000"},
        {"name": "오류", "qty": 2.0, "price": 1000.0, "printed_supply": "1,000"},
    ]
    flagged = pdf_item_parser._flag_arithmetic_mismatches(items)
    assert not flagged[0].get("_flagged")
    assert flagged[1]["_flagged"] is True
    print("OK: test_flag_arithmetic_mismatches_flags_incorrect_printed_supply")


def test_flag_arithmetic_mismatches_prefers_weight_over_qty():
    # 중량이 있으면 수량 대신 중량 x 단가로 검산한다 (generator.py와 동일한 규칙).
    items = [{"name": "중량품목", "qty": 999.0, "weight": "5", "price": 7400.0, "printed_supply": "37000"}]
    flagged = pdf_item_parser._flag_arithmetic_mismatches(items)
    assert not flagged[0].get("_flagged")
    print("OK: test_flag_arithmetic_mismatches_prefers_weight_over_qty")


def test_flag_arithmetic_mismatches_skips_rows_missing_data():
    items = [{"name": "정보부족", "qty": None, "price": None}]
    flagged = pdf_item_parser._flag_arithmetic_mismatches(items)
    assert not flagged[0].get("_flagged")
    print("OK: test_flag_arithmetic_mismatches_skips_rows_missing_data")


def test_render_page_images_returns_one_png_per_page():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()

    images = render_page_images(pdf_bytes)

    assert len(images) == 2
    for img_b64 in images:
        raw = base64.b64decode(img_b64)
        assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    print("OK: test_render_page_images_returns_one_png_per_page")


def test_recover_missing_name_column_fills_structurally_missing_cell():
    from pdf_item_parser import _recover_missing_name_column

    rows = [
        [None, "Quantity", "Unit"],
        [None, "2.0", "days"],
    ]
    row_cells = [
        [None, (100, 0, 150, 20), (150, 0, 200, 20)],
        [None, (100, 20, 150, 40), (150, 20, 200, 40)],
    ]
    crop_calls = []

    def fake_crop(x0, top, x1, bottom):
        crop_calls.append((x0, top, x1, bottom))
        return {
            (0, 0, 100, 20): "Description",
            (0, 20, 100, 40): "ETFE film",
        }.get((x0, top, x1, bottom))

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result[0][0] == "Description"
    assert result[1][0] == "ETFE film"
    assert len(crop_calls) == 2
    print("OK: test_recover_missing_name_column_fills_structurally_missing_cell")


def test_recover_missing_name_column_leaves_existing_cells_untouched():
    from pdf_item_parser import _recover_missing_name_column

    rows = [["TOTAL", "", "", "999"]]
    row_cells = [[(0, 0, 50, 20), (50, 0, 80, 20), (80, 0, 110, 20), (110, 0, 150, 20)]]

    def fake_crop(*args):
        raise AssertionError("이미 셀이 있는 행은 크롭을 호출하면 안 된다")

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result == rows
    print("OK: test_recover_missing_name_column_leaves_existing_cells_untouched")


def test_recover_missing_name_column_skips_when_no_other_cells_to_bound_region():
    from pdf_item_parser import _recover_missing_name_column

    rows = [[None, None, None]]
    row_cells = [[None, None, None]]

    def fake_crop(*args):
        raise AssertionError("경계로 쓸 다른 칸이 없으면 크롭을 호출하면 안 된다")

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result[0][0] is None
    print("OK: test_recover_missing_name_column_skips_when_no_other_cells_to_bound_region")


def test_recover_missing_name_column_skips_when_crop_returns_no_text():
    from pdf_item_parser import _recover_missing_name_column

    rows = [[None, "1"]]
    row_cells = [[None, (50, 0, 80, 20)]]

    def fake_crop(x0, top, x1, bottom):
        return None

    result = _recover_missing_name_column(0, rows, row_cells, fake_crop)
    assert result[0][0] is None
    print("OK: test_recover_missing_name_column_skips_when_crop_returns_no_text")


def test_parse_pdf_items_normal_table_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_normal_table_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_한수_근권부.pdf"))
    names = [it["name"] for it in result["items"]]
    assert names == ["무선 온습도 데이터 로거", "CO2 데이터 로거"]
    assert result["items"][0]["spec"] == "TR-72"
    assert result["items"][0]["unit"] == "SET"
    assert result["items"][0]["qty"] == 13.0
    assert result["items"][0]["price"] == 660000.0
    assert result["warnings"] == []
    assert len(result["page_images"]) == 1
    assert result["company"] == "한수과학"
    assert result["title"] is None
    print("OK: test_parse_pdf_items_normal_table_case")


def test_parse_pdf_items_hierarchical_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_hierarchical_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("2. 견적서(제어)-온실제어장치-26.05_수정.pdf"))
    names = [it["name"] for it in result["items"]]
    assert "온실제어 INTERFACE - 외함" in names
    assert "제어 CONTROLLER - PLC+TOUCH" in names
    assert "배선 자재 - 전선(F-CV)" in names
    assert result["company"] == "아이온이엔지"
    assert result["title"] == "환경제어 계측 자재 대전의 건"
    print("OK: test_parse_pdf_items_hierarchical_case")


def test_parse_pdf_items_duplicate_header_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_duplicate_header_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("한열사_견적서_북미.pdf"))
    by_name = {it["name"]: it for it in result["items"]}
    assert by_name["HONEYWELL - DR100GF"]["price"] == 520000.0
    assert by_name["HONEYWELL - DR100GF"]["qty"] == 2.0
    assert result["company"] == "한열사"
    assert result["title"] is None
    print("OK: test_parse_pdf_items_duplicate_header_case")


def test_parse_pdf_items_no_table_fallback_case():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_no_table_fallback_case (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_코랄_수확후.pdf"))
    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "AL- Ingot"
    assert result["items"][0]["price"] == 6250000.0
    assert result["warnings"]
    assert result["company"] == "㈜코랄인터내셔널"
    assert result["title"] == "AL Ingot 견적서 발송의 건"
    print("OK: test_parse_pdf_items_no_table_fallback_case")


def test_parse_pdf_items_scanned_pdf_uses_ocr_for_company():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_scanned_pdf_uses_ocr_for_company (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_알루스퀘어.pdf"))
    assert result["company"] == "알루스퀘어"
    assert any("OCR" in w for w in result["warnings"])
    assert len(result["page_images"]) == 1
    print("OK: test_parse_pdf_items_scanned_pdf_uses_ocr_for_company")


def test_parse_pdf_items_scanned_pdf_recovers_item_name_and_spec():
    # 이 PDF는 전체 페이지를 저해상도 배경(JPEG)으로 깔고 실제 글자는 고해상도
    # 1비트 스캔 이미지를 별도로 얹은 팩스 스캔본이라, 페이지 전체를 한 번에
    # 렌더링해서 OCR하면(zoom을 얼마나 올리든) 표 헤더/품목 글자가 뭉개져
    # 품명/규격을 전혀 인식하지 못했다(items == []였음). 임베드된 원본 이미지를
    # 리샘플링 없이 그대로 OCR하고, 음절 단위로 쪼개진 헤더 라벨("품","명")도
    # 이어붙여 인식하도록 고친 뒤에는 품명/규격이 채워져야 한다.
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_scanned_pdf_recovers_item_name_and_spec (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_알루스퀘어.pdf"))
    items = [it for it in result["items"] if "AL" in it["name"]]
    assert len(items) == 2
    for item in items:
        assert "AL" in item["name"]
        assert item["spec"].strip()
    print("OK: test_parse_pdf_items_scanned_pdf_recovers_item_name_and_spec")


def test_parse_pdf_items_scanned_pdf_grid_path_recovers_qty_weight_and_price():
    # 표 격자선을 검출해 셀 단위로 잘라 OCR하는 경로(DPI 상향 + 전처리 + 숫자
    # 화이트리스트 + 검산)가 실제로 정확한 수량/중량/단가/공급가를 뽑아내는지
    # 확인한다. 개선 전에는 수량이 전혀 인식되지 않았고(qty=None), 중량이
    # 인접 열의 숫자와 뒤섞여 "2 5"/"2 13" 같은 값이 나왔었다.
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_scanned_pdf_grid_path_recovers_qty_weight_and_price (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_알루스퀘어.pdf"))
    items = [it for it in result["items"] if "AL" in it["name"]]
    assert len(items) == 2
    assert items[0]["qty"] == 2.0
    assert items[0]["unit"] == "kg"
    assert items[0]["price"] == 7400.0
    assert items[0]["weight"] == 5.0
    assert items[1]["qty"] == 2.0
    assert items[1]["price"] == 7400.0
    assert items[1]["weight"] == 13.0
    # 공급가 = 중량 x 단가로 검산이 맞아떨어지므로 두 행 다 플래그가 없어야 한다.
    assert not items[0].get("_flagged")
    assert not items[1].get("_flagged")
    print("OK: test_parse_pdf_items_scanned_pdf_grid_path_recovers_qty_weight_and_price")


def test_parse_pdf_items_scanned_pdf_degrades_gracefully_without_tesseract():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_scanned_pdf_degrades_gracefully_without_tesseract (no sample dir)")
        return
    original_cmd = pytesseract.pytesseract.tesseract_cmd
    original_configured = pdf_item_parser._tesseract_configured
    pytesseract.pytesseract.tesseract_cmd = "definitely_missing_tesseract_binary.exe"
    pdf_item_parser._tesseract_configured = True
    try:
        result = parse_pdf_items(_load_sample("견적서_알루스퀘어.pdf"))
        assert result["items"] == []
        assert result["company"] is None
        assert result["title"] is None
        assert any("찾을 수 없" in w for w in result["warnings"])
    finally:
        pytesseract.pytesseract.tesseract_cmd = original_cmd
        pdf_item_parser._tesseract_configured = original_configured
    print("OK: test_parse_pdf_items_scanned_pdf_degrades_gracefully_without_tesseract")


def test_parse_pdf_items_recovers_borderless_name_column_with_english_headers():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_recovers_borderless_name_column_with_english_headers (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_20260721(그린플러스_IR Cut_8월).pdf"))
    items = result["items"]
    assert len(items) == 2
    assert items[0]["qty"] == 2.0
    assert items[0]["unit"] == "days"
    assert items[0]["price"] == 6119375.0
    assert "ETFE" in items[0]["name"]
    assert items[1]["qty"] == 1300.0
    assert items[1]["unit"] == "㎡"
    assert items[1]["price"] == 11000.0
    assert "Nb2O5" in items[1]["name"]
    print("OK: test_parse_pdf_items_recovers_borderless_name_column_with_english_headers")


def test_extract_company_name_various_samples():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_extract_company_name_various_samples (no sample dir)")
        return
    cases = {
        "2. 견적서_세화볼트.pdf": "세화볼트",
        "2. 그린플러스_광센서_견적서.pdf": "쉘파스페이스",
        "견적서_20260721(그린플러스_IR Cut_8월).pdf": "마이크로웍스솔루션즈 주식회사",
        "견적서_일신_북미.pdf": "일신폴리캠",
        "2. 견적서.pdf": None,
    }
    for filename, expected in cases.items():
        with open(os.path.join(SAMPLE_DIR, filename), "rb") as f:
            text_source = f.read()
        result = parse_pdf_items(text_source)
        assert result["company"] == expected, f"{filename}: expected {expected!r}, got {result['company']!r}"
    print("OK: test_extract_company_name_various_samples")


def test_extract_company_name_excludes_our_own_company():
    text = "受信處 : ㈜그린플러스 貴下\n(주)아이온이엔지\n대전광역시대덕구선비마을로6번길15-8"
    assert extract_company_name(text) == "아이온이엔지"

    text2 = "회 사 명 : (주)그린플러스\n담 당 :\n(주)한 열 사"
    assert extract_company_name(text2) == "한열사"

    text3 = "수신: 그린플러스 귀하\n아무 내용도 없음"
    assert extract_company_name(text3) is None
    print("OK: test_extract_company_name_excludes_our_own_company")


def test_extract_title_various_samples():
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_extract_title_various_samples (no sample dir)")
        return
    cases = {
        "2. 견적서.pdf": "온실복합환경계측 자재의 건",
        "견적서_일신_북미.pdf": "폴리카보네이트 복층판의 건",
        "대금청구서-엽채류동 modbusTCP 작업 (2).pdf": "당진 K-Farm 엽채류동 modbusTCP 작업의 건",
        "2. 견적서_세화볼트.pdf": None,
        "견적서_20260721(그린플러스_IR Cut_8월).pdf": None,
    }
    for filename, expected in cases.items():
        with open(os.path.join(SAMPLE_DIR, filename), "rb") as f:
            text_source = f.read()
        result = parse_pdf_items(text_source)
        assert result["title"] == expected, f"{filename}: expected {expected!r}, got {result['title']!r}"
    print("OK: test_extract_title_various_samples")


def test_extract_title_handles_korean_hanja_and_english_labels():
    assert extract_title("물품명 : 온실복합환경계측 자재") == "온실복합환경계측 자재의 건"
    assert extract_title("見 積 名 : 환경제어 계측 자재") == "환경제어 계측 자재의 건"
    assert extract_title("SUBJECT: Greenhouse control materials") == "Greenhouse control materials의 건"
    assert extract_title("공사명/품명 규격 수량 단위 단가 금액 비 고") is None
    assert extract_title("DESCRIPTION SIZE Q'TY UNIT UNIT PRICE AMOUNT REMARK") is None
    print("OK: test_extract_title_handles_korean_hanja_and_english_labels")


def test_extract_title_truncates_at_trailing_contact_info():
    text = "내 용 : 당진 K-Farm 엽채류동 modbusTCP 작업 연락처 : (T)042-631-2204 (F)042-639-2204"
    assert extract_title(text) == "당진 K-Farm 엽채류동 modbusTCP 작업의 건"
    print("OK: test_extract_title_truncates_at_trailing_contact_info")


def test_extract_title_does_not_duplicate_existing_case_suffix():
    assert extract_title("제 목 : 자재 구매의 건") == "자재 구매의 건"
    print("OK: test_extract_title_does_not_duplicate_existing_case_suffix")


def test_detect_field_order_follows_left_to_right_column_index():
    table = [
        ["품명", "수량", "중량", "단가", "규격"],
        ["AL바", "5", "25kg", "7400", "100x5"],
    ]
    mapping = map_table_columns(table)
    assert pdf_item_parser._detect_field_order(mapping) == ["qty", "weight", "price", "spec"]
    print("OK: test_detect_field_order_follows_left_to_right_column_index")


def test_detect_field_order_returns_none_without_mapping():
    assert pdf_item_parser._detect_field_order(None) is None
    print("OK: test_detect_field_order_returns_none_without_mapping")


def test_weight_is_recognized_natively_without_extra_synonyms():
    """중량은 이제 spec/unit/qty/price와 같은 내장 필드라, synonyms를 따로 안 넘겨도
    HEADER_SYNONYMS만으로 인식되어야 한다."""
    table = [
        ["품명", "규격", "수량", "중량", "단가"],
        ["AL바", "100x5", "5", "25kg", "7400"],
    ]
    result = map_table_columns(table)
    assert result["columns"]["weight"] == [3]
    rows = extract_items_from_table(table, result)
    assert rows[0]["weight"] == "25kg"
    print("OK: test_weight_is_recognized_natively_without_extra_synonyms")


def test_map_table_columns_recognizes_custom_synonym():
    table = [
        ["품명", "규격", "수량", "중량", "단가"],
        ["AL바", "100x5", "5", "25kg", "7400"],
    ]
    result = map_table_columns(table, synonyms={"weight": ["중량"]})
    assert result["columns"]["weight"] == [3]
    print("OK: test_map_table_columns_recognizes_custom_synonym")


def test_extract_items_from_table_passes_through_custom_column():
    table = [
        ["품명", "규격", "수량", "중량", "단가"],
        ["AL바", "100x5", "5", "25kg", "7400"],
    ]
    synonyms = {"weight": ["중량"]}
    mapping = map_table_columns(table, synonyms=synonyms)
    rows = extract_items_from_table(table, mapping, synonyms=synonyms)
    assert rows[0]["weight"] == "25kg"
    resolved = resolve_duplicate_price_columns(rows)
    # weight는 qty/price처럼 숫자 필드라 resolve 단계에서 "25kg" -> 25.0으로 파싱된다.
    assert resolved[0]["weight"] == 25.0
    assert resolved[0]["price"] == 7400.0
    print("OK: test_extract_items_from_table_passes_through_custom_column")


def test_parse_pdf_items_without_extra_fields_is_unaffected():
    # extra_fields를 안 넘기면(기존 호출부) 기존 동작 그대로여야 한다.
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_without_extra_fields_is_unaffected (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_test.pdf"))
    assert result["items"]
    print("OK: test_parse_pdf_items_without_extra_fields_is_unaffected")


def test_parse_pdf_items_extra_fields_does_not_break_scanned_pdf_pipeline():
    # 알루스퀘어 PDF(OCR 경로)에 extra_fields를 넘겨도 파이프라인이 깨지지 않고,
    # 기존 회귀 테스트(품명/규격 인식)와 동일하게 최소 2개 품목이 나와야 한다.
    if not os.path.isdir(SAMPLE_DIR):
        print("SKIP: test_parse_pdf_items_extra_fields_does_not_break_scanned_pdf_pipeline (no sample dir)")
        return
    result = parse_pdf_items(_load_sample("견적서_알루스퀘어.pdf"), extra_fields={"weight": ["중량"]})
    items = [it for it in result["items"] if "AL" in it["name"]]
    assert len(items) == 2
    print("OK: test_parse_pdf_items_extra_fields_does_not_break_scanned_pdf_pipeline")


if __name__ == "__main__":
    test_normalize_header_strips_whitespace_and_uppercases()
    test_match_field_exact_single_line()
    test_match_field_multiline_header_checks_each_line()
    test_match_field_fuzzy_matches_substring_with_bullet_prefix()
    test_match_field_exact_recognizes_quantity_synonym()
    test_find_header_row_uses_fuzzy_fallback_for_unmatched_exact_labels()
    test_map_table_columns_maps_quantity_and_bracketed_price_headers()
    test_match_field_recognizes_description_as_name()
    test_match_row_labels_merges_split_syllables()
    test_match_row_labels_skips_noise_tokens_between_syllables()
    test_match_row_labels_unrelated_seed_does_not_swallow_next_label()
    test_match_row_labels_does_not_cross_into_next_label()
    test_parse_number_handles_currency_and_stray_spaces()
    test_find_header_row_at_index_zero()
    test_find_header_row_scans_past_summary_row()
    test_find_header_row_scans_past_five_metadata_rows()
    test_score_table_counts_matched_fields()
    test_map_table_columns_basic()
    test_map_table_columns_finds_header_not_at_row_zero()
    test_map_table_columns_detects_duplicate_price_header()
    test_map_table_columns_returns_none_without_name_column()
    test_map_table_columns_returns_none_without_qty_or_price()
    test_extract_items_from_table_basic()
    test_extract_items_from_table_keeps_both_duplicate_price_columns()
    test_extract_items_from_table_skips_rows_without_name()
    test_extract_items_from_table_recovers_data_fused_into_header_row()
    test_extract_items_from_table_no_phantom_row_for_bilingual_header_without_fused_data()
    test_resolve_single_price_column()
    test_resolve_duplicate_price_picks_column_matching_qty_times_price()
    test_resolve_duplicate_price_handles_swapped_columns()
    test_resolve_duplicate_price_defaults_to_first_when_qty_missing()
    test_clean_item_rows_drops_summary_and_footer_rows()
    test_clean_item_rows_keeps_category_like_rows()
    test_apply_hierarchical_prefix_prefixes_following_rows()
    test_apply_hierarchical_prefix_passes_through_flat_rows_unchanged()
    test_extract_paragraph_fallback_finds_labelled_values()
    test_extract_paragraph_fallback_returns_none_without_name()
    test_render_pages_for_ocr_uses_ocr_dpi_by_default()
    test_cluster_positions_groups_consecutive_active_regions_by_center()
    test_cluster_positions_empty_projection_returns_empty_list()
    test_deskew_straightens_rotated_horizontal_lines()
    test_preprocess_for_ocr_returns_grayscale_image_same_size()
    test_ocr_cell_numeric_config_includes_whitelist()
    test_ocr_cell_strips_border_noise_characters()
    test_flag_arithmetic_mismatches_flags_incorrect_printed_supply()
    test_flag_arithmetic_mismatches_prefers_weight_over_qty()
    test_flag_arithmetic_mismatches_skips_rows_missing_data()
    test_render_page_images_returns_one_png_per_page()
    test_recover_missing_name_column_fills_structurally_missing_cell()
    test_recover_missing_name_column_leaves_existing_cells_untouched()
    test_recover_missing_name_column_skips_when_no_other_cells_to_bound_region()
    test_recover_missing_name_column_skips_when_crop_returns_no_text()
    test_parse_pdf_items_normal_table_case()
    test_parse_pdf_items_hierarchical_case()
    test_parse_pdf_items_duplicate_header_case()
    test_parse_pdf_items_no_table_fallback_case()
    test_parse_pdf_items_scanned_pdf_uses_ocr_for_company()
    test_parse_pdf_items_scanned_pdf_recovers_item_name_and_spec()
    test_parse_pdf_items_scanned_pdf_grid_path_recovers_qty_weight_and_price()
    test_parse_pdf_items_scanned_pdf_degrades_gracefully_without_tesseract()
    test_parse_pdf_items_recovers_borderless_name_column_with_english_headers()
    test_extract_company_name_various_samples()
    test_extract_company_name_excludes_our_own_company()
    test_extract_title_various_samples()
    test_extract_title_handles_korean_hanja_and_english_labels()
    test_extract_title_truncates_at_trailing_contact_info()
    test_extract_title_does_not_duplicate_existing_case_suffix()
    test_detect_field_order_follows_left_to_right_column_index()
    test_detect_field_order_returns_none_without_mapping()
    test_weight_is_recognized_natively_without_extra_synonyms()
    test_map_table_columns_recognizes_custom_synonym()
    test_extract_items_from_table_passes_through_custom_column()
    test_parse_pdf_items_without_extra_fields_is_unaffected()
    test_parse_pdf_items_extra_fields_does_not_break_scanned_pdf_pipeline()
    print("ALL PASSED")
