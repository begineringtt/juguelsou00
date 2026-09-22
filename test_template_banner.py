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


def test_index_links_to_batch_screen():
    # /batch 에는 "← 지출결의서 단독 생성 화면" 링크로 / 로 돌아올 수 있는데, /
    # 에는 반대로 /batch 로 가는 링크가 없어서 두 화면을 개별 도구로 쓰기 불편했다.
    client = app_module.app.test_client()
    resp = client.get("/")
    html = resp.get_data(as_text=True)
    assert 'href="/batch"' in html
    print("OK: test_index_links_to_batch_screen")


if __name__ == "__main__":
    test_index_shows_refresh_button()
    test_index_shows_added_message_when_refreshed()
    test_index_shows_no_new_values_message()
    test_index_hides_banner_when_not_refreshed()
    test_index_links_to_batch_screen()
    print("ALL PASSED")
