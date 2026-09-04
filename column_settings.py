"""품목 표에 표시할 열(품명/공급가/부가세 제외) 구성을 저장하는 로컬 설정.

data/column_settings.json 에 순서가 있는 리스트로 저장한다. 리스트에 있는
순서가 화면 입력 표/엑셀 생성/PDF 인식 매칭에서 쓰는 열 순서다. 품목(name)은
항상 맨 앞, 공급가(supply)/부가세(vat)는 항상 맨 뒤 고정이라 이 목록에는
들어가지 않는다.
"""

import json
import os

from paths import app_dir
from pdf_item_parser import normalize_header

BASE_DIR = app_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")
COLUMN_SETTINGS_PATH = os.path.join(DATA_DIR, "column_settings.json")

DEFAULT_COLUMNS = [
    {"key": "spec", "label": "규격", "enabled": True, "builtin": True},
    {"key": "unit", "label": "단위", "enabled": True, "builtin": True},
    {"key": "qty", "label": "수량", "enabled": True, "builtin": True},
    {"key": "price", "label": "단가", "enabled": True, "builtin": True},
    {"key": "weight", "label": "중량", "enabled": True, "builtin": True},
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


def load_columns():
    data = _load_json(COLUMN_SETTINGS_PATH, None)
    if data is None:
        columns = [dict(c) for c in DEFAULT_COLUMNS]
        _save_json(COLUMN_SETTINGS_PATH, {"columns": columns})
        return columns
    return data.get("columns", [])


def save_columns(columns):
    _save_json(COLUMN_SETTINGS_PATH, {"columns": columns})


def _next_custom_key(columns):
    existing = {c["key"] for c in columns}
    n = 1
    while f"custom_{n}" in existing:
        n += 1
    return f"custom_{n}"


def add_custom_column(label):
    label = (label or "").strip()
    if not label:
        return None
    columns = load_columns()
    normalized = normalize_header(label)
    for c in columns:
        if normalize_header(c["label"]) == normalized:
            return c
    entry = {"key": _next_custom_key(columns), "label": label, "enabled": True, "builtin": False}
    columns.append(entry)
    save_columns(columns)
    return entry


def set_column_enabled(key, enabled):
    columns = load_columns()
    for c in columns:
        if c["key"] == key:
            c["enabled"] = bool(enabled)
    save_columns(columns)
    return columns


def delete_column(key):
    columns = load_columns()
    remaining = [c for c in columns if not (c["key"] == key and not c.get("builtin"))]
    if len(remaining) == len(columns):
        return False
    save_columns(remaining)
    return True
