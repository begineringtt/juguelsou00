# 지출결의서 앱 — 작업 진행 현황

최종 갱신: 2026-09-01
저장소: D:\claude_personal\setting_01\expense_form_app

## 1. 현재 변경된 파일

- 작업 트리(working tree) 클린 상태 — 커밋되지 않은 변경 없음 (`git status --short` 결과 없음).
- `main` 브랜치가 `origin/main` 대비 **8커밋 앞선 상태** (아직 push 안 함).
- 이번 세션에서 `main`에 병합된 커밋 3개:
  - `e8498fb` — feat: add QUANTITY/PRICE header synonyms with fuzzy fallback for table header matching
  - `7d21523` — feat: recover borderless item-name column via coordinate-based crop
  - `2fa20b7` — Merge worktree-pdf-header-matching-improvements
- 위 커밋들이 건드린 파일: `pdf_item_parser.py`, `test_pdf_item_parser.py`

## 2. 지금까지 대화에서 결정한 내용

- `docs/superpowers/plans/2026-08-31-pdf-header-matching-improvements.md` 계획을 subagent-driven-development 방식으로 실행하기로 함 (사용자 승인, "응").
- 격리 작업을 위해 git worktree(`.claude/worktrees/pdf-header-matching-improvements`)를 만들어 작업 — 작업 완료 후 `main`에 로컬 merge, worktree/브랜치는 삭제.
- **원격 push는 하지 않기로 함** — 사용자가 "main에 로컬 merge (추천)" 옵션을 선택함. `origin`에 반영 여부는 별도 결정 필요.
- 세부 룰링(ruling) 3건:
  1. Task 2 브리프의 `_find_best_table` 줄 번호는 Task 1 반영 후 밀릴 수 있어, 줄 번호 대신 함수명으로 위치를 찾도록 구현자에게 지시.
  2. Task 2 리뷰어가 남긴 "⚠️ 테스트 재실행 안 함" 항목은 컨트롤러가 직접 `task-2-report.md`의 테스트 출력을 확인해 해소 — 실제 결함 아님.
  3. 최종 리뷰의 Minor 발견 3건(크롭 세로 경계 가정, 공백 텍스트가 `""`로 남는 엣지케이스, 테스트의 중복 로컬 import)은 병합을 막을 사안이 아니라고 판단해 그대로 둠.
- `docs/superpowers/specs/2026-08-31-current-features-and-status.md`에 남아있던 열린 질문 중, 이번 세션은 **PDF 헤더 매칭 개선(A항목)만** 다뤘음 — B/C/D항목과 `2026-08-21` 컬럼 커스터마이징은 범위 밖으로 명시적으로 제외.

## 3. 완료한 작업

- [x] **Task 1**: `HEADER_SYNONYMS`에 `QUANTITY`/`PRICE` 동의어 추가, `find_header_row`/`map_table_columns`에 `match_field_fuzzy` fallback 연결 (TDD, task 리뷰 승인, fix loop 없음)
- [x] **Task 2**: `_recover_missing_name_column` 순수 함수 추가 (좌표 크롭으로 테두리선 없는 품목명 칸 복구), `_find_best_table`을 `find_tables()+.extract()` 방식으로 교체 (TDD, task 리뷰 승인, fix loop 없음)
- [x] 최종 whole-branch 리뷰 (opus 모델) — "Ready to merge: Yes", Critical/Important 없음
- [x] `main`에 로컬 merge (`2fa20b7`), merge 후 전체 테스트 재실행 — 통과
- [x] SDD 워크스페이스(`.superpowers/sdd/2026-08-31-pdf-header-matching-improvements`) 및 작업용 worktree/브랜치 정리(삭제)

## 4. 남은 작업

- [ ] **origin에 push 여부 결정** — 현재 `main`이 origin보다 8커밋 앞서 있음 (이번 세션 3개 + 이전 세션 5개). 확인 필요: 원격에 언제 반영할지.
- [ ] `docs/superpowers/specs/2026-08-31-current-features-and-status.md` §6 열린 질문 중 아직 처리 안 된 것들:
  - `2026-08-05` 스펙을 "구현 대기"로 둘지, 실제 구현 방식을 반영해 스펙 문서를 갱신할지 결정
  - `2026-08-21`(품목 컬럼 커스터마이징) 착수 여부/우선순위 — 설계만 있고 미착수 상태 그대로임
  - 문서화 안 된 기능들(PDF 제목 인식, 초과 행 처리, rev.2 템플릿 전환)에 대한 사후 스펙 작성 여부
  - `progress.md`(태스크 추적 로그) 관리를 앞으로 어떻게 이어갈지 — 이번 문서가 그 재개 시도
- [ ] `test_parse_pdf_route.py`의 기존 실패 — 확인 필요 (아래 6번 참고, 원인 미조사)
- [ ] `.claude/worktrees/pdf-header-and-item-columns`, `.claude/worktrees/pdf-header-and-projects` 두 worktree의 현재 상태/필요 여부 — 확인 필요 (이번 세션에서 다루지 않음, 방치된 것인지 진행 중인지 불명)

## 5. 실행한 명령과 테스트 결과

Task 1/2 작업 및 병합 전후로 실행한 테스트 (모두 워크트리 또는 `main`에서 실행):

| 명령 | 결과 |
|---|---|
| `python test_pdf_item_parser.py` | PASS (baseline 39개 → Task1 이후 51개 → Task2 이후 57개, 8개 실제 샘플 PDF 포함) |
| `python test_generator.py` | PASS |
| `python test_column_layout.py` | PASS |
| `python test_item_table_layout.py` | PASS |
| `python test_history_store_merge.py` | PASS |
| `python test_read_seed.py` | PASS |
| `python test_app_refresh_route.py` | PASS |
| `python test_template_banner.py` | PASS |
| merge 후 위 6개 핵심 테스트 재실행 (`main`, `2fa20b7`) | PASS |

## 6. 실행하지 못한 검증

- **`test_parse_pdf_route.py`가 실패함** — 단, base 커밋(`dcc7e93`)에서도 동일하게 실패하는 것을 확인해 "이번 변경으로 인한 회귀는 아님"까지만 확인함. **실패의 근본 원인은 조사하지 않았음 — 확인 필요.**
- 브라우저에서 실제 Flask 앱(`/parse_pdf` 라우트)에 문제의 PDF(`견적서_20260721(그린플러스_IR Cut_8월).pdf`)를 업로드해 UI 상에서 정상 동작하는지는 **수동으로 확인하지 않음** — 유닛/통합 테스트 수준까지만 검증.
- 엑셀 렌더링(LibreOffice/Excel 육안 확인)은 이 환경에 해당 프로그램이 없어 애초에 불가능 — openpyxl 구조 검증으로만 대체 (기존 방식과 동일, 이번 세션에서 새로 발생한 제약 아님).
- `origin`에 push하지 않았으므로 원격 CI(있다면)나 다른 협업자 환경에서의 검증은 이루어지지 않음.
