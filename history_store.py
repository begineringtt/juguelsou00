"""이전에 생성했던 값들을 기억해두는 간단한 로컬 저장소.

- history.json : 업체명/청구부서/청구인/내용/상세내용/집행문구 처럼 자유 입력 텍스트의
  최근 사용 이력을 필드별로 저장한다. (드롭다운 + 직접 입력 겸용의 근거 데이터)
- projects.json : 과제 선택 시 중앙행정기관/전문기관/과제명을 한 번에 채워주기 위한
  프리셋 목록. 새 조합으로 생성하면 자동으로 추가/갱신된다.
"""

import json
import os

from paths import app_dir

BASE_DIR = app_dir()
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
        "project_name": "고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발",
    },
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "수확 후 전 과정 무인 자동화 시스템 개발 및 실증",
    },
    {
        "agency": "과학기술정보통신부",
        "org": "정보통신기획평가원",
        "project_name": "농축산시설 탄소 배출량 통합관리를 위한 디지털 트윈 플랫폼 기술 개발",
    },
    {
        "agency": "농림축산식품부",
        "org": "(재)스마트팜연구개발사업단",
        "project_name": "무인 자율형 K-Farm 저온성 작물 데모온실 구축 및 검증",
    },
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "북미 북동부 환경 적응 및 특약용 작물 재배용 수직농장 모델 개발",
    },
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "인건비 절감 및 생산량 극대화를 위한 심화작업 자동화 수직농장 모델 개발",
    },
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "중동 등 수출대상국가에 적합한 시설자재 개발 및 현지 실증",
    },
    {
        "agency": "농림축산식품부",
        "org": "농림식품기술기획평가원",
        "project_name": "무인 자율형 K-Farm 고온성 작물 데모온실 구축 및 검증",
    },
    {
        "agency": "농림축산식품부",
        "org": "(재)스마트팜연구개발사업단",
        "project_name": "시설 과채류 작물별 생리해석 및 근권부 정밀제어를 위한 지능형 의사결정 시스템 상용화",
    },
    {
        "agency": "산업통상자원부",
        "org": "한국산업기술기획평가원",
        "project_name": "수직농장 유연생산을 위한 자율 농수작업 로봇기술 개발",
    },
]

# 과제 선택 드롭다운에 표시할 축약명. 실제 문서에 들어가는 과제명(정식 명칭)은
# project_name 필드 그대로 유지하고, 목록에서 고르기 쉽도록 표시 텍스트만 축약한다.
# 스캔해온 과제명은 가운뎃점 표기 차이 등 이문(異文)이 섞여 있어 완전 일치 대신
# 각 과제를 구분 짓는 키워드로 매칭한다. (순서대로 첫 매치를 사용)
PROJECT_LABEL_KEYWORDS = [
    ("수확", "수확후"),
    ("고효율", "고효율"),
    ("탄소", "탄소"),
    ("저온성", "저온성"),
    ("고온성", "고온성"),
    ("북미", "북미"),
    ("인건비", "자동화"),
    ("중동", "중동(IR)"),
    ("근권부", "근권부"),
    ("로봇", "로봇"),
]


def short_label(project_name):
    for keyword, label in PROJECT_LABEL_KEYWORDS:
        if keyword in project_name:
            return label
    return project_name


def effective_label(project):
    """저장된 label(사용자가 직접 지정한 축약명)이 있으면 그것을, 없으면 키워드 매칭 결과를 쓴다."""
    return (project.get("label") or "").strip() or short_label(project.get("project_name", ""))


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


def _dedupe_by_label(projects):
    """같은 축약명으로 매칭되는 과제(표기만 다른 중복)는 먼저 나온 것만 남긴다."""
    seen_labels = set()
    deduped = []
    for p in projects:
        label = effective_label(p)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        deduped.append(p)
    return deduped


def load_projects():
    projects = _load_json(PROJECTS_PATH, None)
    if projects is None:
        projects = list(DEFAULT_PROJECTS)
        _save_json(PROJECTS_PATH, projects)
    deduped = _dedupe_by_label(projects)
    if len(deduped) != len(projects):
        _save_json(PROJECTS_PATH, deduped)
    return deduped


def _build_project_entry(agency, org, project_name, label=None):
    project_name = (project_name or "").strip()
    if not project_name:
        raise ValueError("project_name is required")
    entry = {"agency": (agency or "").strip(), "org": (org or "").strip(), "project_name": project_name}
    label = (label or "").strip()
    if label:
        entry["label"] = label
    return entry


def _upsert_project(entry, exclude_name=None):
    """entry를 맨 앞에 추가한다. 같은 축약명으로 매칭되는 기존 과제나 exclude_name에
    해당하는 과제(수정 대상 원본)가 있으면 제거해서 드롭다운에 중복이 남지 않게 한다.
    """
    new_label = effective_label(entry)
    projects = [
        p
        for p in load_projects()
        if p.get("project_name") != exclude_name and effective_label(p) != new_label
    ]
    projects.insert(0, entry)
    projects = projects[:MAX_PROJECTS]
    _save_json(PROJECTS_PATH, projects)
    return entry


def add_project(agency, org, project_name, label=None):
    """과제 정보 영역에서 사용자가 직접 새 과제를 추가할 때 호출한다."""
    entry = _build_project_entry(agency, org, project_name, label)
    return _upsert_project(entry)


def update_project(original_name, agency, org, project_name, label=None):
    """기존 과제(project_name == original_name)를 새 내용으로 교체한다."""
    entry = _build_project_entry(agency, org, project_name, label)
    return _upsert_project(entry, exclude_name=original_name)


def delete_project(project_name):
    """project_name과 일치하는 과제를 목록에서 제거한다. 제거됐으면 True를 반환한다."""
    projects = load_projects()
    remaining = [p for p in projects if p.get("project_name") != project_name]
    if len(remaining) == len(projects):
        return False
    _save_json(PROJECTS_PATH, remaining)
    return True


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


def merge_read_seed(seed):
    """read_seed.scan_read_folder()의 결과를 기존 이력/과제 프리셋에 중복 없이 병합한다."""
    hist = load_history()
    added_history = 0
    for field in HISTORY_FIELDS:
        new_values = seed.get("history", {}).get(field, [])
        existing = set(hist.get(field, []))
        for value in new_values:
            if value not in existing:
                hist.setdefault(field, []).append(value)
                existing.add(value)
                added_history += 1
    _save_json(HISTORY_PATH, hist)

    projects = load_projects()
    existing_names = {p.get("project_name") for p in projects}
    added_projects = 0
    for p in seed.get("projects", []):
        name = p.get("project_name")
        if name and name not in existing_names:
            projects.append(p)
            existing_names.add(name)
            added_projects += 1
    _save_json(PROJECTS_PATH, projects)

    return {"history_added": added_history, "projects_added": added_projects}
