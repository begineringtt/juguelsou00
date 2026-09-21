# 지출결의서 자동 생성기

회사 양식(지출결의서, `GP-A-001`)을 그대로 채운 `.xlsx` 파일을 웹 폼 입력만으로
자동 생성해주는 로컬 Flask 앱입니다. 견적서 PDF를 업로드하면 품목/업체명/내용(제목)을
자동으로 인식해서 채워주는 기능도 있습니다.

## 요구사항

- Python 3.10 이상
- (Windows) 인터넷 브라우저 (앱 실행 시 자동으로 열립니다)

## 설치 및 실행

### Windows (Python 없이도 OK)

1. 이 저장소를 다운로드/클론합니다.
2. `설치.bat` 파일을 더블클릭합니다.
   - Python이 없으면 자동으로 설치를 시도합니다(winget 사용). 이 경우 설치 후
     창을 닫고 `설치.bat`을 한 번 더 실행해달라는 안내가 뜹니다(새로 설치된
     Python은 같은 창에서 바로 인식되지 않기 때문입니다).
   - Python이 이미 있으면 바로 필요한 패키지를 설치하고 프로그램을 실행합니다.
3. 다음부터는 `실행.bat`만 더블클릭하면 됩니다.

### 직접 설치(Mac/Linux 포함)

```bash
git clone <이 저장소의 clone 주소>
cd expense_form_app
pip install -r requirements.txt
python app.py
```

실행하면 브라우저가 자동으로 `http://127.0.0.1:5000` 을 열어줍니다.

## 사용법

1. 기본 정보(업체명/발의일/지출일/내용 등)를 입력합니다.
2. "과제 정보"에서 기존 과제를 선택하거나 새 과제를 직접 추가/수정할 수 있습니다.
3. 품목을 직접 입력하거나, 견적서 PDF를 업로드/드래그하면 품목·업체명·내용(제목)이
   자동으로 인식되어 채워집니다 (인식 결과는 적용 전에 화면에서 확인/수정 가능합니다).
   텍스트 레이어가 없는 스캔/팩스 PDF는 내장된 OCR(Tesseract, 한국어+영어)로
   자동 인식을 시도합니다 - 화질이 나쁜 팩스는 표 인식률이 떨어질 수 있으니
   인식 결과를 미리보기 이미지와 꼭 대조해주세요. OCR 엔진은 `tesseract_bin/`에
   함께 들어있어 별도 설치가 필요 없습니다.
4. "엑셀 파일 생성" 버튼을 누르면 완성된 `.xlsx` 파일이 다운로드됩니다.

한 번 입력한 값(업체명/과제/문구 등)은 `data/` 폴더에 로컬로 저장되어 다음 실행 때
드롭다운으로 다시 선택할 수 있습니다. 이 폴더는 사용자별 데이터라서 git에는 포함되지
않습니다(`.gitignore` 참고).

## 테스트

```bash
python test_column_layout.py
python test_item_table_layout.py
python test_generator.py
python test_history_store_merge.py
python test_read_seed.py
python test_pdf_item_parser.py
python test_pdf_convert.py
python test_combined_pdf.py
python test_pipeline_combined_pdf.py
python test_automation_combined_pdf.py
```

`test_pdf_item_parser.py`의 일부 테스트는 사내 견적서 PDF 샘플(`PDF_read/` 폴더, git에
포함되지 않음)이 있어야 실행되며, 없으면 자동으로 건너뜁니다(SKIP).

## Windows 실행 파일(.exe)로 빌드하기 (선택)

```bash
pip install pyinstaller
pyinstaller 지출결의서생성기.spec
```

`dist/지출결의서생성기.exe` 가 생성됩니다.

## 폴더 구조

```
app.py              Flask 라우트 (지출결의서 단독 + /batch 자동 정리)
generator.py         엑셀 생성 로직 (template_files/base_template.xlsx 채우기)
history_store.py     입력 이력/과제 프리셋 로컬 저장(JSON)
pdf_item_parser.py    견적서 PDF에서 품목/업체명/내용(제목) 인식 (스캔 PDF는 OCR로 대체)
templates/index.html  웹 UI (지출결의서 단독 생성)
templates/batch.html  웹 UI (견적서 → 지출결의서·검수확인서 자동 정리)
template_files/       회사 지출결의서/검수확인서 원본 엑셀 양식
tesseract_bin/         스캔 PDF OCR용 Tesseract 실행 파일 + 한국어/영어 언어팩(번들)

# 자동 정리 파이프라인 (신규)
quote_reader.py       견적서 통합 리더 (PDF 표/좌표복원, JPG·PNG OCR, XLSX 직접 읽기)
inspection_generator.py  검수확인서 생성 (template_files/inspection_template.xlsx 채우기)
folder_router.py      과제 카테고리 → setting_03 폴더 매핑 + 업체 하위폴더 명명 규칙 학습
checklist_updater.py  연구비 업로드 체크리스트 갱신(O 표시, 다른 이름 저장)
report_writer.py      처리이력 보고서(누적 로그) 작성
pdf_convert.py        xlsx → pdf (LibreOffice headless)
combined_pdf.py        견적서·지출결의서·사업자등록증·통장사본을 한 PDF로 병합(통합 출력)
pipeline.py           견적서 1건 → 문서 생성·PDF·통합출력·매니페스트
automation.py         상위 오케스트레이션 (폴더 배치 + 첨부 자동복사 + 체크리스트 + 보고서)
attachment_finder.py  setting_03("서버")에서 업체별 통장사본·사업자등록증 색인/검색
automation_cli.py     명령줄 실행 진입점
```

## 견적서 → 지출결의서·검수확인서 자동 정리 (신규 기능)

견적서 한 장을 올리면 다음을 한 번에 처리합니다.

1. 견적서(PDF/JPG/PNG/XLSX)에서 품목·수량·단가·중량·공급가를 인식
   - 표 격자선이 없는 견적서는 단어 좌표로 열을 복원 (예: 각파이프 견적서)
   - JPG/PNG는 내장 Tesseract OCR, XLSX는 시트에서 직접 읽음
2. **지출결의서**(기존 GP-A-001 양식)와 **검수확인서**(회사 제공 양식) 생성
3. 둘 다 **PDF로 변환** (LibreOffice 필요 — 없으면 xlsx만 저장)
4. 과제 카테고리에 맞는 `setting_03` 하위 폴더로 정리
   - `중동` 카테고리는 자동으로 **IR 폴더**로 갑니다.
   - 업체 하위폴더 이름은 그 카테고리의 기존 폴더 규칙(날짜형/N차형/평문)을 보고 자동 결정
   - 견적서를 함께 정리
   - **통장사본·사업자등록증은 setting_03의 기존 업체 폴더("서버")에서 업체명으로 자동
     검색해 복사** (`attachment_finder.py`). 폴더명이 곧 업체명이라는 점을 이용하며,
     날짜·차수 접두("2026-09-20 유진철강", "3차 유진철강")가 붙어 있어도 매칭합니다.
     직접 올린 파일이 있으면 그게 우선합니다.
5. **체크리스트**(`연구비 파일 업로드 체크용_*.xlsx`)의 해당 칸을 O로 갱신해 다른 이름으로 저장
6. **처리이력 보고서**(`체크리스트/처리이력_보고서.xlsx`)에 한 줄 기록
7. **통합 출력**: 견적서 → 지출결의서 → 사업자등록증 → 통장사본 순서로 한 PDF에 병합한
   `통합출력_{업체명}_{카테고리}.pdf`를 대상 폴더에 함께 생성 (검수확인서는 제외 —
   서명/확인이 필요해 별도로 처리). 일부 파일이 없거나 변환에 실패해도(예: LibreOffice
   미설치로 xlsx 변환 불가) 나머지만으로 병합하고, 못 넣은 파일과 이유는 처리 결과에
   남는다. CLI에서는 `--no-combined-pdf`로 끌 수 있다.

### 웹에서 쓰기

앱 실행 후 `http://127.0.0.1:5000/batch` 로 이동 → setting_03 경로/카테고리/업체명을
입력하고 견적서를 올린 뒤 실행. ‘미리보기(정리 안 함)’로 먼저 결과를 확인할 수 있습니다.

### 명령줄에서 쓰기

```bash
python automation_cli.py --quote "견적서.pdf" --category 고효율 --company "유진철강산업㈜" \
    --setting03 "D:\claude_personal\setting_03" \
    --inspector "유찬희 책임연구원" --inspect-date 2026-09-21 \
    --biz "사업자등록증.jpg" --bank "통장사본.jpg"      # --dry-run 으로 계획만 확인
```

### PDF 변환 준비물

xlsx → pdf 변환에는 **LibreOffice**가 필요합니다(무료). 설치돼 있지 않으면 xlsx만
저장되고 안내 메시지가 표시됩니다. Windows는 https://ko.libreoffice.org 에서 설치하면
자동으로 인식됩니다.

### 참고

- 업체명은 견적서 로고(이미지)에만 있는 경우가 많아 자동 인식이 비어 있을 수 있습니다.
  화면에서 업체명을 직접 입력/확인하세요(폴더명·검수확인서·체크리스트 매칭 기준).
- 검수확인서의 ‘제품 사진’ 칸은 비워 두므로, 필요 시 사진을 수기로 붙여 넣으세요.
- 체크리스트에 아직 없는 신규 업체는 오표기 대신 “찾지 못함”으로 안내합니다.
