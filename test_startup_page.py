import os

import app as app_module


def test_startup_path_defaults_to_single_doc_screen():
    # 원래(예전) 실행.bat 은 아무 환경변수 없이 python app.py 만 돌리므로, 기본값은
    # 단독 생성 화면(/)이어야 한다.
    os.environ.pop("GP_OPEN_PAGE", None)
    assert app_module._startup_path() == "/"
    print("OK: test_startup_path_defaults_to_single_doc_screen")


def test_startup_path_opens_batch_screen_when_requested():
    # 견적서자동정리_실행.bat 은 GP_OPEN_PAGE=batch 를 설정해서 배치 화면을 연다.
    os.environ["GP_OPEN_PAGE"] = "batch"
    try:
        assert app_module._startup_path() == "/batch"
    finally:
        os.environ.pop("GP_OPEN_PAGE", None)
    print("OK: test_startup_path_opens_batch_screen_when_requested")


if __name__ == "__main__":
    test_startup_path_defaults_to_single_doc_screen()
    test_startup_path_opens_batch_screen_when_requested()
    print("ALL PASSED")
