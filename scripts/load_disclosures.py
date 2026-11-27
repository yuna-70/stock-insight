"""
공시 목록을 DB(disclosures)에 저장하는 스크립트

정한 회사들의 기간 내 공시를 DART list.json으로 받아서 disclosures 테이블에 넣는다.
rcept_no가 이미 있으면 건너뛴다(DO NOTHING) → 여러 번 실행해도 중복 없음.

실행 전: docker ps로 stock-insight-db가 Up인지, load_corps.py로 corps가 채워졌는지 확인
실행:    python scripts/load_disclosures.py  (저장소 맨 위에서)
"""

import os
from datetime import datetime

import psycopg
import requests
from dotenv import load_dotenv

# ── 설정 ─────────────────────────────────────────────
# 수집할 회사코드 (삼성전자, SK하이닉스). corps에 있는 회사여야 FK 에러가 안 난다
CORP_CODES = ["00126380", "00164779"]

# 수집 기간 (YYYYMMDD)
BGN_DE = "20260825"
END_DE = "20261125"

LIST_URL = "https://opendart.fss.or.kr/api/list.json"
PAGE_COUNT = 100  # 한 번에 받을 최대 개수 (DART 최대 100)


def classify(report_nm: str) -> str:
    """공시명을 보고 v1 종류를 붙인다.

    우리 분류 이름이 아니라 DART 제목에 실제로 나오는 '핵심 단어'로 찾는다.
    if/elif는 처음 맞는 것 하나만 돌려주므로 순서가 결과에 영향을 준다.
    """
    if "영업(잠정)실적" in report_nm:
        return "실적"
    elif "장래사업" in report_nm:
        return "회사계획"
    elif "배당" in report_nm or "자기주식" in report_nm:
        return "주주환원"
    else:
        return "기타"


def fetch_disclosures(api_key: str, corp_code: str) -> list[tuple]:
    """회사 하나의 기간 내 공시를 전부 받아서 DB에 넣을 튜플 리스트로 돌려준다.

    공시가 100개를 넘으면 여러 페이지로 나눠 오기 때문에 마지막 페이지까지 돈다.
    실패하면 빈 리스트를 돌려준다 (다른 회사 수집은 계속되도록).
    """
    rows = []
    page_no = 1

    while True:
        response = requests.get(
            LIST_URL,
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": BGN_DE,
                "end_de": END_DE,
                "page_count": PAGE_COUNT,
                "page_no": page_no,
            },
            timeout=10,  # DART가 응답이 없을 때 무한정 기다리지 않게
        )
        data = response.json()

        # 000이 아니면 이 회사는 실패 → 이유를 보여주고 빈 리스트 (다른 회사는 계속)
        # (013 = 기간 내 공시 없음도 여기로 온다)
        if data["status"] != "000":
            print(f"[건너뜀] {corp_code}: {data['status']} {data['message']}")
            return []

        for item in data["list"]:
            report_nm = item["report_nm"].strip()  # 이름 뒤에 공백이 붙어 옴
            rcept_dt = datetime.strptime(item["rcept_dt"], "%Y%m%d").date()  # 글자 → 날짜
            # 튜플 순서 = INSERT 컬럼 순서
            rows.append((item["rcept_no"], corp_code, report_nm, rcept_dt, classify(report_nm)))

        # 마지막 페이지면 끝, 아니면 다음 페이지
        if page_no >= data["total_page"]:
            break
        page_no += 1

    print(f"[수집] {corp_code}: {len(rows)}개 (DART total_count {data['total_count']})")
    return rows


def save_disclosures(database_url: str, rows: list[tuple]) -> int:
    """공시 튜플들을 DB에 저장하고, 실제로 새로 들어간 개수를 돌려준다."""
    sql = (
        "INSERT INTO disclosures (rcept_no, corp_code, report_nm, rcept_dt, type) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (rcept_no) DO NOTHING;"  # 공시는 고쳐지지 않고 정정 공시가 새로 올라옴 → 있으면 건너뜀
    )

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # DO NOTHING이라 '보낸 개수 ≠ 들어간 개수'. 전후 개수 차이로 정직하게 센다
            cur.execute("SELECT COUNT(*) FROM disclosures;")
            before = cur.fetchone()[0]

            cur.executemany(sql, rows)

            cur.execute("SELECT COUNT(*) FROM disclosures;")
            after = cur.fetchone()[0]

        conn.commit()  # 안 하면 끝날 때 전부 취소됨

    return after - before


def main():
    load_dotenv()
    api_key = os.getenv("DART_API_KEY")
    database_url = os.getenv("DATABASE_URL")

    if not api_key or not database_url:
        raise SystemExit(".env에서 DART_API_KEY 또는 DATABASE_URL을 찾을 수 없습니다.")

    # 회사마다 받아서 하나의 리스트로 합치기
    rows = []
    for corp_code in CORP_CODES:
        rows.extend(fetch_disclosures(api_key, corp_code))

    if not rows:
        raise SystemExit("저장할 공시가 없습니다.")

    # 넣기 전 검증: 개수 + 샘플 한 줄 (칸이 뒤바뀐 실수를 잡으려고)
    print(f"[합계] {len(rows)}개")
    print(f"[샘플] {rows[0]}")

    inserted = save_disclosures(database_url, rows)
    print(f"[저장] 새로 {inserted}개 저장, {len(rows) - inserted}개는 이미 있어서 건너뜀")


# 이 파일을 직접 실행할 때만 main()을 돈다
# (다른 파일에서 classify 같은 함수만 import할 때는 수집이 실행되지 않음)
if __name__ == "__main__":
    main()