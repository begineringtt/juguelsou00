import json
import os
import shutil
import tempfile

import history_store
import pipeline


def test_project_for_category_finds_user_added_project():
    # "고온성"은 folder_router가 아는 유효한 카테고리라서 폴더 매핑 자체는 되지만,
    # 사용자가 실제 저장한 과제 정보(직접 추가/수정한 값)를 봐야 한다는 걸 검증한다.
    tmp_dir = tempfile.mkdtemp()
    original_projects_path = history_store.PROJECTS_PATH
    try:
        history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")
        history_store.add_project(
            agency="테스트부처", org="테스트기관",
            project_name="사용자가 새로 추가한 고온성 테스트 과제",
            label="고온성",
        )

        proj = pipeline.project_for_category("고온성")

        assert proj["agency"] == "테스트부처"
        assert proj["org"] == "테스트기관"
        assert proj["project_name"] == "사용자가 새로 추가한 고온성 테스트 과제"
        print("OK: test_project_for_category_finds_user_added_project")
    finally:
        history_store.PROJECTS_PATH = original_projects_path
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_project_for_category_still_resolves_builtin_category():
    tmp_dir = tempfile.mkdtemp()
    original_projects_path = history_store.PROJECTS_PATH
    try:
        history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")

        proj = pipeline.project_for_category("고온성")

        assert "고온성" in proj["project_name"]
        print("OK: test_project_for_category_still_resolves_builtin_category")
    finally:
        history_store.PROJECTS_PATH = original_projects_path
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_project_for_category_does_not_crash_on_a_custom_user_added_category():
    # 배치 화면에서 사용자가 새로 추가한 과제(예: "탄소", "로봇"처럼 folder_router의
    # 고정 매핑에 없는 라벨)를 골라도 배치 실행이 예외로 죽으면 안 된다.
    tmp_dir = tempfile.mkdtemp()
    original_projects_path = history_store.PROJECTS_PATH
    try:
        history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")
        history_store.add_project(
            agency="테스트부처", org="테스트기관",
            project_name="사용자가 새로 추가한 커스텀 과제",
            label="커스텀라벨",
        )

        proj = pipeline.project_for_category("커스텀라벨")

        assert proj["project_name"] == "사용자가 새로 추가한 커스텀 과제"
        print("OK: test_project_for_category_does_not_crash_on_a_custom_user_added_category")
    finally:
        history_store.PROJECTS_PATH = original_projects_path
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_project_for_category_finds_user_added_project()
    test_project_for_category_still_resolves_builtin_category()
    test_project_for_category_does_not_crash_on_a_custom_user_added_category()
    print("ALL PASSED")
