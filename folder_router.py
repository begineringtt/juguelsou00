"""과제 카테고리 -> setting_03 폴더 결정 + 업체 하위폴더 명명 규칙 학습.

핵심 규칙(사용자 확정):
  - 사용자가 과제 카테고리를 고른다.
  - "중동" 카테고리는 실제 폴더가 "IR" 이다. (절대 잊지 말 것 - 매핑에 고정)
  - 업체 하위폴더 이름은 각 카테고리 폴더의 기존 하위폴더 명명 규칙을 보고 만든다.
    카테고리마다 규칙이 다르다:
      · 고온성      : 업체명 그대로            (예: "그린공조시스템")
      · 고효율 광원 : "YYYY-MM-DD 업체" / "YYYY.MM.DD 업체"
      · 근권부      : "N차 업체"               (예: "10차 신안그린테크")
      · 팁스        : "N차_업체_품목"          (예: "1차_아이엘패널_판넬")
    -> 규칙을 하드코딩하지 않고, 실제 형제 폴더에서 자동 감지한다.
"""

import datetime
import os
import re


# 카테고리(사용자 선택 값) -> setting_03 하위 폴더명
CATEGORY_TO_FOLDER = {
    "자동화": "자동화",
    "고효율": "고효율 광원",
    "고효율 광원": "고효율 광원",
    "북미": "북미",
    "중동": "IR",          # ★ 중동 = IR 폴더
    "중동(IR)": "IR",
    "IR": "IR",
    "고온성": "고온성",
    "저온성": "저온성",
    "근권부": "근권부",
    "수확후": "수확후",
    "팁스": "팁스",
    "TIPS": "팁스",
}

# 화면 드롭다운에 보여줄 카테고리(대표 이름) 목록
CATEGORY_CHOICES = ["자동화", "고효율", "북미", "중동", "고온성", "저온성", "근권부", "수확후", "팁스"]


def folder_for_category(category):
    key = (category or "").strip()
    if key in CATEGORY_TO_FOLDER:
        return CATEGORY_TO_FOLDER[key]
    # 부분 일치(예: "중동 등 수출..." 같은 과제명)
    for k, v in CATEGORY_TO_FOLDER.items():
        if k and k in key:
            return v
    raise ValueError(f"알 수 없는 과제 카테고리입니다: {category!r}")


def category_root(setting03_root, category):
    return os.path.join(setting03_root, folder_for_category(category))


# ------------------------------------------------------------------ #
# 업체 하위폴더 명명 규칙 감지
# ------------------------------------------------------------------ #

_DATE_PREFIX = re.compile(r"^(\d{4})[-.](\d{2})[-.](\d{2})\s*(.*)$")
_CHA_PREFIX = re.compile(r"^(\d{1,3})\s*차[\s_]*(.*)$")


def _normalize(name):
    return re.sub(r"\s+", "", (name or "")).lower()


def detect_naming_pattern(sibling_names):
    """형제 폴더 이름들을 보고 지배적 명명 규칙을 반환한다.

    반환: dict {kind: 'date'|'cha'|'plain', sep, max_cha}
    """
    date_sep = None
    date_count = 0
    cha_count = 0
    cha_sep = " "
    max_cha = 0
    for n in sibling_names:
        m = _DATE_PREFIX.match(n)
        if m:
            date_count += 1
            date_sep = "-" if "-" in n[:10] else "."
            continue
        m = _CHA_PREFIX.match(n)
        if m:
            cha_count += 1
            num = int(m.group(1))
            max_cha = max(max_cha, num)
            # 구분자(공백 vs 언더바) 감지
            after = n[m.start(2):]
            cha_sep = "_" if ("_" in n.split("차", 1)[1][:1] or "_" in n) and " " not in n else " "
            continue
    total = len(sibling_names)
    if cha_count and cha_count >= date_count:
        return {"kind": "cha", "sep": cha_sep, "max_cha": max_cha}
    if date_count:
        return {"kind": "date", "sep": date_sep or "-", "max_cha": max_cha}
    return {"kind": "plain", "sep": " ", "max_cha": max_cha}


def find_existing_company_folder(sibling_names, company):
    """company 이름을 포함하는 기존 폴더가 있으면 그 이름을 반환(없으면 None).

    폴더명이 "N차 신안그린테크" / "2026-09-20 유진철강" 처럼 접두가 붙어 있어도
    회사명 핵심 토큰이 들어 있으면 매칭한다.
    """
    comp = _normalize(company)
    if not comp:
        return None
    # 회사명에서 접미(㈜, (주), 산업, 시스템 등)를 떼어낸 핵심 토큰도 함께 시도
    core = re.sub(r"(주식회사|㈜|\(주\)|산업|시스템|테크|이엔지|엔지니어링)", "", company or "")
    core = _normalize(core)
    for n in sibling_names:
        nn = _normalize(n)
        if comp and comp in nn:
            return n
        if core and len(core) >= 2 and core in nn:
            return n
    return None


def propose_company_folder(sibling_names, company, product=None, today=None):
    """새 업체 하위폴더 이름을 규칙에 맞게 제안한다.

    반환: (folder_name, is_new, pattern)
      기존 폴더가 있으면 (그 이름, False, ...)
      없으면 감지된 규칙으로 새 이름 (name, True, ...)
    """
    existing = find_existing_company_folder(sibling_names, company)
    pattern = detect_naming_pattern(sibling_names)
    if existing:
        return existing, False, pattern

    company_clean = (company or "업체명미상").strip()
    today = today or datetime.date.today()
    if pattern["kind"] == "date":
        sep = pattern["sep"]
        datestr = today.strftime(f"%Y{sep}%m{sep}%d")
        name = f"{datestr} {company_clean}"
    elif pattern["kind"] == "cha":
        nxt = pattern["max_cha"] + 1
        if pattern["sep"] == "_":
            parts = [f"{nxt}차", company_clean]
            if product:
                parts.append(product)
            name = "_".join(parts)
        else:
            name = f"{nxt}차 {company_clean}"
    else:
        name = company_clean
    return name, True, pattern
