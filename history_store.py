"""이전에 생성했던 값들을 기억해두는 간단한 로컬 저장소.

- history.json : 업체명/청구부서/청구인/내용/상세내용/집행문구 처럼 자유 입력 텍스트의
  최근 사용 이력을 필드별로 저장한다. (드롭다운 + 직접 입력 겸용의 근거 데이터)
- projects.json : 과제 선택 시 중앙행정기관/전문기관/과제명을 한 번에 채워주기 위한
  프리셋 목록. 새 조합으로 생성하면 자동으로 추가/갱신된다.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
PROJECTS_PATH = os.path.join(DATA_DIR, "projects.json")

HISTORY_FIELDS = ["company", "department", "requester", "title", "detail", "execution_note"]
MAX_HISTORY_PER_FIELD = 50
MAX_PROJECTS = 50

DEFAULT_PROJECTS = [
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "인건비 절감 및 생산량 극대화를 위한 심화작업 자동화 수직농장 모델 개발",
    },
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발",
    },
]


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path, data):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_history():
    hist = _load_json(HISTORY_PATH, {})
    for field in HISTORY_FIELDS:
        hist.setdefault(field, [])
    return hist


def load_projects():
    projects = _load_json(PROJECTS_PATH, None)
    if projects is None:
        projects = list(DEFAULT_PROJECTS)
        _save_json(PROJECTS_PATH, projects)
    return projects


def _move_to_front(items, value):
    items = [v for v in items if v != value]
    items.insert(0, value)
    return items[:MAX_HISTORY_PER_FIELD]


def record_generation(data):
    """지출결의서를 하나 생성할 때마다 호출해서 이력/과제 프리셋을 갱신한다."""
    hist = load_history()
    for field in HISTORY_FIELDS:
        value = (data.get(field) or "").strip()
        if value:
            hist[field] = _move_to_front(hist[field], value)
    _save_json(HISTORY_PATH, hist)

    project_name = (data.get("project_name") or "").strip()
    if project_name:
        projects = load_projects()
        projects = [p for p in projects if p.get("project_name") != project_name]
        projects.insert(
            0,
            {
                "agency": (data.get("agency") or "").strip(),
                "org": (data.get("org") or "").strip(),
                "project_name": project_name,
            },
        )
        _save_json(PROJECTS_PATH, projects[:MAX_PROJECTS])
