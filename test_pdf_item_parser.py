from pdf_item_parser import normalize_header, match_field, match_field_fuzzy, parse_number


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


if __name__ == "__main__":
    test_normalize_header_strips_whitespace_and_uppercases()
    test_match_field_exact_single_line()
    test_match_field_multiline_header_checks_each_line()
    test_match_field_fuzzy_matches_substring_with_bullet_prefix()
    test_parse_number_handles_currency_and_stray_spaces()
    print("ALL PASSED")
