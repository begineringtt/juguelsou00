# PDF 헤더 매핑 개선 + 업체명 자동 인식 + 과제 프리셋 정리/CRUD — 설계안

- 날짜: 2026-08-05 (설계), 2026-09-01 (실제 구현 상태 반영)
- 상태: 부분 구현됨 — A항목은 설계대로 구현 완료, B/C항목은 목표는 달성했으나 설계와 다른 기술적 접근으로 구현됨, D항목은 CRUD 자체는 동작하나 스펙의 API 계약과 다름. 각 섹션 끝의 "실제 구현" 하위 항목 참고.

## 구현 현황 요약

| 항목 | 설계 | 실제 구현 | 판정 |
|---|---|---|---|
| A. PDF 헤더 동의어 확장 + 좌표 기반 복구 | `HEADER_SYNONYMS`에 QUANTITY/PRICE 추가 + fuzzy fallback, `find_tables()`+`crop()`으로 품목명 칸 복구 | 설계대로 구현 (커밋 `e8498fb`, `7d21523`, 계획 `docs/superpowers/plans/2026-08-31-pdf-header-matching-improvements.md`) | ✅ 구현 완료 |
| B. 과제 프리셋 정리 + `short_name` | JSON에 `short_name` 필드 저장, 10개로 정리 | 10개 정리는 동일하게 됨. 필드명은 `short_name`이 아니라 `label`이며, 사용자가 지정하지 않으면 `PROJECT_LABEL_KEYWORDS` 키워드 매칭(`short_label()`)으로 매번 계산(`effective_label()`) | △ 목표 달성, 저장 방식 다름 |
| C. PDF 업체명 자동 인식 | `extract_tables()`로 표 셀 라벨-값 매칭 우선 | `extract_company_name(text)`가 라인 단위 정규식 라벨 매칭 + `(주)`/`㈜`/`주식회사` 반복 빈도 추정으로 구현 — 표 셀 단위 접근 아님 | ✅ 목표 달성, 접근 방식 다름 |
| D. 과제 프리셋 CRUD, id 기반 REST API | `id`(uuid4) 필드 + `POST/PUT/DELETE /api/projects/<id>` | `id` 필드 없음. `project_name`을 키로 쓰는 `POST /add_project`/`/update_project`/`/delete_project` (전부 POST). 프론트엔드 `<select>`의 `value`도 설계와 달리 여전히 배열 인덱스(`loop.index0`) 그대로 | △ CRUD는 동작하나 API 계약이 다름 |

## 배경

사용자가 4가지 개선을 요청함:

1. `견적서_20260721(그린플러스_IR Cut_8월).pdf` 처럼 품목표 헤더가 영문(Description/Quantity/Unit/Price)인 견적서를 업로드하면 품목/규격/단위/수량/단가가 제대로 채워지지 않는다.
2. 과제 선택 목록(`data/projects.json`)에 중복 항목이 많고 과제명이 길어 고르기 불편하다.
3. PDF에서 업체명(거래처명)도 자동으로 인식해서 기본정보 입력란에 반영할 수 있으면 좋겠다.
4. 과제 프리셋(축약어별 중앙행정기관/전문기관/과제명)을 페이지 안에서 직접 추가/수정/삭제할 수 있어야 한다.

## A. PDF 품목 헤더 매핑 개선 (`pdf_item_parser.py`)

`견적서_20260721(그린플러스_IR Cut_8월).pdf`를 pdfplumber로 직접 분석한 결과, 문제는 두 겹이었다:

### A-1. 헤더 동의어 부족

표 헤더가 `Description / Quantity / Unit / Price(￦/M2) / Amount(￦)` 로 되어 있는데:
- `Description`→name, `Unit`→unit 은 이미 동의어에 있어 매칭됨.
- `Quantity`는 동의어 목록(`Q'TY`, `QTY`)에 없어 매칭 실패 → **`QUANTITY`를 qty 동의어에 추가**.
- `Price(￦/M2)`는 괄호가 붙어 있어 `UNIT PRICE`/`단가`와 정확히 일치하지 않음 → **`PRICE`를 price 동의어에 추가**하고, `match_field`가 (기존 정확 일치 우선 시도 후) 실패하면 `match_field_fuzzy`(부분 문자열 포함 매칭)로 한번 더 시도하도록 fallback을 추가한다. 이렇게 하면 `PRICE(￦/M2)`도 "PRICE"를 포함하므로 매칭된다.
- `Amount(￦)`(금액 = 수량×단가)는 의도적으로 동의어에 추가하지 않는다 — 단가가 아닌 합계금액이므로 여기 매핑되면 안 된다. (fuzzy 매칭을 추가해도 "AMOUNT"는 어떤 동의어와도 겹치지 않으므로 안전)

### A-2. 품목명 칸이 표에서 통째로 누락되는 문제 (핵심 버그)

이 PDF는 품목명(Description) 칸에 **행별 구분선이 없다** — 배경색 강조 박스가 수량/단위/단가/금액 4개 칸에만 그려져 있고, 품목명 칸은 표 전체 높이만큼 하나로 뭉쳐 있다. 그 결과 pdfplumber의 선(line) 기반 표 추출이 품목명 칸을 행 단위로 못 쪼개서, **헤더 행과 모든 데이터 행에서 품목명 칸이 빈 값(None)으로 나온다** (직접 확인함 — 현재 코드로 이 파일을 파싱하면 품목 0개, "표를 인식하지 못했습니다" 경고만 나옴).

해결책: 표 추출 후, 최좌측 칸이 전체 행에서 비어 있는데 다른 칸들은 값이 있는 경우를 감지해서, **좌표 기반으로 복구**한다.
- `pdfplumber`의 `page.find_tables()`로 얻은 `Table` 객체는 각 행(`table.rows[i]`)의 실제 좌표(bbox)와, 옆 칸(1번 칸)의 x좌표를 알 수 있다.
- 품목명 칸의 x범위 = [표 왼쪽 끝, 1번 칸의 왼쪽 x좌표 최소값]. 이 범위 × 각 행의 (top, bottom) 로 `page.crop(...)`해서 그 영역의 텍스트를 뽑아 해당 행의 품목명으로 채운다.
- 이미 값이 있는 칸(예: 마지막 TOTAL행은 원래도 정상 추출됨)은 건드리지 않는다 — 빈 칸만 보충하므로 기존에 잘 동작하던 8개 샘플 PDF에는 영향이 없어야 한다 (회귀 테스트로 확인).
- 이 복구는 모든 후보 표에 대해 미리 적용해두고(부작용 없음: 채울 텍스트가 없으면 그대로 빈 값 유지), 그 다음에 기존 헤더 탐색/컬럼 매핑 로직을 그대로 태운다.

이 두 가지를 같이 적용하면: 헤더 행이 `["...복구된 Description...", "Quantity", "Unit", "Price(￦/M2)", None]` 형태로 살아나고, name/qty/unit/price 4개 필드가 모두 매핑되어 품목 2개(ETFE 필름, Nb2O5 Target Mix 재료비)가 정상 인식된다. 표 안의 소분류/설명 줄(예: "2) 가시광 투과율..." 같은 수량·단가 없는 줄)은 기존 계층형 대분류 처리 로직이 일부 흡수하지만 완벽하지 않을 수 있음 — 기존 설계 철학대로 "최선을 다해 초안을 채우고 사용자가 모달에서 검토/수정"하는 것으로 충분하다.

### 테스트

- `test_pdf_item_parser.py`에 이 IR Cut 샘플용 케이스 추가 (품목 2개, 각각의 name/unit/qty/price 값 확인).
- 기존 8개 샘플에 대한 기존 테스트가 계속 통과하는지 확인 (회귀 방지).

### 실제 구현 (2026-09-01, 설계대로 구현 완료)

`docs/superpowers/plans/2026-08-31-pdf-header-matching-improvements.md` 계획으로 진행, 두 태스크 모두 task 리뷰 및 최종 whole-branch 리뷰 승인.

- **A-1 (헤더 동의어)**: `pdf_item_parser.py`의 `HEADER_SYNONYMS`에 `QUANTITY`(qty)/`PRICE`(price) 동의어 추가, `find_header_row`/`map_table_columns`가 정확 매칭 실패 시 기존 `match_field_fuzzy`로 한 번 더 시도하도록 fallback 연결. 설계 문서(A-1)와 구현이 정확히 일치 (커밋 `e8498fb`).
- **A-2 (좌표 기반 품목명 복구)**: 새 순수 함수 `_recover_missing_name_column(table_x0, rows, row_cells, crop_text_fn)` 추가, `_find_best_table`이 `page.extract_tables()` 대신 `page.find_tables()` + `.extract()`를 호출해 셀 bbox 정보를 얻고 이 복구를 끼워 넣도록 변경. 이미 값이 있는 칸(bbox가 존재하는 칸)은 절대 건드리지 않음 — 설계(A-2)의 "빈 칸만 보충" 원칙 그대로 구현 (커밋 `7d21523`).
- **테스트**: `test_parse_pdf_items_recovers_borderless_name_column_with_english_headers`를 실제 `견적서_20260721(그린플러스_IR Cut_8월).pdf` 샘플로 추가 — 설계에서 예상한 품목 2개(ETFE 필름, Nb2O5 관련 재료)와 각각의 qty/unit/price 값을 검증. 기존 8개 샘플 테스트 전부 회귀 없이 통과 확인.

## B. 과제 프리셋 정리 (중복 제거 + `short_name` 축약어)

`data/projects.json`의 14개 항목을 아래 10개로 정리하고, 각 항목에 `short_name` 필드를 추가한다.

| short_name | agency | org | project_name |
|---|---|---|---|
| 고효율 | 농림축산식품부 | 농림식품기술기획평가원 | 고효율 광원 및 지능형 광조절 시스템 탑재 모듈형 수직농장 모델 개발 |
| 수확후 | 농림축산식품부 | 농림식품기술기획평가원 | 수확 후 전 과정 무인 자동화 시스템 개발 및 실증 |
| 탄소 | 과학기술정보통신부 | 정보통신기획평가원 | 농축산시설 탄소 배출량 통합관리를 위한 디지털 트윈 플랫폼 기술 개발 |
| 저온성 | 농림축산식품부 | (재)스마트팜연구개발사업단 | 무인 자율형 K-Farm 저온성 작물 데모온실 구축 및 검증 |
| 북미 | 농림축산식품부 | 농림식품기술기획평가원 | 북미 북동부 환경 적응 및 특약용 작물 재배용 수직농장 모델 개발 |
| 자동화 | 농림축산식품부 | 농림식품기술기획평가원 | 인건비 절감 및 생산량 극대화를 위한 심화작업 자동화 수직농장 모델 개발 |
| IR | 농림축산식품부 | 농림식품기술기획평가원 | 중동 등 수출대상국가에 적합한 시설자재 개발 및 현지 실증 |
| 고온 | 농림축산식품부 | 농림식품기술기획평가원 | 무인 자율형 K-Farm 고온성 작물 데모온실 구축 및 검증 |
| 근권부 | 농림축산식품부 | (재)스마트팜연구개발사업단 | 시설 과채류 작물별 생리해석 및 근권부 정밀제어를 위한 지능형 의사결정 시스템 상용화 |
| 로봇 | 산업통상자원부 | 한국산업기술기획평가원 | 수직농장 유연생산을 위한 자율 농수작업 로봇기술 개발 |

제거되는 4건 (중복): "농・축산시설..." 탄소 오타 변형, "K-farm"(소문자) 저온성 중복, "북동부권"/"특·약용" 표기 + 전문기관이 다른 북미 변형(오타로 확인됨, 농림식품기술기획평가원으로 통합), "특〮약용" 특수문자 북미 변형.

이 목록으로 `history_store.DEFAULT_PROJECTS`와 `data/projects.json`을 갱신한다 (기존 `data/projects.json`을 위 10개로 덮어씀).

`record_generation()`/`merge_read_seed()`가 기존 프로젝트 목록에 자동으로 항목을 추가하는 기존 동작은 그대로 둔다 (이렇게 자동 추가된 항목은 `short_name`이 없을 수 있음 → 화면에서는 `short_name`이 없으면 `project_name`을 그대로 보여주는 것으로 하위 호환 처리).

### 프론트엔드 변경

- "과제 선택" `<select>`의 옵션 텍스트를 `project_name` 대신 `short_name`(없으면 `project_name`)으로 표시하고, `title` 속성에 전체 `project_name`을 넣어 마우스 오버 시 전체 과제명을 볼 수 있게 한다.
- 옵션의 `value`는 배열 인덱스 대신 **항목의 고유 id**로 바꾼다 (아래 D에서 CRUD로 목록이 동적으로 바뀌므로 인덱스 기반 매칭은 깨지기 쉬움).

### 실제 구현 (스펙과 다른 방식으로 구현됨)

- **10개 정리**: 설계(B 표)와 동일한 10개 프로젝트가 `history_store.DEFAULT_PROJECTS`에 그대로 들어 있음 (커밋 `57e7c3a`). 이 부분은 설계 그대로 반영됨.
- **`short_name` 필드는 없음**: 대신 `label`이라는 이름의 선택적 필드를 씀. 사용자가 관리 패널에서 명시적으로 축약명을 입력한 경우에만 `label`이 저장되고(`add_project`/`update_project`), 없으면 `PROJECT_LABEL_KEYWORDS`(키워드→축약명 매핑 테이블)를 이용한 `short_label(project_name)`으로 매번 즉석 계산 — 이 둘을 합친 게 `effective_label(project)` (`history_store.py:80-103`). `record_generation`/`merge_read_seed`로 자동 추가되는 항목은 `label`이 없는 채로 저장되고 화면에서는 키워드 매칭 결과가 표시됨 — 설계 §65의 "하위 호환 처리" 의도와 결과적으로 같음.
- **프론트엔드 표시는 구현됨, `value`는 여전히 인덱스**: `templates/index.html:224`의 `<option value="{{ loop.index0 }}">{{ p.label }}</option>`처럼 옵션 텍스트는 `label`(= `effective_label` 결과)로 표시되지만, `value`는 설계에서 바꾸기로 한 "고유 id"가 아니라 여전히 배열 인덱스(`loop.index0`)다 — id 필드 자체가 없으므로(§D 참고) 이 부분은 구현되지 않았다. `title` 속성으로 전체 과제명을 보여주는 부분도 코드에 없음.

## C. PDF 업체명(거래처명) 자동 인식

### 인식 로직 (`pdf_item_parser.py`에 `extract_company_name(pdf_bytes)` 추가, `parse_pdf_items()` 결과에 `"company"` 키로 포함)

두 가지 패턴을 순서대로 시도, 첫 매칭을 채택:

1. **표 안 라벨-값 패턴**: `page.extract_tables()`로 얻은 모든 표(품목표 포함 전부)를 훑어서, 어떤 셀이 회사명 라벨 동의어(`상호`, `업체`, `거래처명`, `발신`, `회사명`, `COMPANY`, `COMPANY NAME`)와 일치하면 같은 행의 다음 비어있지 않은 셀을 값 후보로 취한다. (`견적서_20260721` 샘플의 "상호 | 마이크로웍스솔루션즈 주식회사" 행이 이 패턴)
2. **평문 "라벨 : 값" 패턴**: 표에서 못 찾으면 페이지 텍스트를 줄 단위로 스캔해서 위 동의어 라벨 뒤 콜론(`:`/`：`) 다음 값을 후보로 취한다 (기존 `extract_paragraph_fallback`과 동일한 방식, 회사명 전용으로 재사용).

**안전장치 (자사명 오인식 방지)**: 실제 샘플 견적서 중 일부는 "회사명" 라벨이 발주처(그린플러스, 즉 사용자 회사 자신)를 가리키는 경우가 있었다 (`2. 그린플러스_광센서_견적서.pdf`, `한열사_견적서_북미.pdf`). 후보 값을 정규화했을 때 `"그린플러스"`(공백 유무 무관, `(주)` 등 접두 무관)를 포함하면 그 후보는 버리고 다음 후보를 계속 찾는다. 못 찾으면 `company`는 `None`으로 반환 — 이 경우 프론트엔드는 체크박스를 아예 보여주지 않는다.

라벨이 전혀 없는 견적서(로고 이미지만 있는 경우 등, 예: `견적서_일신_북미.pdf`)는 인식되지 않는다 — 기존 품목 파싱과 동일하게 "최선을 다해 인식, 실패 시 직접 입력"이 원칙이므로 범위 밖으로 둔다.

### 프론트엔드 변경 (PDF 가져오기 모달)

- `/parse_pdf` 응답에 `company` 필드가 추가됨.
- 모달 상단(경고 문구 아래)에 `company`가 인식된 경우에만 `인식된 업체명: {값} [기본정보에 반영 ✓]` 형태의 체크박스를 표시 (기본 체크됨).
- "표에 적용" 버튼 클릭 시, 이 체크박스가 켜져 있으면 기본정보의 업체명 입력란(`input[name=company]`)에 값을 반영한다 (품목 반영과 별개 동작이며, 품목 교체/추가 선택과 무관하게 항상 적용).

### 실제 구현 (목표는 달성, 접근 방식은 다름)

- **인식 로직**: 설계와 달리 `extract_tables()`로 표 셀을 훑는 방식이 아니라, 페이지 전체 텍스트(`text`)를 줄 단위로 스캔해서 라벨 정규식(`_COMPANY_LABEL_PATTERNS`)으로 먼저 찾고, 실패하면 `(주)`/`㈜`/`주식회사` 반복 패턴(`_COMPANY_PATTERNS`)의 등장 빈도로 추정하는 방식으로 구현됨 (`pdf_item_parser.py:96` `extract_company_name(text)`, 커밋 `7164bd4`, rev.2 전환 커밋 `eeadc22`에서 배선). 함수 시그니처도 설계의 `extract_company_name(pdf_bytes)`가 아니라 이미 추출된 텍스트를 받는 `extract_company_name(text)`.
- **자사명 오인식 방지**: 설계와 동일한 목적으로 `_OUR_COMPANY_MARKERS`(그린플러스/GREENPLUS 등)를 후보에서 제외하는 로직이 구현되어 있음 — 설계 §81의 안전장치 그대로.
- **프론트엔드**: 설계는 "기본 체크된 체크박스"를 제안했지만, 실제로는 `pdfCompanyRow`(`templates/index.html:336`)라는 편집 가능한 텍스트 입력 행으로 구현되어 있고, 기본정보의 업체명란이 **비어 있을 때만** 자동으로 채워짐(`templates/index.html:751`, `!companyInput.value.trim()`) — 체크박스 온/오프 방식이 아니라 "값이 없을 때만 자동 채움 + 직접 수정 가능"으로 UX가 달라짐.

## D. 과제 프리셋 CRUD (추가/수정/삭제) — 즉시 반영

### 데이터 모델 변경

`data/projects.json`의 각 항목에 고유 `id`(문자열, `uuid4().hex`)를 추가한다. `history_store.load_projects()`가 로드 시 `id`가 없는 기존 항목에는 자동으로 id를 부여하고 저장한다 (마이그레이션, 하위 호환).

### 백엔드: 새 라우트 (`app.py`)

- `POST /api/projects` — body: `{short_name, agency, org, project_name}` → 새 항목 생성(`id` 부여) 후 생성된 항목 JSON 반환.
- `PUT /api/projects/<id>` — body: 위 4개 필드 → 해당 id 항목 수정 후 수정된 항목 반환. 없는 id면 404.
- `DELETE /api/projects/<id>` — 해당 id 항목 삭제. 없는 id면 404.

세 라우트 모두 `history_store.py`에 대응하는 `add_project(data)` / `update_project(id, data)` / `delete_project(id)` 함수를 추가해서 처리하고, `data/projects.json`을 갱신한다. 최소 검증: `project_name`은 필수(빈 문자열이면 400), 나머지 필드는 빈 문자열 허용.

### 프론트엔드: 관리 패널

- "과제 정보" fieldset 안, "과제 선택" 드롭다운 옆에 `⚙ 과제 관리` 버튼 추가. 클릭 시 아래에 접이식 패널이 펼쳐짐/닫힘.
- 패널 내용: `축약어 | 중앙행정기관 | 전문기관 | 과제명 | (저장/삭제)` 4+1열 표. 각 행은 텍스트 입력칸으로 바로 수정 가능하고 행마다 "저장"(변경분 있을 때만 활성화) / "삭제" 버튼.
- 맨 아래 빈 입력 행 + "추가" 버튼으로 신규 항목 등록.
- 모든 동작은 `fetch()`로 위 API를 호출하고, 성공하면 클라이언트 메모리의 `PROJECTS` 배열을 갱신 → 관리 패널 표, "과제 선택" 드롭다운, 중앙행정기관/전문기관/과제명 datalist를 모두 다시 그린다 (페이지 새로고침 없음).
- 삭제 시 간단한 `confirm()` 확인창을 띄운다 (되돌릴 수 없는 삭제이므로).

### 실제 구현 (CRUD는 동작하나 API 계약이 다름)

- **`id` 필드 없음**: `data/projects.json`의 각 항목에 `uuid4` 기반 `id`는 없다. 대신 `project_name` 문자열을 키로 사용한다.
- **라우트**: 설계의 `POST /api/projects`·`PUT /api/projects/<id>`·`DELETE /api/projects/<id>` 대신, 전부 `POST`인 `app.py`의 `/add_project`(28행)·`/update_project`(45행)·`/delete_project`(63행) 3개 라우트로 구현됨 (커밋 `eeadc22`). 수정 시에는 `original_name`(변경 전 과제명)으로 대상을 찾으므로, **동명 과제가 있으면 잘못된 항목이 수정/삭제될 수 있는 취약점**이 있음 — id 기반이었다면 없었을 문제.
- **프론트엔드 관리 패널**: "⚙ 과제 관리" 접이식 표 대신, "과제 선택" 옆에 `+ 새 과제 추가`/`수정`/`삭제` 버튼과 별도 패널(`#addProjectPanel`, `templates/index.html:227-231`)로 구현됨 — 목적(추가/수정/삭제를 새로고침 없이)은 동일하게 달성했으나 UI 구조는 설계의 "4+1열 표"가 아님.
- **`value` 인덱스 기반 유지**: §B의 "실제 구현"에서 언급한 대로, `<select>`의 `value`가 여전히 `loop.index0`라서, 목록 순서가 바뀌거나 항목이 삭제/추가되면 이전에 선택돼 있던 옵션의 `value`가 다른 항목을 가리키게 될 수 있다 — id 기반으로 갔다면 방지됐을 문제이며, 위 `original_name` 기반 수정/삭제 취약점과 근본 원인이 같다(고유하고 불변인 식별자의 부재).

## 범위 밖

- 업체명 인식 로직이 커버하지 못하는 견적서 양식(라벨 없는 로고형, 표 없이 자유배치된 폼형 등)에 대한 별도 대응.
- 품목표 내 소분류/설명 줄의 완벽한 정리(기존 계층형 처리 한계 그대로 유지).
- `record_generation`/`merge_read_seed`가 자동 추가하는 프로젝트 항목에 `short_name`을 자동으로 유추해서 채우는 기능 (수동으로 관리 패널에서 채우면 됨).
