import os
import shutil
import tempfile

import openpyxl

from read_seed import scan_read_folder


def _build_fixture_workbook(path):
    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "sheet1"
    ws1["A9"] = "업체명"
    ws1["D9"] = "주식회사 신안그린테크"
    ws1["L11"] = "청 구 인"
    ws1["O11"] = "김용직 주임연구원"
    ws1["A12"] = "내  용"
    ws1["D12"] = "고효율 과제 환경제어 자재 구매의 건"
    ws1["A13"] = "상세내용"
    ws1["B14"] = "해당 연구개발 과제 수행을 위한 자재를 구매 하오니 결재 승인 요청드립니다."
    ws1["B16"] = "중앙행정기관 : 농림축산식품부"
    ws1["B17"] = "전문기관 : 농림식품기술기획평가원"
    ws1["B18"] = "과제명 : 고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발"
    ws1["B20"] = "연구재료비 집행의 건 (연구개발계획서 상 계상되어 있는 건임)"

    ws2 = wb.create_sheet("sheet2")
    ws2["A9"] = "업체명"
    ws2["D9"] = "(주)아이온이엔지"
    ws2["N11"] = "청 구 인"
    ws2["Q11"] = "이배훈 책임연구원"
    ws2["A12"] = "내  용"
    ws2["D12"] = "온실용 환경제어 계측 자재 구매 진행의 건"
    ws2["A13"] = "상세내용"
    ws2["C14"] = "해당 연구개발 수행을 위한 온실용 환경제어 계측 자재를 구매하고자 하오니 결재 승인 요청드립니다."
    ws2["B16"] = "중앙행정기관 : 농림축산식품부"
    ws2["B17"] = "전문기관 : 농림식품기술기획평가원"
    ws2["B18"] = "과제명 : 수확 후 전 과정 무인 자동화 시스템 개발 및 실증"
    ws2["B20"] = "연구재료비 집행의 건 (연구개발계획서 상 계상되어 있는 건임)"

    ws3 = wb.create_sheet("제품등")
    ws3["A1"] = "관련 없는 시트"

    wb.save(path)


def _build_corrupted_file(path):
    with open(path, "wb") as f:
        f.write(b"not a real xlsx file")


def test_scan_read_folder():
    tmp_dir = tempfile.mkdtemp()
    try:
        _build_fixture_workbook(os.path.join(tmp_dir, "fixture_a.xlsx"))

        skip_wb = openpyxl.Workbook()
        skip_wb.active["A9"] = "업체명"
        skip_wb.active["D9"] = "UNIQUE_SKIP_COMPANY_XYZ"
        skip_wb.save(os.path.join(tmp_dir, "~$fixture_a.xlsx"))

        _build_corrupted_file(os.path.join(tmp_dir, "broken.xlsx"))

        result = scan_read_folder(tmp_dir)

        assert result["history"]["company"] == ["주식회사 신안그린테크", "(주)아이온이엔지"]
        assert result["history"]["requester"] == ["김용직 주임연구원", "이배훈 책임연구원"]
        assert result["history"]["title"] == [
            "고효율 과제 환경제어 자재 구매의 건",
            "온실용 환경제어 계측 자재 구매 진행의 건",
        ]
        assert result["history"]["detail"] == [
            "해당 연구개발 과제 수행을 위한 자재를 구매 하오니 결재 승인 요청드립니다.",
            "해당 연구개발 수행을 위한 온실용 환경제어 계측 자재를 구매하고자 하오니 결재 승인 요청드립니다.",
        ]
        assert result["history"]["execution_note"] == [
            "연구재료비 집행의 건 (연구개발계획서 상 계상되어 있는 건임)"
        ]
        assert "UNIQUE_SKIP_COMPANY_XYZ" not in result["history"]["company"]

        assert result["projects"] == [
            {
                "agency": "농림축산식품부",
                "org": "농림식품기술기획평가원",
                "project_name": "고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발",
            },
            {
                "agency": "농림축산식품부",
                "org": "농림식품기술기획평가원",
                "project_name": "수확 후 전 과정 무인 자동화 시스템 개발 및 실증",
            },
        ]
        print("OK: test_scan_read_folder")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_scan_read_folder()
    print("ALL PASSED")
