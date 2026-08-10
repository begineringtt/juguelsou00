import base64
import os

import fitz

from pdf_item_parser import (
    normalize_header, match_field, match_field_fuzzy, parse_number,
    find_header_row, score_table, map_table_columns, extract_items_from_table,
    resolve_duplicate_price_columns, clean_item_rows, apply_hierarchical_prefix,
    extract_paragraph_fallback, render_page_images, parse_pdf_items,
    extract_company_name, extract_title,
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
    assert match_field_fuzzy("ㅇ. 공 급 가 액") is None
    assert match_field_fuzzy("ㅇ. 부 가 세") is None
    print("OK: test_match_field_fuzzy_matches_substring_with_bullet_prefix")


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
    assert score == 5
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
    assert score == 5
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
    assert result["title"] == "환경제어 계측 자재 대전"
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
        "2. 견적서.pdf": "온실복합환경계측 자재",
        "견적서_일신_북미.pdf": "폴리카보네이트 복층판",
        "대금청구서-엽채류동 modbusTCP 작업 (2).pdf": "당진 K-Farm 엽채류동 modbusTCP 작업",
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
    assert extract_title("물품명 : 온실복합환경계측 자재") == "온실복합환경계측 자재"
    assert extract_title("見 積 名 : 환경제어 계측 자재") == "환경제어 계측 자재"
    assert extract_title("SUBJECT: Greenhouse control materials") == "Greenhouse control materials"
    assert extract_title("공사명/품명 규격 수량 단위 단가 금액 비 고") is None
    assert extract_title("DESCRIPTION SIZE Q'TY UNIT UNIT PRICE AMOUNT REMARK") is None
    print("OK: test_extract_title_handles_korean_hanja_and_english_labels")


def test_extract_title_truncates_at_trailing_contact_info():
    text = "내 용 : 당진 K-Farm 엽채류동 modbusTCP 작업 연락처 : (T)042-631-2204 (F)042-639-2204"
    assert extract_title(text) == "당진 K-Farm 엽채류동 modbusTCP 작업"
    print("OK: test_extract_title_truncates_at_trailing_contact_info")


if __name__ == "__main__":
    test_normalize_header_strips_whitespace_and_uppercases()
    test_match_field_exact_single_line()
    test_match_field_multiline_header_checks_each_line()
    test_match_field_fuzzy_matches_substring_with_bullet_prefix()
    test_match_field_recognizes_description_as_name()
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
    test_render_page_images_returns_one_png_per_page()
    test_parse_pdf_items_normal_table_case()
    test_parse_pdf_items_hierarchical_case()
    test_parse_pdf_items_duplicate_header_case()
    test_parse_pdf_items_no_table_fallback_case()
    test_extract_company_name_various_samples()
    test_extract_company_name_excludes_our_own_company()
    test_extract_title_various_samples()
    test_extract_title_handles_korean_hanja_and_english_labels()
    test_extract_title_truncates_at_trailing_contact_info()
    print("ALL PASSED")
