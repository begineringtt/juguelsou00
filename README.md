# 지출결의서 자동 생성기

회사 양식(지출결의서, `GP-A-001`)을 그대로 채운 `.xlsx` 파일을 웹 폼 입력만으로
자동 생성해주는 로컬 Flask 앱입니다. 견적서 PDF를 업로드하면 품목/업체명/내용(제목)을
자동으로 인식해서 채워주는 기능도 있습니다.

## 요구사항

- Python 3.10 이상
- (Windows) 인터넷 브라우저 (앱 실행 시 자동으로 열립니다)

## 설치

```bash
git clone <이 저장소의 clone 주소>
cd expense_form_app
pip install -r requirements.txt
```

## 실행

```bash
python app.py
```

실행하면 브라우저가 자동으로 `http://127.0.0.1:5000` 을 열어줍니다.

Windows에서는 `실행.bat` 파일을 더블클릭해도 동일하게 실행됩니다 (위 `pip install`은
최초 1회만 하면 됩니다).

## 사용법

1. 기본 정보(업체명/발의일/지출일/내용 등)를 입력합니다.
2. "과제 정보"에서 기존 과제를 선택하거나 새 과제를 직접 추가/수정할 수 있습니다.
3. 품목을 직접 입력하거나, 견적서 PDF를 업로드/드래그하면 품목·업체명·내용(제목)이
   자동으로 인식되어 채워집니다 (인식 결과는 적용 전에 화면에서 확인/수정 가능합니다).
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
app.py              Flask 라우트
generator.py         엑셀 생성 로직 (template_files/base_template.xlsx 채우기)
history_store.py     입력 이력/과제 프리셋 로컬 저장(JSON)
pdf_item_parser.py    견적서 PDF에서 품목/업체명/내용(제목) 인식
templates/index.html  웹 UI
template_files/       회사 지출결의서 원본 엑셀 양식
```
