from pdf_item_parser import (
    normalize_header, match_field, match_field_fuzzy, parse_number,
    find_header_row, score_table, map_table_columns, extract_items_from_table,
    resolve_duplicate_price_columns, clean_item_rows, apply_hierarchical_prefix,
    extract_paragraph_fallback,
)


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


if __name__ == "__main__":
    test_normalize_header_strips_whitespace_and_uppercases()
    test_match_field_exact_single_line()
    test_match_field_multiline_header_checks_each_line()
    test_match_field_fuzzy_matches_substring_with_bullet_prefix()
    test_parse_number_handles_currency_and_stray_spaces()
    test_find_header_row_at_index_zero()
    test_find_header_row_scans_past_summary_row()
    test_score_table_counts_matched_fields()
    test_map_table_columns_basic()
    test_map_table_columns_finds_header_not_at_row_zero()
    test_map_table_columns_detects_duplicate_price_header()
    test_map_table_columns_returns_none_without_name_column()
    test_map_table_columns_returns_none_without_qty_or_price()
    test_extract_items_from_table_basic()
    test_extract_items_from_table_keeps_both_duplicate_price_columns()
    test_extract_items_from_table_skips_rows_without_name()
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
    print("ALL PASSED")
