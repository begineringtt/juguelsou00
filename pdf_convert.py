"""xlsx -> pdf 변환 (LibreOffice headless).

회사 PC에는 LibreOffice가 없을 수 있으므로, 이 모듈은 변환기를 자동 탐색하고
없으면 명확한 예외를 던진다. (이 클라우드 세션에는 soffice가 설치돼 있음)

주의: LibreOffice 렌더링은 Excel과 미세하게 다를 수 있어, 생성 결과는 육안으로
한 번 확인하는 것을 권장한다.
"""

import os
import shutil
import subprocess
import tempfile


class ConverterUnavailableError(RuntimeError):
    pass


def _find_soffice():
    for name in ("libreoffice", "soffice"):
        path = shutil.which(name)
        if path:
            return path
    # Windows 기본 설치 경로 후보
    for cand in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if os.path.isfile(cand):
            return cand
    return None


def xlsx_to_pdf(xlsx_path, out_dir=None, timeout=180):
    """xlsx_path 를 같은 폴더(또는 out_dir)에 동일 이름 .pdf 로 변환하고 그 경로 반환."""
    soffice = _find_soffice()
    if not soffice:
        raise ConverterUnavailableError(
            "LibreOffice(soffice)를 찾을 수 없습니다. PDF 변환을 건너뜁니다."
        )
    xlsx_path = os.path.abspath(xlsx_path)
    out_dir = os.path.abspath(out_dir or os.path.dirname(xlsx_path))
    os.makedirs(out_dir, exist_ok=True)

    # 동시 실행 충돌을 피하려고 프로필 디렉터리를 매번 임시로 분리
    with tempfile.TemporaryDirectory() as profile:
        # Windows 경로(백슬래시)를 그대로 file:// 뒤에 붙이면 잘못된 URI가 되어
        # LibreOffice가 부트스트랩에 실패한다(예: "bootstrap.ini가 손상됨" 오류).
        # 슬래시로 바꾸고 file:/// 형태로 정규화해야 한다.
        profile_uri = "file:///" + profile.replace("\\", "/").lstrip("/")
        cmd = [
            soffice, "--headless", "--norestore", "--nolockcheck",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to", "pdf:calc_pdf_Export",
            "--outdir", out_dir, xlsx_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    pdf_path = os.path.join(out_dir, os.path.splitext(os.path.basename(xlsx_path))[0] + ".pdf")
    if not os.path.isfile(pdf_path):
        raise RuntimeError(
            f"PDF 변환 실패: {proc.stderr.decode('utf-8', 'ignore')[:500]}"
        )
    return pdf_path


def available():
    return _find_soffice() is not None
