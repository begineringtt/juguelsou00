import io

import fitz

import app as app_module


def _tiny_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "품명 규격 단위 수량 단가")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_parse_pdf_route_returns_json_with_expected_keys():
    client = app_module.app.test_client()
    data = {"file": (io.BytesIO(_tiny_pdf_bytes()), "quote.pdf")}
    resp = client.post("/parse_pdf", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body.keys()) == {"items", "page_images", "warnings"}
    assert isinstance(body["items"], list)
    assert len(body["page_images"]) == 1
    print("OK: test_parse_pdf_route_returns_json_with_expected_keys")


def test_parse_pdf_route_requires_file():
    client = app_module.app.test_client()
    resp = client.post("/parse_pdf", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    print("OK: test_parse_pdf_route_requires_file")


if __name__ == "__main__":
    test_parse_pdf_route_returns_json_with_expected_keys()
    test_parse_pdf_route_requires_file()
    print("ALL PASSED")
