"""budget_check.py 단위 테스트.

"연구비 소진 계획.xlsx"(과제x업체 계획 금액)와 "01. 지출결의서_전체과제_통합(양식).xlsx"
(과제별 마스터 양식, 시트 목록만 참조)를 실제 setting_03 폴더 현황
(checklist_sync.scan_status)/처리이력 로그와 대조해, 아직 안 만든 (과제,업체)와
계획 대비 금액이 다른 건을 찾아낸다.
"""

import os
import tempfile
import unittest

import openpyxl

import budget_check


class ResolveFolderTest(unittest.TestCase):
    def test_passthrough_for_direct_matches(self):
        self.assertEqual(budget_check.resolve_folder("자동화"), "자동화")
        self.assertEqual(budget_check.resolve_folder("로봇"), "로봇")
        self.assertEqual(budget_check.resolve_folder("탄소"), "탄소")

    def test_uses_folder_router_alias_for_substring_match(self):
        # folder_router.CATEGORY_TO_FOLDER 에 "중동" -> "IR" 별칭이 이미 있고,
        # "중동IR" 은 "중동"을 부분 문자열로 포함하므로 그 별칭을 재사용해야 한다.
        self.assertEqual(budget_check.resolve_folder("중동IR"), "IR")

    def test_uses_local_alias_for_ai_projects(self):
        # 연구비 소진 계획.xlsx 의 "AI(1년)"/"AI(1.5년)" 표기는 실제 폴더명과
        # 전혀 다르게 지어져 있어(AI(1y)그린CS / AI(1.5y)메타파머스) 앱 전역
        # CATEGORY_TO_FOLDER 에는 없는, budget_check 전용 별칭이 필요하다.
        self.assertEqual(budget_check.resolve_folder("AI(1년)"), "AI(1y)그린CS")
        self.assertEqual(budget_check.resolve_folder("AI(1.5년)"), "AI(1.5y)메타파머스")


def _write_plan_workbook(path):
    """연구비 소진 계획.xlsx 의 실제 구조(과제별 계획/실제 2행 블록, 업체는 열
    헤더, D열부터 시작)를 그대로 흉내낸 작은 합성 워크북을 만든다."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "결제금액 계획"
    ws["D1"] = "태광테크"
    ws["E1"] = "부강기업"
    ws["D2"] = "PVC 사출"
    ws["E2"] = "케이싱"
    ws["B3"] = "자동화"
    ws["C3"] = "계획"
    ws["D3"] = 2000000
    ws["E3"] = 3000000
    ws["C4"] = "실제"
    ws["B5"] = "고효율"
    ws["C5"] = "계획"
    ws["E5"] = 2000000  # 태광테크 칸은 비어 있음(계획 없음) -> 제외되어야 함
    ws["C6"] = "실제"
    # 실제 파일 꼬리의 소계/오차금액 행은 프로젝트가 아니므로 제외돼야 한다.
    ws["B7"] = "소계"
    ws["C7"] = "계획"
    ws["D7"] = 5000000
    wb.save(path)


class LoadPlanTest(unittest.TestCase):
    def test_reads_planned_amounts_per_project_and_company(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            _write_plan_workbook(path)
            rows = budget_check.load_plan(path)

        pairs = {(r["project"], r["company"]): r["planned_amount"] for r in rows}
        self.assertEqual(pairs[("자동화", "태광테크")], 2000000)
        self.assertEqual(pairs[("자동화", "부강기업")], 3000000)
        self.assertEqual(pairs[("고효율", "부강기업")], 2000000)
        self.assertNotIn(("고효율", "태광테크"), pairs)

    def test_excludes_non_project_summary_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            _write_plan_workbook(path)
            rows = budget_check.load_plan(path)

        projects = {r["project"] for r in rows}
        self.assertNotIn("소계", projects)

    def test_each_row_includes_resolved_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            _write_plan_workbook(path)
            rows = budget_check.load_plan(path)

        row = next(r for r in rows if r["project"] == "자동화" and r["company"] == "태광테크")
        self.assertEqual(row["folder"], "자동화")


class LoadMasterProjectsTest(unittest.TestCase):
    def test_returns_sheet_names_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "01. 지출결의서_전체과제_통합(양식).xlsx")
            wb = openpyxl.Workbook()
            wb.active.title = "근권부"
            wb.create_sheet("수확후")
            wb.create_sheet("팁스")
            wb.save(path)

            projects = budget_check.load_master_projects(path)

        self.assertEqual(projects, ["근권부", "수확후", "팁스"])


class LoadActualTotalsTest(unittest.TestCase):
    def test_sums_total_amount_per_folder_and_company(self):
        import report_writer

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "처리이력_보고서.xlsx")
            report_writer.append_entry(path, {
                "category": "자동화", "company": "태광테크", "folder": "자동화/태광테크",
                "generated": ["지출결의서"], "attachments": [], "total_amount": 2000000,
                "item_count": 1, "source": "pdf-table", "note": "",
            })
            report_writer.append_entry(path, {
                "category": "자동화", "company": "태광테크", "folder": "자동화/태광테크",
                "generated": ["지출결의서"], "attachments": [], "total_amount": 500000,
                "item_count": 1, "source": "pdf-table", "note": "",
            })
            report_writer.append_entry(path, {
                "category": "자동화", "company": "부강기업", "folder": "자동화/부강기업",
                "generated": ["지출결의서"], "attachments": [], "total_amount": 3000000,
                "item_count": 1, "source": "pdf-table", "note": "",
            })

            totals = budget_check.load_actual_totals(path)

        self.assertEqual(totals[("자동화", "태광테크")], 2500000)
        self.assertEqual(totals[("자동화", "부강기업")], 3000000)

    def test_missing_file_returns_empty(self):
        totals = budget_check.load_actual_totals("존재하지_않는_파일.xlsx")
        self.assertEqual(totals, {})


class CheckProgressTest(unittest.TestCase):
    def _write_master(self, path, sheet_names):
        wb = openpyxl.Workbook()
        wb.active.title = sheet_names[0]
        for name in sheet_names[1:]:
            wb.create_sheet(name)
        wb.save(path)

    def test_reports_missing_pairs_amount_mismatches_and_project_coverage(self):
        import report_writer

        with tempfile.TemporaryDirectory() as tmp:
            # 태광테크: 지출결의서 있음(처리이력에도 남음, 금액이 계획과 다름)
            done_dir = os.path.join(tmp, "자동화", "2026.01.01 태광테크")
            os.makedirs(done_dir)
            with open(os.path.join(done_dir, "지출결의서_태광테크.xlsx"), "w") as f:
                f.write("dummy")

            # 부강기업: 계획은 있지만 폴더/문서가 전혀 없음 -> 누락
            os.makedirs(os.path.join(tmp, "자동화", "2026.01.02 부강기업"))

            report_path = os.path.join(tmp, "체크리스트", "처리이력_보고서.xlsx")
            os.makedirs(os.path.dirname(report_path))
            report_writer.append_entry(report_path, {
                "category": "자동화", "company": "태광테크", "folder": "자동화/태광테크",
                "generated": ["지출결의서"], "attachments": [], "total_amount": 2500000,
                "item_count": 1, "source": "pdf-table", "note": "",
            })

            plan_path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            _write_plan_workbook(plan_path)  # 자동화: 태광테크 2,000,000 / 부강기업 3,000,000

            master_path = os.path.join(tmp, "01. 지출결의서_전체과제_통합(양식).xlsx")
            self._write_master(master_path, ["자동화", "고효율"])

            result = budget_check.check_progress(
                tmp, plan_path=plan_path, master_path=master_path, report_path=report_path)

        missing = {(m["project"], m["company"]) for m in result["missing"]}
        self.assertIn(("자동화", "부강기업"), missing)
        self.assertNotIn(("자동화", "태광테크"), missing)
        self.assertEqual(result["missing_count"], len(result["missing"]))

        mismatch = next(m for m in result["mismatches"]
                         if m["project"] == "자동화" and m["company"] == "태광테크")
        self.assertEqual(mismatch["planned_amount"], 2000000)
        self.assertEqual(mismatch["actual_amount"], 2500000)
        self.assertEqual(mismatch["diff"], 500000)

        # 고효율은 계획에 금액이 없어 load_plan 자체가 건너뛰지만(태광테크 칸이
        # 비어 있음), 마스터 양식(01. 파일)에는 시트로 존재하고 실제 폴더에
        # 지출결의서가 하나도 없으므로 "문서가 아예 없는 과제"로 잡혀야 한다.
        self.assertIn("고효율 광원", result["projects_without_any_report"])
        self.assertNotIn("자동화", result["projects_without_any_report"])

    def test_reports_per_project_and_overall_completion_percentage(self):
        import report_writer

        with tempfile.TemporaryDirectory() as tmp:
            done_dir = os.path.join(tmp, "자동화", "2026.01.01 태광테크")
            os.makedirs(done_dir)
            with open(os.path.join(done_dir, "지출결의서_태광테크.xlsx"), "w") as f:
                f.write("dummy")
            os.makedirs(os.path.join(tmp, "자동화", "2026.01.02 부강기업"))

            report_path = os.path.join(tmp, "체크리스트", "처리이력_보고서.xlsx")
            os.makedirs(os.path.dirname(report_path))
            report_writer.append_entry(report_path, {
                "category": "자동화", "company": "태광테크", "folder": "자동화/태광테크",
                "generated": ["지출결의서"], "attachments": [], "total_amount": 2500000,
                "item_count": 1, "source": "pdf-table", "note": "",
            })

            plan_path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            _write_plan_workbook(plan_path)  # 자동화: 태광테크(완료)/부강기업(미완료), 고효율: 부강기업(미완료)

            master_path = os.path.join(tmp, "01. 지출결의서_전체과제_통합(양식).xlsx")
            self._write_master(master_path, ["자동화", "고효율"])

            result = budget_check.check_progress(
                tmp, plan_path=plan_path, master_path=master_path, report_path=report_path)

        by_project = {p["project"]: p for p in result["progress_by_project"]}
        self.assertEqual(by_project["자동화"], {"project": "자동화", "planned": 2, "done": 1, "percent": 50})
        self.assertEqual(by_project["고효율"], {"project": "고효율", "planned": 1, "done": 0, "percent": 0})

        self.assertEqual(result["overall_progress"], {"planned": 3, "done": 1, "percent": 33})


class ScaffoldFoldersTest(unittest.TestCase):
    def test_creates_folder_for_planned_company_with_no_existing_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            # _write_plan_workbook: 자동화(태광테크 2,000,000/부강기업 3,000,000),
            # 고효율(부강기업 2,000,000, "고효율 광원" 폴더로 해석됨)
            _write_plan_workbook(plan_path)

            result = budget_check.scaffold_folders(tmp, plan_path=plan_path)

            self.assertTrue(os.path.isdir(os.path.join(tmp, "자동화", "태광테크")))
            self.assertTrue(os.path.isdir(os.path.join(tmp, "자동화", "부강기업")))
            self.assertTrue(os.path.isdir(os.path.join(tmp, "고효율 광원", "부강기업")))
        created = {(c["folder"], c["company"]) for c in result["created"]}
        self.assertEqual(created, {
            ("자동화", "태광테크"), ("자동화", "부강기업"), ("고효율 광원", "부강기업"),
        })
        self.assertEqual(result["already_existed"], [])

    def test_does_not_duplicate_an_existing_similarly_named_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "자동화", "2026.01.01 태광테크"))
            plan_path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            _write_plan_workbook(plan_path)

            result = budget_check.scaffold_folders(tmp, plan_path=plan_path)

            # 이미 날짜가 붙은 업체 폴더가 있으면 새 폴더를 또 만들면 안 된다.
            self.assertFalse(os.path.isdir(os.path.join(tmp, "자동화", "태광테크")))
            entries = set(os.listdir(os.path.join(tmp, "자동화")))
            self.assertEqual(entries, {"2026.01.01 태광테크", "부강기업"})
        already = {(c["folder"], c["company"]) for c in result["already_existed"]}
        self.assertIn(("자동화", "태광테크"), already)
        created = {(c["folder"], c["company"]) for c in result["created"]}
        self.assertIn(("자동화", "부강기업"), created)
        self.assertNotIn(("자동화", "태광테크"), created)

    def test_creates_project_folder_itself_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = os.path.join(tmp, "연구비 소진 계획.xlsx")
            _write_plan_workbook(plan_path)

            budget_check.scaffold_folders(tmp, plan_path=plan_path)

            self.assertTrue(os.path.isdir(os.path.join(tmp, "자동화")))


if __name__ == "__main__":
    unittest.main()
