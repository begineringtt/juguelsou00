import io
import os
import shutil

import app as app_module
import column_settings


def _use_temp_data_dir():
    original_data_dir = column_settings.DATA_DIR
    original_path = column_settings.COLUMN_SETTINGS_PATH
    temp_dir = os.path.join(os.path.dirname(__file__), "_test_data_route")
    if os.path.isdir(temp_dir):
        shutil.rmtree(temp_dir)
    column_settings.DATA_DIR = temp_dir
    column_settings.COLUMN_SETTINGS_PATH = os.path.join(temp_dir, "column_settings.json")

    def _restore():
        column_settings.DATA_DIR = original_data_dir
        column_settings.COLUMN_SETTINGS_PATH = original_path
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)

    return _restore


def test_get_column_settings_returns_defaults():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.get("/column_settings")
        assert resp.status_code == 200
        body = resp.get_json()
        assert [c["key"] for c in body["columns"]] == ["spec", "unit", "qty", "price"]
    finally:
        restore()
    print("OK: test_get_column_settings_returns_defaults")


def test_add_column_route_then_it_appears_in_get():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.post("/column_settings/add", data={"label": "중량"})
        assert resp.status_code == 200
        added = resp.get_json()["column"]
        assert added["label"] == "중량"

        resp2 = client.get("/column_settings")
        assert added["key"] in [c["key"] for c in resp2.get_json()["columns"]]
    finally:
        restore()
    print("OK: test_add_column_route_then_it_appears_in_get")


def test_add_column_route_rejects_blank_label():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.post("/column_settings/add", data={"label": "  "})
        assert resp.status_code == 400
    finally:
        restore()
    print("OK: test_add_column_route_rejects_blank_label")


def test_save_column_settings_route_reorders():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        columns = column_settings.load_columns()
        reordered = list(reversed(columns))
        resp = client.post("/column_settings", json={"columns": reordered})
        assert resp.status_code == 200
        assert [c["key"] for c in column_settings.load_columns()] == ["price", "qty", "unit", "spec"]
    finally:
        restore()
    print("OK: test_save_column_settings_route_reorders")


def test_delete_column_route_rejects_builtin():
    restore = _use_temp_data_dir()
    try:
        client = app_module.app.test_client()
        resp = client.post("/column_settings/delete", data={"key": "unit"})
        assert resp.status_code == 400
    finally:
        restore()
    print("OK: test_delete_column_route_rejects_builtin")


def test_parse_pdf_route_passes_enabled_custom_labels_as_extra_fields():
    # column_settings에 커스텀 열을 추가해두면 /parse_pdf가 에러 없이 그 필드를
    # extra_fields로 넘긴 채로 정상 응답해야 한다 (값 인식 여부는 이 테스트의 범위가 아님).
    restore = _use_temp_data_dir()
    try:
        column_settings.add_custom_column("중량")
        client = app_module.app.test_client()

        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "품명 규격 단위 수량 단가")
        pdf_bytes = doc.tobytes()
        doc.close()

        data = {"file": (io.BytesIO(pdf_bytes), "quote.pdf")}
        resp = client.post("/parse_pdf", data=data, content_type="multipart/form-data")
        assert resp.status_code == 200
    finally:
        restore()
    print("OK: test_parse_pdf_route_passes_enabled_custom_labels_as_extra_fields")


if __name__ == "__main__":
    test_get_column_settings_returns_defaults()
    test_add_column_route_then_it_appears_in_get()
    test_add_column_route_rejects_blank_label()
    test_save_column_settings_route_reorders()
    test_delete_column_route_rejects_builtin()
    test_parse_pdf_route_passes_enabled_custom_labels_as_extra_fields()
    print("ALL PASSED")
