"""setting_03 을 "서버"로 보고, 업체별 통장사본·사업자등록증(및 기타 문서) 위치를
색인한다. setting_03 하위는 [과제폴더]/[업체폴더]/파일 구조이고, 업체 폴더 이름이
곧 업체명이다(앞에 날짜나 'N차'가 붙기도 함).

새 견적서를 처리할 때, 그 업체의 통장사본·사업자등록증이 다른 과제 폴더에 이미
있으면 찾아서 새 폴더로 복사하는 데 쓴다.
"""

import os
import re

# 문서 종류 판별(파일명 기준)
DOC_PATTERNS = {
    "통장사본": ["통장"],
    "사업자등록증": ["사업자"],
    "견적서": ["견적"],
    "지출결의서": ["지출결의", "지결"],
    "전자세금계산서": ["전자세금계산", "세금계산서"],
    "거래명세서": ["거래명세"],
    "검수확인서": ["검수확인"],
}

_DATE_PREFIX = re.compile(r"^\s*\d{4}[-.]\d{1,2}[-.]\d{1,2}\s*")
_CHA_PREFIX = re.compile(r"^\s*\d{1,3}\s*차[\s_]*")
# 업체명 뒤에 붙는 품목/괄호 설명 (예: "코리아농업개발(모터)", "성훈엔지니어링 (빌렛)")
_TRAIL_PAREN = re.compile(r"[\(（].*$")
_STRIP_TOKENS = re.compile(r"(주식회사|㈜|\(주\)|㈜|산업|시스템|테크|이엔지|엔지니어링|인터내셔널)")


def clean_company(folder_name):
    """업체 폴더명에서 날짜/차수 접두, 괄호 설명을 떼어 업체 표시명을 만든다."""
    name = folder_name
    name = _DATE_PREFIX.sub("", name)
    name = _CHA_PREFIX.sub("", name)
    # 언더바로 품목이 붙은 경우(팁스: 아이엘패널_판넬) 첫 토큰을 업체명으로
    # 단, 업체명 자체에 _가 없다고 보장 못 하니 괄호/공백까지만 정리
    name = name.strip()
    return name


def normalize(s):
    return re.sub(r"\s+", "", (s or "")).lower()


def core_token(s):
    s = _TRAIL_PAREN.sub("", s or "")
    s = _STRIP_TOKENS.sub("", s)
    s = re.sub(r"[_\-\s]+", "", s)
    return normalize(s)


def classify(filename):
    n = filename.replace(" ", "")
    for doc, keys in DOC_PATTERNS.items():
        if any(k in n for k in keys):
            return doc
    return None


def build_index(setting03_root, categories=None):
    """setting_03 을 훑어 업체별 문서 위치를 색인한다.

    반환: { core_key: {
              "display": 대표 업체명,
              "folders": set(원본 폴더명들),
              "docs": { 문서종류: [ {path, mtime, folder, category}, ... ] } } }
    """
    index = {}
    if not os.path.isdir(setting03_root):
        return index
    for category in os.listdir(setting03_root):
        cat_path = os.path.join(setting03_root, category)
        if not os.path.isdir(cat_path):
            continue
        if categories and category not in categories:
            continue
        for company_folder in os.listdir(cat_path):
            comp_path = os.path.join(cat_path, company_folder)
            if not os.path.isdir(comp_path):
                continue
            display = clean_company(company_folder)
            key = core_token(display)
            if not key:
                continue
            node = index.setdefault(key, {"display": display, "folders": set(), "docs": {}})
            node["folders"].add(company_folder)
            # 더 짧고 깔끔한 표시명을 대표로
            if len(display) < len(node["display"]):
                node["display"] = display
            for root, _dirs, files in os.walk(comp_path):
                for fn in files:
                    if fn.startswith("~$"):
                        continue
                    doc = classify(fn)
                    if not doc:
                        continue
                    fpath = os.path.join(root, fn)
                    try:
                        mtime = os.path.getmtime(fpath)
                    except OSError:
                        mtime = 0
                    node["docs"].setdefault(doc, []).append(
                        {"path": fpath, "mtime": mtime, "folder": company_folder, "category": category})
    return index


def match_company(index, company):
    """업체명을 색인 키에 정확히(core_token 완전 일치) 매칭. 없으면 None.

    부분 일치("유사")는 잘못된 업체의 사업자등록증/통장사본이 조용히 붙는
    사고로 이어질 수 있어 여기서는 쓰지 않는다 - find_fuzzy_candidates()로
    후보를 뽑아 사용자 확인을 받은 뒤에만 쓴다.
    """
    key = core_token(company)
    if key and key in index:
        return key
    return None


def _is_fuzzy_partial(key_a, key_b):
    return bool(key_a) and bool(key_b) and (key_a in key_b or key_b in key_a) and min(len(key_a), len(key_b)) >= 2


def find_fuzzy_candidates(index, company):
    """정확히 일치하는 업체가 없을 때, 부분 포함 관계인 후보들을 찾는다.
    (정확 매칭이 있으면 애초에 확인이 필요 없으므로 빈 리스트를 반환한다.)

    반환: [{"key", "display", "has_docs": {문서종류: bool, ...}}, ...]
          이름 길이 차이가 적은(더 비슷한) 순으로 정렬.
    """
    key = core_token(company)
    if not key or key in index:
        return []
    candidate_keys = [k for k in index if _is_fuzzy_partial(key, k)]
    candidate_keys.sort(key=lambda k: abs(len(k) - len(key)))
    return [
        {
            "key": k,
            "display": index[k]["display"],
            "has_docs": {d: bool(index[k]["docs"].get(d)) for d in ("통장사본", "사업자등록증")},
        }
        for k in candidate_keys
    ]


def find_documents(index, company, doc_types=("통장사본", "사업자등록증"), prefer="newest"):
    """업체의 지정 문서들을 색인에서 찾아 각 종류별 대표 파일 경로를 반환.

    정확히 일치하는 업체일 때만 채운다(유사 매칭은 find_fuzzy_candidates()로
    후보를 보여주고 사용자가 확정한 뒤에만 이 함수에 그 확정된 이름을 넘겨야
    한다).

    반환: { 문서종류: path or None }, 그리고 매칭된 업체 표시명.
    """
    key = match_company(index, company)
    result = {d: None for d in doc_types}
    if key is None:
        return result, None
    node = index[key]
    for d in doc_types:
        cands = node["docs"].get(d, [])
        if not cands:
            continue
        if prefer == "newest":
            cands = sorted(cands, key=lambda c: c["mtime"], reverse=True)
        result[d] = cands[0]["path"]
    return result, node["display"]
