import app as app_module


def test_index_shows_refresh_button():
    client = app_module.app.test_client()
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert "refreshReadSeedBtn" in html
    assert "read 폴더에서 최신 이력 불러오기" in html
    print("OK: test_index_shows_refresh_button")


def test_index_shows_added_message_when_refreshed():
    client = app_module.app.test_client()
    resp = client.get("/?refreshed=1&added=4")
    html = resp.get_data(as_text=True)
    assert "새 값 4개를 반영했습니다" in html
    print("OK: test_index_shows_added_message_when_refreshed")


def test_index_shows_no_new_values_message():
    client = app_module.app.test_client()
    resp = client.get("/?refreshed=1&added=0")
    html = resp.get_data(as_text=True)
    assert "새로 추가된 값이 없습니다" in html
    print("OK: test_index_shows_no_new_values_message")


def test_index_hides_banner_when_not_refreshed():
    client = app_module.app.test_client()
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert "read 폴더에서 새 값" not in html
    assert "새로 추가된 값이 없습니다" not in html
    print("OK: test_index_hides_banner_when_not_refreshed")


if __name__ == "__main__":
    test_index_shows_refresh_button()
    test_index_shows_added_message_when_refreshed()
    test_index_shows_no_new_values_message()
    test_index_hides_banner_when_not_refreshed()
    print("ALL PASSED")
