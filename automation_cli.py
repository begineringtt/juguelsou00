"""명령줄에서 자동화 1건 실행.

예)
  python automation_cli.py --quote "견적서.pdf" --category 고효율 --company "유진철강산업㈜" \
      --setting03 "D:\\claude_personal\\setting_03" --inspector "유찬희 책임연구원" \
      --inspect-date 2026-09-21 --biz "사업자등록증.jpg" --bank "통장사본.jpg"

--dry-run 을 주면 목표 폴더로 옮기지 않고 임시 폴더에 만든 뒤 계획만 출력한다.
"""

import argparse
import sys

import automation
import folder_router


def main(argv=None):
    ap = argparse.ArgumentParser(description="견적서 -> 지출결의서/검수확인서 자동 생성·정리")
    ap.add_argument("--quote", required=True, help="견적서 파일(PDF/JPG/PNG/XLSX)")
    ap.add_argument("--category", required=True,
                    help="과제 카테고리: " + ", ".join(folder_router.CATEGORY_CHOICES))
    ap.add_argument("--company", required=True, help="업체명")
    ap.add_argument("--setting03", required=True, help="setting_03 루트 경로")
    ap.add_argument("--inspector", default="", help="검수자 성명")
    ap.add_argument("--inspect-date", default=None, help="검수일 YYYY-MM-DD")
    ap.add_argument("--requester", default="", help="청구인")
    ap.add_argument("--product", default=None, help="팁스 등 폴더명에 품목 접미가 필요할 때")
    ap.add_argument("--biz", default=None, help="사업자등록증 파일")
    ap.add_argument("--bank", default=None, help="통장사본 파일")
    ap.add_argument("--tax", default=None, help="전자세금계산서 파일")
    ap.add_argument("--statement", default=None, help="거래명세서 파일")
    ap.add_argument("--no-pdf", action="store_true", help="PDF 변환 건너뜀")
    ap.add_argument("--dry-run", action="store_true", help="목표 폴더로 옮기지 않고 계획만")
    args = ap.parse_args(argv)

    attachments = {}
    if args.biz:
        attachments["사업자등록증"] = args.biz
    if args.bank:
        attachments["통장사본"] = args.bank
    if args.tax:
        attachments["전자세금계산서"] = args.tax
    if args.statement:
        attachments["거래명세서"] = args.statement

    m = automation.run(
        args.quote, args.category, args.company, args.setting03,
        inspector=args.inspector, inspect_date=args.inspect_date,
        requester=args.requester, product=args.product,
        attachments=attachments, place=not args.dry_run,
        make_pdf=not args.no_pdf,
    )

    print("=" * 60)
    print(f"업체       : {m['company']}")
    print(f"카테고리   : {m['category']}  ->  폴더 '{m['category_folder']}'")
    print(f"대상 폴더  : {m['target_folder_name']}  ({'신규 생성' if m['target_folder_is_new'] else '기존 폴더'})")
    print(f"품목 수    : {m['item_count']}   견적 총액: {m['total_supply']:,}원")
    print(f"견적 인식  : {m['quote_source']}")
    if m.get("pdf_error"):
        print(f"[PDF] {m['pdf_error']}")
    if m["warnings"]:
        print("[주의] " + " / ".join(m["warnings"]))
    print("-" * 60)
    for f in m.get("placed_files", m["generated_xlsx"] + m["generated_pdf"]):
        print("  파일:", f)
    ck = m.get("checklist")
    if ck:
        if ck["misses"]:
            print("[체크리스트] " + " / ".join(ck["misses"]))
        else:
            print(f"[체크리스트] {len(ck['marked'])}개 셀 O 표시")
    if m.get("report_path"):
        print("[보고서]", m["report_path"])
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
