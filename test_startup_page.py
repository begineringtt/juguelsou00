import os

import app as app_module


def test_startup_path_defaults_to_single_doc_screen():
    # 원래(예전) 실행.bat 은 아무 환경변수 없이 python app.py 만 돌리므로, 기본값은
    # 단독 생성 화면(/)이어야 한다.
    os.environ.pop("GP_OPEN_PAGE", None)
    assert app_module._startup_path() == "/"
    print("OK: test_startup_path_defaults_to_single_doc_screen")


def test_server_runs_threaded_so_one_slow_request_does_not_block_others():
    # 서버가 single-threaded 였을 때는, 사진 견적서 OCR처럼 느린 요청 하나가
    # 처리되는 동안 다른 화면(단독 생성 화면의 PDF 업로드 등)의 요청이 전부 막혀
    # "Failed to fetch"로 실패했다. threaded=True 로 동시 요청을 처리해야 한다.
    assert app_module._RUN_KWARGS.get("threaded") is True
    print("OK: test_server_runs_threaded_so_one_slow_request_does_not_block_others")


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
    test_server_runs_threaded_so_one_slow_request_does_not_block_others()
    test_startup_path_opens_batch_screen_when_requested()
    print("ALL PASSED")
