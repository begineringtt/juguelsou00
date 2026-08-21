# 품목 표 열(컬럼) 사용자 설정 기능 — 설계안

- 날짜: 2026-08-21
- 상태: 설계 승인됨 (구현 대기)

## 배경

`견적서_알루스퀘어.pdf`는 일반 견적서(품명/규격/단위/수량/단가)와 달리 **중량(重量)** 열이 하나 더 있다(품명/규격/수량/중량/단위/단가/공급가액). 사용자가 다음 4가지를 요청함:

1. 단위/수량 칸은 병합하지 말고 셀 1칸에서만 입력되게 한다.
2. 품목/규격 칸의 범위(폭)를 늘린다.
3. "중량"처럼 지금 없는 항목을 타이핑해서 추가할 수 있어야 하고, 그 항목도 PDF에서 자동 인식되어야 한다.
4. 항목들의 순서를 바꿀 수 있는 설정을 넣는다.

기존에는 규격/단위/수량/단가 4개가 `generator.py`의 `ITEM_FIELDS`에 고정 리스트로 박혀 있고, 화면에도 체크박스 4개가 고정으로 있었다. 이걸 사용자가 직접 추가/삭제/순서변경/켜고끄는 **하나의 설정**으로 일반화한다.

## A. 데이터 모델 (`column_settings.py`, 신규)

`data/column_settings.json`에 저장:

```json
{"columns": [
  {"key": "spec",  "label": "규격", "enabled": true, "builtin": true},
  {"key": "unit",  "label": "단위", "enabled": true, "builtin": true},
  {"key": "qty",   "label": "수량", "enabled": true, "builtin": true},
  {"key": "price", "label": "단가", "enabled": true, "builtin": true}
]}
```

- **품목(name)은 항상 맨 앞, 공급가(supply)/부가세(vat)는 항상 맨 뒤 고정** — 이 셋은 목록에 들어가지 않는다. 계산식(`공급가 = 수량×단가`, `부가세 = 공급가/10`)이 `key`로 열을 찾아 쓰기 때문에(`_col_letter(layout, "qty")` 등 고정 열 문자가 아니라 key 기반 조회) 순서가 바뀌어도 그대로 동작한다.
- 리스트에 있는 순서 = 화면 입력 표 순서 = 엑셀 생성 순서 = PDF 인식 매칭 순서.
- `builtin: true`(규격/단위/수량/단가)는 끄기만 가능, 삭제 불가. `builtin: false`(타이핑으로 추가한 항목)는 켜기/끄기/삭제/순서변경 모두 가능.
- 파일이 없으면 위 4개 builtin 기본값으로 새로 만든다(`load_columns()`가 없으면 생성).

**모듈 API** (`history_store.py`와 같은 스타일):
- `load_columns() -> list[dict]`
- `save_columns(columns: list[dict])` — 순서/`enabled` 값을 통째로 덮어씀 (설정 모달의 "저장"에서 사용)
- `add_custom_column(label: str) -> dict` — `custom_<n>` 형태의 새 key를 발급해 리스트 끝에 추가하고 저장, 추가된 항목 반환. `label`이 비어있거나(공백 제거 후) 이미 있는 항목의 라벨과 정규화 기준(`normalize_header`)으로 같으면 새로 만들지 않고 기존 항목을 그대로 반환한다(중복 방지).
- `set_column_enabled(key: str, enabled: bool)` — 체크박스 즉시토글 자동저장용 (순서는 안 건드림)
- `delete_column(key: str)` — `builtin`이면 무시, 아니면 제거하고 저장

## B. 셀 폭 배분 규칙 (`generator.py`)

`ITEM_FIELDS` 고정 리스트를 없애고, `column_settings.load_columns()`에서 `enabled`인 것만 걸러 동적으로 구성한다. name/supply/vat는 여전히 코드에 고정.

**폭 배분**: 열을 "narrow"(1칸 고정, 병합 없음)와 "wide"(가중치 비례 분배)로 나눈다.
- narrow: `unit`, `qty`, 그리고 모든 커스텀(`builtin: false`) 열 — 기본적으로 짧은 값 위주라고 가정.
- wide: `name`(가중치 6), `spec`(가중치 5), `price`(가중치 3), `supply`(가중치 3), `vat`(가중치 3) — 기존 `_largest_remainder_allocation`을 그대로 재사용.
- 전체 27칸 중 narrow 열 개수만큼 뺀 나머지를 wide 열끼리 가중치대로 분배.

실제로 계산해본 결과(기본 4개 다 켜짐):

```
품목: B-H (7칸)   ← 기존 B-F(5칸)에서 넓어짐
규격: I-N (6칸)   ← 기존 G-J(4칸)에서 넓어짐
단위: O (1칸)     ← 기존 K-M(3칸, 병합) 에서 단칸으로
수량: P (1칸)     ← 기존 N-P(3칸, 병합) 에서 단칸으로
단가: Q-T (4칸, 기존과 동일)
공급가: U-X (4칸, 기존과 동일)
부가세: Y-AB (4칸, 기존과 동일)
```

단위/수량을 1칸으로 고정해서 남는 4칸이 품목(+2)·규격(+2)에만 들어가고 단가/공급가/부가세는 그대로 유지된다. `_add_item_row_merges`는 지금처럼 `span > 1`인 열만 병합하므로 단위/수량/커스텀 열은 자동으로 병합되지 않는다.

`test_column_layout.py`의 기존 기대값(B-F 등)은 이 변경으로 달라지므로 새 값으로 갱신한다.

## C. PDF 인식 확장 (`pdf_item_parser.py`)

지금 `match_field`/`match_field_fuzzy`/`_could_seed_label`/`_label_field_for_prefix`/`find_header_row`/`map_table_columns`가 전부 모듈 상수 `HEADER_SYNONYMS`를 직접 참조한다. 이 함수들에 `synonyms=HEADER_SYNONYMS` 파라미터를 추가해서(기본값이 기존 상수이므로 기존 호출부/테스트는 안 건드려도 그대로 통과), `parse_pdf_items(pdf_bytes, extra_fields=None)`가 호출될 때 `extra_fields`(예: `{"custom_1": ["중량"]}`, `column_settings`에서 만든 커스텀 항목 라벨)를 `HEADER_SYNONYMS`와 합친 딕셔너리를 만들어 전체 파이프라인에 넘긴다.

`extract_items_from_table` 등 표 추출 파이프라인(pdfplumber 표 경로 + OCR 경로 둘 다)은 지금 `name/spec/unit/qty/price`만 고정된 dict 모양으로 행을 만드는데, 여기에 커스텀 열도 "그 열이 있으면 값을 담아 그대로 다음 단계로 흘려보내는" 방식으로 일반화한다 — `resolve_duplicate_price_columns`/`clean_item_rows`/`apply_hierarchical_prefix`는 자기가 아는 필드(name/spec/qty/price)만 보고 나머지 키는 그대로 복사해서 넘긴다 (이미 `apply_hierarchical_prefix`가 `row = dict(row)` 패턴으로 이렇게 하고 있음, 같은 패턴 재사용).

`app.py`의 `/parse_pdf` 라우트가 `column_settings.load_columns()`에서 `builtin: false`인 항목들을 모아 `extra_fields`로 넘긴다.

## D. 화면 UI (`templates/index.html`)

- 기존 "규격/단위/수량/단가" 체크박스 4개 → `column_settings`에서 받아온 열 개수만큼 **동적으로** 렌더링(Jinja). 체크 변경 시 지금처럼 즉시 열 표시/숨김(클라이언트) + `set_column_enabled` fetch로 서버에도 자동 저장 (페이지 새로고침 불필요).
- 체크박스 줄 옆에 **"⚙ 열 관리"** 버튼 → 모달:
  - 각 열이 한 줄: 드래그 핸들(⠿, HTML5 드래그로 순서 변경) + 열 이름 + (커스텀만) ✕ 삭제 버튼.
  - 맨 아래 입력창 + "추가" 버튼 — 타이핑하면 `add_custom_column`으로 새 항목 추가.
  - "저장" 클릭 시 새 순서를 `save_columns`로 보내고 `location.reload()` (표를 새 구성으로 다시 그림 — 진행 중이던 입력값은 이 시점에서 사라질 수 있음, 열 구성은 자주 바꾸는 게 아니라 허용 가능한 트레이드오프로 판단).
- PDF 업로드 미리보기 표(`pdfDraftBody`)도 활성화된 열만큼 컬럼을 동적으로 만들고, PDF 인식 결과에 커스텀 키 값이 있으면 그 칸에 채운다.
- 품목 입력 표(`itemsTable`)의 `<td data-col="...">`도 고정 5개에서 설정된 열 개수만큼 동적 생성으로 바뀐다. `/generate` 폼 제출 시 `item_<key>[]`형태로 필드명을 동적으로 만들어 보내고, `app.py`의 `/generate`도 `column_settings`를 읽어 그만큼의 `item_<key>[]`를 파싱해 `items` dict에 채운다.

## 테스트 계획

- `column_settings.py`: load/save/add/delete/enable 단위 테스트 (신규 `test_column_settings.py`).
- `generator.py`: `test_column_layout.py`의 기존 4개 테스트를 새 폭 배분 규칙에 맞게 갱신 + 커스텀 열 1개 추가된 경우의 레이아웃 테스트 추가.
- `pdf_item_parser.py`: `extra_fields`로 커스텀 라벨을 넘겼을 때 표/OCR 양쪽에서 그 값이 인식되는 테스트 추가 (기존 `test_pdf_item_parser.py` 스타일 유지, 필요하면 견적서_알루스퀘어.pdf로 "중량" 열 인식 회귀 테스트도 추가).
- `app.py` 라우트 테스트(`test_parse_pdf_route.py`, 신규 `test_generate_route.py` 등)에서 커스텀 열 있는 시나리오 왕복 확인.
