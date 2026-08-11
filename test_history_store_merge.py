import json
import os
import shutil
import tempfile

import history_store


def test_merge_read_seed_appends_new_values_only():
    tmp_dir = tempfile.mkdtemp()
    original_history_path = history_store.HISTORY_PATH
    original_projects_path = history_store.PROJECTS_PATH
    try:
        history_store.HISTORY_PATH = os.path.join(tmp_dir, "history.json")
        history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")

        with open(history_store.HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump({"company": ["기존업체"], "requester": [], "title": [],
                       "detail": [], "execution_note": [], "department": []}, f)
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([{"agency": "A부처", "org": "A기관", "project_name": "기존과제"}], f)

        seed = {
            "history": {
                "company": ["기존업체", "신규업체"],
                "requester": ["신규연구원"],
                "title": [],
                "detail": [],
                "execution_note": [],
            },
            "projects": [
                {"agency": "A부처", "org": "A기관", "project_name": "기존과제"},
                {"agency": "B부처", "org": "B기관", "project_name": "신규과제"},
            ],
        }

        summary = history_store.merge_read_seed(seed)
        assert summary == {"history_added": 2, "projects_added": 1}

        with open(history_store.HISTORY_PATH, "r", encoding="utf-8") as f:
            saved_history = json.load(f)
        assert saved_history["company"] == ["기존업체", "신규업체"]
        assert saved_history["requester"] == ["신규연구원"]

        with open(history_store.PROJECTS_PATH, "r", encoding="utf-8") as f:
            saved_projects = json.load(f)
        assert [p["project_name"] for p in saved_projects] == ["기존과제", "신규과제"]

        # 같은 seed를 다시 병합해도 더 늘어나지 않아야 한다 (idempotent)
        summary2 = history_store.merge_read_seed(seed)
        assert summary2 == {"history_added": 0, "projects_added": 0}

        print("OK: test_merge_read_seed_appends_new_values_only")
    finally:
        history_store.HISTORY_PATH = original_history_path
        history_store.PROJECTS_PATH = original_projects_path
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_record_generation_preserves_existing_custom_label():
    tmp_dir = tempfile.mkdtemp()
    original_history_path = history_store.HISTORY_PATH
    original_projects_path = history_store.PROJECTS_PATH
    try:
        history_store.HISTORY_PATH = os.path.join(tmp_dir, "history.json")
        history_store.PROJECTS_PATH = os.path.join(tmp_dir, "projects.json")
        with open(history_store.PROJECTS_PATH, "w", encoding="utf-8") as f:
            json.dump([], f)

        history_store.add_project(
            agency="A부처", org="A기관", project_name="아주 긴 전체 과제명 예시", label="축약명",
        )
        assert history_store.effective_label(history_store.load_projects()[0]) == "축약명"

        # "+ 새 과제 추가"로 축약명을 지정해 둔 과제로 실제 지출결의서를 생성하면,
        # 폼에 축약명 입력칸이 없어서 record_generation이 label 없는 새 dict로
        # 덮어써 버리는 버그가 있었다. 생성 후에도 축약명이 남아있어야 한다.
        history_store.record_generation({
            "agency": "A부처", "org": "A기관", "project_name": "아주 긴 전체 과제명 예시",
            "company": "업체", "title": "제목", "detail": "상세", "execution_note": "집행문구",
        })

        reloaded = history_store.load_projects()
        assert len(reloaded) == 1
        assert reloaded[0].get("label") == "축약명"
        assert history_store.effective_label(reloaded[0]) == "축약명"
        print("OK: test_record_generation_preserves_existing_custom_label")
    finally:
        history_store.HISTORY_PATH = original_history_path
        history_store.PROJECTS_PATH = original_projects_path
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_merge_read_seed_appends_new_values_only()
    test_record_generation_preserves_existing_custom_label()
    print("ALL PASSED")
