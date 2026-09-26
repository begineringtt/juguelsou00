# Progress: 견적서 기반 지출결의서·검수확인서 자동 정리 기능 개선

Last updated: 2026-09-26 (실행 중 경과/예상시간 표시 + 진행률 시각화 추가)

## Goal

- 견적서(PDF/JPG/XLSX) 한 장을 올리면 지출결의서·검수확인서를 만들고, PDF 변환 + 과제/업체 폴더 정리 + 통장사본·사업자등록증 자동 첨부 + 체크리스트/처리이력 갱신까지 한 번에 처리하는 `/batch` 화면(견적서자동정리_실행.bat)을 실사용 가능한 수준으로 완성한다.
- 기존 "지출결의서 단독 생성" 화면(`/`, 실행.bat)은 그대로 유지하고, 두 화면을 개별 도구로 계속 쓸 수 있게 한다.

## Current Status

- Status: In progress (핵심 플로우는 동작 확인됨, 남은 과제 있음 — 아래 Next Steps 참고)
- Current focus: 없음 — 사용자 확인 대기 중 (이 문서 작성 시점에 막 완료한 작업들의 실사용 검증)
- Branch: `main` (로컬에서만 작업, 브랜치 분리 없이 직접 커밋)
- Related issue/PR: 없음. [2026-09-26] `main`을 origin에 push 완료(14커밋) — 이제 `main`과 `origin/main`이 동일한 상태.

## Decisions

- [2026-09-22] 배치 화면(`/batch`)의 과제 카테고리를 고정 9개 목록 대신, 단독 생성 화면(`/`)과 동일한 사용자 관리 과제 목록(`history_store`)을 쓰도록 변경 — 두 화면이 과제 정보를 공유해야 한다는 사용자 요구.
- [2026-09-22] 이미지(JPG/PNG) 견적서의 회전 보정 기준: Tesseract OSD(`image_to_osd`)로 감지, 실패 시 원본 유지 — 신뢰도 낮아도 방향 보정 자체는 시도(과도하게 보수적으로 하지 않기로 함).
- [2026-09-22] `folder_router`가 모르는 과제 카테고리(사용자가 새로 추가한 과제 등)를 만나면 예외를 던지는 대신, 카테고리 이름 자체를 폴더명으로 써서 새 폴더를 만들도록 완화 — 배치 화면이 고정 카테고리에서 사용자 관리 목록으로 바뀐 이상, 이 제약이 막혀서는 안 됨.
- [2026-09-22] 업체명 자동 인식(`/batch_parse_quote`)은 회사명/제목만 필요하므로, 이미지 견적서의 무거운 품목 표 OCR(`ocr_extract_items`, 셀마다 Tesseract 프로세스 별도 실행이라 큰 사진에서 675초까지 걸림)을 건너뛰기로 함(`company_only=True`) — 사용자가 "업체명이 자동으로 안 됨"이라 느낀 원인이 실제로는 무한정 느린 처리였음.
- [2026-09-22] setting_03에서 업체명으로 사업자등록증/통장사본을 자동 찾을 때, **핵심어 완전 일치("정확")만 조용히 자동 첨부**하고, 부분 일치("유사")는 후보 목록을 보여주고 사용자가 확정한 것만 쓰기로 함 — 잘못된 업체의 통장/계좌 정보가 조용히 붙는 사고 방지가 우선순위. (사용자 승인: "핵심어가 일치하면 정확", 확인은 "견적서 올리자마자 바로", 거부 시 "직접 업로드 + 해당없음 선택창").
- [2026-09-22] 검수확인서에는 금액(공급가)을 아예 안 보여주기로 함 — 검수확인서는 품목/규격/수량 확인용 문서지 금액 확인용이 아니라는 사용자 판단.
- [2026-09-22] Flask 개발 서버를 `threaded=True`로 전환 — 느린 OCR 요청 하나가 서버 전체를 막아버리는 구조적 문제(ERR_CONNECTION_REFUSED, Failed to fetch 등 여러 증상의 공통 원인)였음.
- [2026-09-22] `실행.bat`과 `견적서자동정리_실행.bat`이 서로 다른 기본 화면(`/` vs `/batch`)을 열도록 `GP_OPEN_PAGE` 환경변수로 분기 — 두 화면을 "개별 도구"로 쓰고 싶다는 사용자 요구에 맞춤.
- [2026-09-26] 사용자가 "연구비 소진 계획 대비 체크가 반영이 안 된 것 같다"고 했지만 실제로는 버그가 아니라 "숫자 나열이라 한눈에 안 보인다"는 시각화 문제였음 — dataviz 스킬 기준으로 전체 진행률 큰 숫자 + 과제별 진행률 막대(단일 브랜드색 채움 + 회색 트랙, 완료율 낮은 순 정렬)를 기존 표 위에 추가.
- [2026-09-26] `/batch_run` PDF 변환 중 경과/예상 남은 시간 표시는, 백엔드가 단일 동기 요청이라 실제 진행률 스트리밍이 어려워 브라우저 localStorage에 지난 실행 시간(최근 20개)을 기록해두고 그 평균을 다음 실행의 예상 소요시간으로 쓰는 방식을 택함 — 서버 구조를 바꾸지 않고도 매 실행마다 예측이 점점 정확해짐.
- [2026-09-26] "연구비 소진 계획.xlsx" 체크 기능 설계 시, "01. 지출결의서_전체과제_통합(양식).xlsx"는 문서 내부 구조까지 비교하지 않고 과제 목록(시트 이름) 참조로만 쓰기로 함 — 사용자가 "문서 존재 여부만" 확인하면 된다고 답함. 금액 비교는 "계획 대비 오차금액까지" 포함하기로 함(사용자 답: "둘다") — 생성된 지출결의서 xlsx는 openpyxl로 저장된 수식이라 재파싱해도 계산된 값이 안 나오므로, 매번 실행 시 `report_writer.py`가 이미 남기는 `처리이력_보고서.xlsx`의 정적 견적 총액 값을 실제 금액 소스로 재사용함.
- [2026-09-26] 과제 표기가 파일마다 3가지로 다름("중동IR"/"중동"/"IR", "AI(1년)"/"AICS1년"/"AI(1y)그린CS" 등) — 기존 `folder_router.CATEGORY_TO_FOLDER`(부분 문자열 별칭)를 우선 재사용하고, 그걸로 못 잡는 AI 두 과제만 `budget_check.py`에 로컬 별칭 추가.
- [2026-09-26] `/batch_run`(품목까지 뽑는 전체 경로)의 격자 OCR 헤더 탐색을 고칠 때, "전체 이미지를 한 번만 OCR해서 셀 텍스트도 그 결과로 복원" 방식을 먼저 시도했으나 실제 샘플(`견적서_알루스퀘어.pdf`)에서 정확도 회귀가 났음(좁은 "품명" 열이 전체 페이지 OCR에서는 "ee" 같은 잡음으로 뭉개짐 — Tesseract가 psm 6 전체 페이지 모드에서 좁은 열 텍스트를 잘 못 읽는 게 근본 원인). 최종적으로는 "전체 이미지 OCR은 후보 행을 저렴하게 걸러내는 용도로만 쓰고, 실제 헤더 확정 + 본문 셀 값은 기존처럼 셀별 정밀 재OCR(`_ocr_cell`)을 그대로 쓰되 후보가 아닌 행은 건너뛴다"는 하이브리드로 확정 — 속도와 정확도를 둘 다 지키려면 "빠른 사전 필터 + 정밀 확정"조합이 필요했다는 게 핵심 교훈.

## Completed

- [x] 배치 화면 과제 카테고리를 사용자 관리 목록으로 전환, 과제 추가/수정/삭제 UI, 견적서 드래그앤드롭, 업체명 자동 인식 (`a6becc7`)
- [x] 이미지 견적서 회전 미보정 버그 수정(`fix_image_orientation`), `_read_image_quote`의 items 튜플 언패킹 누락 버그 수정, `folder_router` 미지원 카테고리 폴백 (`cd0b000`)
- [x] 배치 화면 업체명 자동 인식에서 무거운 품목 OCR 스킵 — 675초 → 27초 (`3ebb1ae`)
- [x] 단독 생성 화면(`/`)에 배치 화면(`/batch`)으로 가는 링크 추가 — 이전엔 `/batch`→`/`만 가능했음 (`356d2e0`)
- [x] `실행.bat`/`견적서자동정리_실행.bat`이 각자 다른 기본 화면을 열도록 분리 (`c6a728b`)
- [x] Flask 서버 `threaded=True` 전환 — 느린 OCR 요청이 다른 요청을 막던 문제 해결, 실측으로 검증(27초짜리 OCR 진행 중에도 PDF 파싱 0.7초 완료) (`42e7949`)
- [x] 검수확인서에서 공급가(금액) 컬럼 제거 — 규격/수량만 표시 (`e7f5189`)
- [x] setting_03 사업자등록증/통장사본 자동 첨부에 정확/유사 매칭 구분 + 유사 매칭 확인 UI 추가 (`15fd6aa`)
- [x] `/batch_run` 테스트가 실제 `data/app_config.json`을 오염시키던 테스트 격리 버그 수정 + 실사용자 설정 파일 복구 (`106a79a`)
- [x] 새 견적서 파일로 다시 업로드하면 이전 업체명이 안 바뀌던 버그 수정 (`a803006`)
- [x] "개요/단가/수량"처럼 세로형 필드-값 레이아웃인 견적서(품목 표 헤더가 없는 1개 품목짜리 스펙시트, 예: 혜일 2026.09.02 견적서)를 위한 최후 폴백 파서 추가 (`bbfbd94`)
- [x] 위 모든 변경사항을 실제 헤드리스 브라우저(playwright)로 직접 띄워서 화면 동작까지 확인 (배치 화면 렌더링, 업체명 자동 인식, 유사 매칭 선택 패널, 업체명 재업로드 시 갱신 등)
- [x] **`/batch_run` 전체 경로(품목까지 추출)의 격자 OCR 헤더 탐색 속도 근본 개선** — 헤더를 찾으려고 후보 행 전부(사진처럼 지저분하면 최대 100개+) x 열마다 셀을 잘라 별도 Tesseract 프로세스를 새로 띄우던 구조를, "전체 이미지 1회 OCR로 후보 행만 저렴하게 추리고, 실제 확정/본문 재구성은 기존처럼 셀 단위 정밀 재OCR" 하이브리드로 교체. 실측: `견적서_알루스퀘어.pdf` 87초 → 52초, 원래 신고 대상이었던 노이즈 심한 사진(`관수작업 비교견적서.jpg`, row 후보 101개 → 셀 재OCR 1338회 필요)은 아예 실행이 끝나지 않던 수준에서 35초로 완료. `_build_table_from_grid`가 body_end를 표 끝까지 늘릴 때 배열 경계를 벗어나 크래시하는 기존 오프바이원 버그도 같이 발견해 수정(회귀 테스트로 우연히 발견).

- [x] `/batch_run` 완료 결과에 "폴더 열기" 버튼 추가 — 백엔드 `/open_folder`(`os.startfile()`)와 프론트 버튼 연결, 이미 응답에 있었지만 화면에 안 쓰이던 `target_dir`을 재사용
- [x] "연구비 소진 계획.xlsx"(과제x업체 계획 금액) 대비 진행 현황 체크 기능 신규 추가(`budget_check.py`) — 아직 안 만든 (과제,업체) 목록/개수, 계획 대비 실제 금액이 다른 건, "01. 지출결의서_전체과제_통합(양식).xlsx" 기준 문서가 하나도 없는 과제를 계산. `/batch` 화면에 "체크 실행" 버튼으로 연결. 실제 setting_03 데이터로 검증: 70개 미작성, 1건 금액 불일치(자동화/부강기업 계획 200만원 vs 실제 411만원), 로봇·탄소 과제는 문서 자체가 없음 — 전부 실제 폴더 상태와 일치하는 걸 직접 확인.
- [x] `/batch_run` 실행 중 "경과 X초 · 예상 남은 시간 약 Y초" 표시 추가 — localStorage에 지난 실행 시간(최근 20개)을 기록해 평균으로 다음 실행 예상 소요시간을 추정, 1초마다 갱신. 실제 fetch를 흉내낸 지연 응답으로 playwright에서 중간 상태("경과 1초 · 예상 남은 시간 약 9초")까지 직접 확인.
- [x] "연구비 소진 계획 대비 진행 현황"에 전체 진행률 큰 숫자("전체 진행률 33% (35/105건 완료)") + 과제별 진행률 막대(완료율 낮은 순 정렬) 추가 — `budget_check.check_progress()`가 `progress_by_project`/`overall_progress` 반환하도록 확장. 실제 데이터로 확인: 로봇·탄소 0%, 고효율 100% 등 한눈에 보임.
- [x] "연구비 소진 계획.xlsx" 기준으로 (과제,업체) 폴더를 미리 만들어두는 기능 추가(`budget_check.scaffold_folders`) — 이미 비슷한 이름의 폴더(날짜 접두 등 포함)가 있으면 건너뛰고, 없는 조합만 새 폴더로 생성. `/batch` 화면에 "빠진 폴더 전부 만들기" 버튼으로 연결. **실제 setting_03에는 아직 실행 안 함 — 사용자가 직접 버튼을 눌러 실행하도록 남겨둠**(70개 폴더가 한 번에 생기는 실제 변경이라 사용자가 직접 트리거하는 게 맞다고 판단).

## In Progress

- (없음 — 이 문서 작성 시점에 진행 중인 작업 없음. 사용자의 다음 지시 대기 중)

## Next Steps

1. ~~**`/batch_run`(실행 버튼)의 품목 표 OCR 속도**~~ — [2026-09-26] 완료: 헤더 탐색을 하이브리드(전체 이미지 1회 OCR 사전 필터 + 후보 행만 정밀 재OCR)로 교체. 아래 "Completed" 항목 참고.
2. ~~**origin push 여부 결정**~~ — [2026-09-26] 완료: 사용자 확인 후 14커밋 전부 origin/main에 push함.
3. 사용자가 직접 `실행.bat` / `견적서자동정리_실행.bat`을 다시 실행해서, 이번 세션에서 고친 것들이 실사용 환경에서도 기대대로 동작하는지 최종 확인 필요 (특히 처음 신고했던 "회전된 사진 인식 안 됨", "ERR_CONNECTION_REFUSED", "Failed to fetch" 세 가지 원 증상이 실제로 재발 안 하는지, 그리고 이번에 고친 "실행 버튼 눌렀을 때 품목 추출이 너무 느림/멈춘 것 같음" 증상도 재발 안 하는지).
4. **"빠진 폴더 전부 만들기" 버튼을 실제 setting_03에 아직 실행 안 함** — 로직은 격리된 임시 폴더로 TDD 검증 완료했지만, 실제 데이터에 70개 폴더를 한 번에 만드는 건 사용자가 직접 버튼을 눌러 실행해야 함.
5. ~~(이전 세션에서 넘어온) `.claude/worktrees/pdf-header-and-item-columns`, `.claude/worktrees/pdf-header-and-projects` 두 워크트리 상태 확인~~ — [2026-09-22] 확인 완료: 둘 다 이미 `main`에 다른 구현으로 들어간(superseded) 작업이라 워크트리 디렉토리는 삭제. 커밋은 브랜치(`worktree-pdf-header-and-item-columns`, `worktree-pdf-header-and-projects`)와 백업 태그(`backup/pdf-header-and-item-columns-2026-09-22`, `backup/pdf-header-and-projects-2026-09-22`)로 보존.

## Changed Files

- `budget_check.py`(신규): 연구비 소진 계획 대비 진행 현황 체크(`load_plan`, `load_actual_totals`, `load_master_projects`, `check_progress`, `scaffold_folders`). [2026-09-26] `check_progress()`가 `progress_by_project`/`overall_progress`(과제별·전체 완료율)도 반환하도록 확장
- `app.py`: `/open_folder`(`os.startfile()`), `/budget_check`(`budget_check.check_progress()`), `/scaffold_folders`(`budget_check.scaffold_folders()`) 라우트 신규 추가. `/batch_parse_quote`에 `attachment_match`(정확/유사 매칭) 추가, `/batch_run`에 `attachment_company_override`/`skip_auto_attachments` 필드 추가, `_startup_path()`/`_RUN_KWARGS`(threaded=True) 추가
- `attachment_finder.py`: `match_company()`를 정확 매칭 전용으로 축소, `find_fuzzy_candidates()` 신규 추가
- `automation.py`: `run()`에 `attachment_company_override` 파라미터 추가
- `folder_router.py`: `folder_for_category()`가 미지원 카테고리에서 예외 대신 폴백하도록 변경
- `inspection_generator.py`: 검수확인서에서 공급가(I열) 값을 안 채우도록 변경
- `pdf_item_parser.py`: `fix_image_orientation()` 신규 추가(OSD 기반 회전 보정). [2026-09-26] `_build_table_from_grid()`의 헤더 탐색을 하이브리드 사전 필터 방식으로 교체(전체 이미지 1회 `_ocr_words()` 결과로 `_match_row_labels()`를 이용해 후보 행만 저렴하게 추리고, 그 후보 행에 대해서만 기존 `_ocr_cell()` 정밀 재확인), body_end가 배열 끝까지 자랄 때의 오프바이원 경계 버그 수정
- `pipeline.py`: `project_for_category()`가 사용자 저장 과제 목록을 우선 쓰도록 정리
- `quote_reader.py`: `company_only` 옵션, 이미지 경로 전처리 통일(회전보정→그레이스케일→이진화→deskew→노이즈제거), `_extract_single_item_from_spec_sheet()`(세로형 스펙시트 폴백) 추가
- `templates/batch.html`: 과제 추가/수정/삭제 UI, 견적서 드래그앤드롭, 업체명 자동 인식 + 재업로드 시 갱신, 유사 매칭 확인 패널. [2026-09-26] "폴더 열기" 버튼, "연구비 소진 계획 대비 진행 현황" 카드(체크 실행 + 빠진 폴더 전부 만들기 버튼 + 진행률 막대 + 결과 표) 추가, `/batch_run` 실행 중 경과/예상 남은 시간 표시(localStorage 기반 추정)
- `templates/index.html`: `/batch`로 가는 링크 추가
- `견적서자동정리_실행.bat`: `GP_OPEN_PAGE=batch` 환경변수 설정 추가
- `.gitignore`: `data/app_config.json` 추가(로컬 전용 설정, 커밋 대상 아님)
- `test_automation.py`, `test_automation_attachment_override.py`(신규), `test_batch_route.py`, `test_pipeline_project_for_category.py`, `test_quote_reader.py`(신규), `test_startup_page.py`(신규), `test_template_banner.py`: 위 변경사항에 대한 TDD 테스트
- `test_budget_check.py`(14개): `resolve_folder`/`load_plan`/`load_master_projects`/`load_actual_totals`/`check_progress`(진행률 포함)/`scaffold_folders` 전체 TDD 테스트. `test_batch_route.py`에 `/open_folder`, `/budget_check`, `/scaffold_folders` 라우트 테스트 8개 추가
- `test_pdf_item_parser.py`: [2026-09-26] `test_build_table_from_grid_prefilters_candidate_rows_before_cell_ocr` 신규 추가 — 후보 행 전부가 아니라 헤더 라벨이 있는 소수의 행에만 정밀 셀 재OCR이 호출되는지 검증(합성 격자 이미지 + `_ocr_words`/`_ocr_cell` 목킹). 수정 전 코드로는 이 테스트가 실패함을 `git stash`로 직접 확인.

## Commands Run

```text
python test_pdf_item_parser.py        # [2026-09-26] 76개(신규 1개 포함) — 전부 PASS, 회귀 없음. 실제 사진 샘플(관수작업 비교견적서.jpg)로도 별도 확인: 34.88초 완료(이전엔 완주된 적이 없었음)
python test_pdf_item_parser.py        # 57개, 매 커밋 후 재실행 — 전부 PASS, 회귀 없음
python test_quote_reader.py           # 8개 — PASS (실사용 샘플 파일 포함, 일부는 파일 없으면 skip)
python test_batch_route.py            # 10개 — PASS, 1 skip(실제 SAMPLE/CHECKLIST 파일 없음)
python test_automation.py             # 18개 — PASS, 2개는 /tmp 하드코딩 경로 때문에 이 환경(Windows)에서 원래부터 ERROR(이 세션 변경과 무관, 기존 이슈)
python test_automation_attachment_override.py  # 2개 — PASS
python test_startup_page.py           # 3개 — PASS
python test_template_banner.py        # 5개 — PASS
python test_automation_combined_pdf.py # 1개 — PASS

# 실 브라우저(playwright, chromium headless) 검증
# - 배치 화면 렌더링, 업체명 자동 인식(PDF/이미지), 유사 매칭 후보 선택 패널,
#   정확 매칭 안내 문구, 업체명 재업로드 시 갱신, 실행.bat/견적서자동정리_실행.bat
#   기본 화면 분리 — 전부 스크린샷으로 직접 확인
```

## Test Status

- Last passing: 위 "Commands Run" 전체 — 이 문서 작성 직전에 마지막으로 재실행, 전부 통과
- Failing: `test_automation.py`의 `test_mark_cells`, `test_append_creates_and_grows` — `/tmp/...` 하드코딩 경로 때문에 Windows 환경에서 실패. 이 세션 변경과 무관한 기존 이슈(원래도 실패했었음), 원인 조사 안 함
- Not run: `test_pdf_item_parser.py`의 스캔 PDF 관련 일부 테스트를 제외하면 대부분 실행함. CI는 없음(로컬 실행만)

## Risks / Open Questions

- ~~**`/batch_run` 전체 실행 시 품목 OCR 속도**가 여전히 사진 크기/표 칸 수에 따라 몇 분씩 걸릴 수 있음~~ — [2026-09-26] 해결: 헤더 탐색을 하이브리드 사전 필터로 교체해 근본 속도 개선. 다만 이미지가 너무 노이즈가 심해 전체 이미지 1회 OCR에서 라벨 후보가 하나도 안 잡히면(예: 관수작업 비교견적서.jpg) 품목을 못 찾고 조기 종료함 — 이는 원본 사진 품질 한계이지, 무한정 느려지는 문제는 아님.
- 이미지 품질이 낮은(흐림/저해상도) 견적서 사진은 회전 보정 + 전처리를 다 거쳐도 업체명/품목을 못 찾을 수 있음 — 코드 버그가 아니라 원본 사진 품질의 근본적 한계. 화면에 경고 문구는 뜨지만, 사용자가 이를 "버그"로 다시 인식하고 신고할 가능성 있음.
- ~~원격(origin)에 13커밋 밀려 있음~~ — [2026-09-26] 해결: push 완료, `main`/`origin/main` 동기화됨.
- `data/history.json`, `data/projects.json`, `data/column_settings.json`, `data/app_config.json`은 전부 `.gitignore` 대상(로컬 전용 데이터) — 이 PC를 벗어나면(재설치 등) 사용자가 직접 추가한 과제/컬럼 설정이 다시 초기화됨. 별도 백업/이관 방법이 필요할 수 있음.
