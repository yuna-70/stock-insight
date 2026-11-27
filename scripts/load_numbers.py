"""
실적 공시의 숫자를 DB(disclosure_numbers)에 저장하는 스크립트

disclosures에서 type='실적'인 공시를 꺼내, 원문 표를 파싱해서 저장한다.

두 단계로 나눈다:
  1) 모으기: DART 요청 + 파싱 (느림, DB 안 씀)
  2) 저장하기: 공시마다 지우고 다시 넣기 (빠름, 한 번에 commit)
→ 느린 네트워크를 기다리는 동안 DB 연결을 붙잡지 않고,
  중간에 실패하면 아무것도 반영되지 않는다 (반쯤 저장된 상태 없음)

중복 방지는 두 겹: 코드(지우고 다시 넣기) + DB(UNIQUE rcept_no, item, scope, period)

실행 전: load_disclosures.py로 disclosures가 채워져 있어야 함 (FK)
실행:    python scripts/load_numbers.py  (저장소 맨 위에서)
"""

import os

import psycopg
from dotenv import load_dotenv

# 같은 scripts 폴더의 파싱 함수 재사용 (import할 때 explore_numbers의 main은 실행 안 됨)
from explore_numbers import fetch_table_rows, parse_earnings

SELECT_SQL = "SELECT rcept_no FROM disclosures WHERE type = '실적' ORDER BY rcept_dt;"
DELETE_SQL = "DELETE FROM disclosure_numbers WHERE rcept_no = %s;"
INSERT_SQL = (
    "INSERT INTO disclosure_numbers (rcept_no, item, scope, period, value, unit) "
    "VALUES (%s, %s, %s, %s, %s, %s);"
)


def get_earnings_rcept_nos(database_url: str) -> list[str]:
    """DB에서 실적 공시의 접수번호 목록을 꺼낸다."""
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(SELECT_SQL)
            return [row[0] for row in cur.fetchall()]  # ('2026...',) → '2026...'


def collect_numbers(api_key: str, rcept_nos: list[str]) -> dict[str, list[tuple]]:
    """1단계: 공시마다 원문을 받아 파싱하고, {접수번호: [DB용 6칸 튜플, ...]}로 모은다.

    DB는 쓰지 않는다. 표 모양·단위가 이상한 공시는 건너뛰고 나머지는 계속.
    """
    collected = {}
    for rcept_no in rcept_nos:
        try:
            rows = fetch_table_rows(api_key, rcept_no)
            results = parse_earnings(rows)  # (item, scope, period, value, unit)
        except ValueError as e:
            print(f"[건너뜀] {rcept_no}: {e}")
            continue

        # 앞에 rcept_no를 붙여 DB 컬럼 순서(6칸)에 맞춤
        collected[rcept_no] = [(rcept_no, *r) for r in results]
        print(f"[파싱] {rcept_no}: {len(results)}개")

    return collected


def save_numbers(database_url: str, collected: dict[str, list[tuple]]) -> int:
    """2단계: 공시마다 예전 숫자를 지우고 새로 넣는다. DB 전체 줄 수를 돌려준다.

    모든 공시를 하나의 트랜잭션으로 처리 → 중간에 에러가 나면 전부 취소
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            for rcept_no, params in collected.items():
                cur.execute(DELETE_SQL, (rcept_no,))
                cur.executemany(INSERT_SQL, params)

            cur.execute("SELECT COUNT(*) FROM disclosure_numbers;")
            total = cur.fetchone()[0]

        conn.commit()

    return total


def main():
    load_dotenv()
    api_key = os.getenv("DART_API_KEY")
    database_url = os.getenv("DATABASE_URL")
    if not api_key or not database_url:
        raise SystemExit(".env에서 DART_API_KEY 또는 DATABASE_URL을 찾을 수 없습니다.")

    rcept_nos = get_earnings_rcept_nos(database_url)
    print(f"[대상] 실적 공시 {len(rcept_nos)}개")

    collected = collect_numbers(api_key, rcept_nos)        # 1단계: 모으기
    if not collected:
        raise SystemExit("저장할 숫자가 없습니다.")

    new_count = sum(len(p) for p in collected.values())
    total = save_numbers(database_url, collected)          # 2단계: 저장하기

    print(f"[완료] 공시 {len(collected)}개, 숫자 {new_count}개 저장 → DB 전체 {total}개")


if __name__ == "__main__":
    main()