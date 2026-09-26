"""/batch, /batch_run 라우트 스모크 테스트.

실제 견적서 샘플이 있을 때만 /batch_run 을 돌리고, 없으면 GET 만 확인한다.
"""

import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import app as appmod
import history_store

SAMPLE = "/mnt/user-data/uploads/setting_03/고효율 광원/2026-09-20 유진철강/견적서.pdf"
CHECKLIST = "/mnt/user-data/uploads/setting_03/체크리스트/연구비 파일 업로드 체크용_26.09.09.xlsx"


class BatchRouteTest(unittest.TestCase):
    def setUp(self):
        self.client = appmod.app.test_client()

    def test_get_batch_page(self):
        r = self.client.get("/batch")
        self.assertEqual(r.status_code, 200)

    def test_batch_page_includes_open_folder_button(self):
        r = self.client.get("/batch")
        html = r.get_data(as_text=True)
        self.assertIn('id="openFolderBtn"', html)

    def test_batch_page_includes_budget_check_button(self):
        r = self.client.get("/batch")
        html = r.get_data(as_text=True)
        self.assertIn('id="budgetCheckBtn"', html)

    def test_batch_page_includes_attachment_match_panel(self):
        r = self.client.get("/batch")
        html = r.get_data(as_text=True)
        self.assertIn('id="attachmentMatchPanel"', html)
        self.assertIn('name="attachment_company_override"', html)
        self.assertIn('name="skip_auto_attachments"', html)

    def test_missing_fields_rejected(self):
        r = self.client.post("/batch_run", data={}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_parse_quote_route_recognizes_company_from_xlsx(self):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "공급자: 가나다전자㈜"
        ws.append(["품명", "수량", "단가"])
        ws.append(["테스트자재", 2, 1000])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        r = self.client.post(
            "/batch_parse_quote",
            data={"quote": (buf, "견적서.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIn("가나다전자", j.get("company") or "")

    def test_parse_quote_route_rejects_missing_file(self):
        r = self.client.post("/batch_parse_quote", data={}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_open_folder_opens_existing_directory(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            with mock.patch.object(appmod.os, "startfile", create=True) as startfile:
                r = self.client.post("/open_folder", data={"path": tmp_dir})
            self.assertEqual(r.status_code, 200)
            startfile.assert_called_once_with(tmp_dir)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_open_folder_rejects_missing_directory(self):
        r = self.client.post("/open_folder", data={"path": "존재하지_않는_경로_xyz"})
        self.assertEqual(r.status_code, 400)

    def test_budget_check_rejects_missing_setting03_root(self):
        r = self.client.post("/budget_check", data={"setting03_root": ""})
        self.assertEqual(r.status_code, 400)

    def test_budget_check_reports_missing_pairs_for_real_layout(self):
        import openpyxl
        import report_writer

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "자동화", "태광테크"))
            report_path = os.path.join(tmp, "체크리스트", "처리이력_보고서.xlsx")
            os.makedirs(os.path.dirname(report_path))
            report_writer.append_entry(report_path, {
                "category": "자동화", "company": "태광테크", "folder": "자동화/태광테크",
                "generated": [], "attachments": [], "total_amount": 1000,
                "item_count": 1, "source": "pdf-table", "note": "",
            })

            plan_wb = openpyxl.Workbook()
            plan_ws = plan_wb.active
            plan_ws.title = "결제금액 계획"
            plan_ws["D1"] = "태광테크"
            plan_ws["B3"] = "자동화"
            plan_ws["C3"] = "계획"
            plan_ws["D3"] = 2000000
            plan_wb.save(os.path.join(tmp, "연구비 소진 계획.xlsx"))

            master_wb = openpyxl.Workbook()
            master_wb.active.title = "자동화"
            master_wb.save(os.path.join(tmp, "01. 지출결의서_전체과제_통합(양식).xlsx"))

            r = self.client.post("/budget_check", data={"setting03_root": tmp})

        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        missing = {(m["project"], m["company"]) for m in j["missing"]}
        self.assertIn(("자동화", "태광테크"), missing)

    def test_parse_quote_route_reports_exact_attachment_match(self):
        import openpyxl
        tmp_dir = tempfile.mkdtemp()
        try:
            setting03_root = os.path.join(tmp_dir, "setting_03")
            repo_dir = os.path.join(setting03_root, "고온성", "가나다전자")
            os.makedirs(repo_dir)
            open(os.path.join(repo_dir, "통장사본.jpg"), "w").close()

            wb = openpyxl.Workbook()
            ws = wb.active
            ws["A1"] = "공급자: 가나다전자㈜"
            ws.append(["품명", "수량", "단가"])
            ws.append(["테스트자재", 2, 1000])
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            r = self.client.post(
                "/batch_parse_quote",
                data={"quote": (buf, "견적서.xlsx"), "setting03_root": setting03_root},
                content_type="multipart/form-data",
            )
            self.assertEqual(r.status_code, 200)
            j = r.get_json()
            self.assertEqual(j["attachment_match"]["type"], "exact")
            self.assertEqual(j["attachment_match"]["display"], "가나다전자")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_parse_quote_route_reports_fuzzy_attachment_candidates(self):
        import openpyxl
        tmp_dir = tempfile.mkdtemp()
        try:
            setting03_root = os.path.join(tmp_dir, "setting_03")
            repo_dir = os.path.join(setting03_root, "고온성", "가나다전자부품")
            os.makedirs(repo_dir)
            open(os.path.join(repo_dir, "통장사본.jpg"), "w").close()

            wb = openpyxl.Workbook()
            ws = wb.active
            ws["A1"] = "공급자: 가나다전자㈜"
            ws.append(["품명", "수량", "단가"])
            ws.append(["테스트자재", 2, 1000])
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            r = self.client.post(
                "/batch_parse_quote",
                data={"quote": (buf, "견적서.xlsx"), "setting03_root": setting03_root},
                content_type="multipart/form-data",
            )
            self.assertEqual(r.status_code, 200)
            j = r.get_json()
            self.assertEqual(j["attachment_match"]["type"], "fuzzy")
            candidates = j["attachment_match"]["candidates"]
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["display"], "가나다전자부품")
            self.assertTrue(candidates[0]["has_docs"]["통장사본"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_batch_run_uses_confirmed_attachment_override(self):
        import openpyxl
        tmp_dir = tempfile.mkdtemp()
        original_config_path = appmod._CONFIG_PATH
        try:
            # /batch_run은 "다음 실행 때 자동으로 채워주려고" setting03_root를
            # 앱 설정 파일에 저장한다 - 격리 안 하면 이 테스트가 실사용자의
            # 진짜 설정 파일을 임시 경로로 덮어써버린다.
            appmod._CONFIG_PATH = os.path.join(tmp_dir, "app_config.json")
            setting03_root = os.path.join(tmp_dir, "setting_03")
            os.makedirs(os.path.join(setting03_root, "고온성"))
            repo_dir = os.path.join(setting03_root, "고온성", "대한중공업")
            os.makedirs(repo_dir)
            open(os.path.join(repo_dir, "통장사본.jpg"), "w").close()

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["품명", "수량", "단가"])
            ws.append(["테스트자재", 2, 1000])
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)

            data = {
                "setting03_root": setting03_root, "category": "고온성", "company": "대한",
                "quote": (buf, "견적서.xlsx"),
                "attachment_company_override": "대한중공업",
                "dry_run": "1",
            }
            r = self.client.post("/batch_run", data=data, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 200)
            j = r.get_json()
            self.assertIn("통장사본", j["attachments_from_repo"])
        finally:
            appmod._CONFIG_PATH = original_config_path
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_batch_page_lists_user_saved_projects_not_fixed_categories(self):
        tmp_dir = tempfile.mkdtemp()
        original_projects_path = history_store.PROJECTS_PATH
        try:
            history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")
            history_store.add_project(
                agency="테스트부처", org="테스트기관",
                project_name="배치화면 카테고리 목록용 테스트 과제",
                label="배치테스트과제",
            )
            r = self.client.get("/batch")
            self.assertEqual(r.status_code, 200)
            self.assertIn("배치테스트과제", r.get_data(as_text=True))
        finally:
            history_store.PROJECTS_PATH = original_projects_path
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @unittest.skipUnless(os.path.isfile(SAMPLE) and os.path.isfile(CHECKLIST),
                         "실제 샘플/체크리스트 없음")
    def test_full_run_places_files(self):
        root = tempfile.mkdtemp(prefix="sb_route_")
        original_config_path = appmod._CONFIG_PATH
        try:
            appmod._CONFIG_PATH = os.path.join(root, "app_config.json")
            os.makedirs(os.path.join(root, "체크리스트"))
            os.makedirs(os.path.join(root, "고효율 광원", "2026-09-20 유진철강"))
            shutil.copy2(CHECKLIST, os.path.join(root, "체크리스트"))
            with open(SAMPLE, "rb") as fh:
                qbytes = fh.read()
            data = {
                "setting03_root": root, "category": "고효율", "company": "유진철강산업㈜",
                "inspector": "유찬희 책임연구원", "inspect_date": "2026-09-20",
                "quote": (io.BytesIO(qbytes), "견적서.pdf"),
            }
            r = self.client.post("/batch_run", data=data, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 200)
            j = r.get_json()
            self.assertEqual(j["item_count"], 1)
            self.assertEqual(j["total_supply"], 5043168)
            self.assertGreaterEqual(len(j["placed_files"]), 3)
            self.assertEqual(j["checklist"]["misses"], [])
        finally:
            appmod._CONFIG_PATH = original_config_path


if __name__ == "__main__":
    unittest.main(verbosity=2)
