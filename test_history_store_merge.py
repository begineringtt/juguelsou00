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


if __name__ == "__main__":
    test_merge_read_seed_appends_new_values_only()
    print("ALL PASSED")
