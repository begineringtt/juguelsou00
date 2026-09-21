"""/batch, /batch_run 라우트 스모크 테스트.

실제 견적서 샘플이 있을 때만 /batch_run 을 돌리고, 없으면 GET 만 확인한다.
"""

import io
import os
import shutil
import tempfile
import unittest

import app as appmod

SAMPLE = "/mnt/user-data/uploads/setting_03/고효율 광원/2026-09-20 유진철강/견적서.pdf"
CHECKLIST = "/mnt/user-data/uploads/setting_03/체크리스트/연구비 파일 업로드 체크용_26.09.09.xlsx"


class BatchRouteTest(unittest.TestCase):
    def setUp(self):
        self.client = appmod.app.test_client()

    def test_get_batch_page(self):
        r = self.client.get("/batch")
        self.assertEqual(r.status_code, 200)

    def test_missing_fields_rejected(self):
        r = self.client.post("/batch_run", data={}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    @unittest.skipUnless(os.path.isfile(SAMPLE) and os.path.isfile(CHECKLIST),
                         "실제 샘플/체크리스트 없음")
    def test_full_run_places_files(self):
        root = tempfile.mkdtemp(prefix="sb_route_")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
