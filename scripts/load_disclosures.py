"""
공시 목록을 DB(disclosures)에 저장하는 스크립트

정한 회사들의 최근 3개월 공시를 list.json으로 받아서 disclosures 테이블에 넣는다.
rcept_no가 이미 있으면 건너뛴다 → 여러 번 실행해도 중복 없음.
"""

# 표준 라이브러리: os, datetime(datetime) 가져오기
import os
from datetime import datetime

# 외부 라이브러리: psycopg, requests, load_dotenv 가져오기
import psycopg
import requests
from dotenv import load_dotenv

# ── 설정 ─────────────────────────────────
# 수집할 회사코드 리스트: 삼성전자 "00126380", SK하이닉스 "00164779"
CORP_CODES = ["00126380", "00164779"]

# 기간: BGN_DE = "20260825", END_DE = "20261125"
BGN_DE = "20260825"
END_DE = "20261125"

# ── 공시 종류 나누기 함수 ───────────────────
# 함수 이름: classify, 매개변수: report_nm
def classify(report_nm: str) -> str:
    # 표대로 "실적" / "회사계획" / "주주환원" / "기타" 중 하나를 return
    if "영업(잠정)실적" in report_nm:
        return "실적"
    elif "장래사업" in report_nm:
        return "회사계획"
    elif "배당" in report_nm or "자기주식" in report_nm:
        return "주주환원"
    else:
        return "기타"

# ── 1. 키와 DB 주소 불러오기 ─────────────── (load_corps.py와 같음)
load_dotenv()
API_KEY = os.getenv("DART_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not API_KEY or not DATABASE_URL:
    raise SystemExit("키나 주소를 찾을 수 없습니다.")

# ── 2. 회사마다 공시 목록 받아서 rows에 모으기 ──
# 빈 리스트 rows
rows = []

# 회사코드 리스트를 하나씩 돌면서
for corp_code in CORP_CODES:
    # list.json 요청 (explore_disclosures.py와 같은 파라미터, corp_code만 바꿔서)
    # json → data, status가 "000"이 아니면 메시지 보여주고 이 회사는 건너뛰기 (continue)
    response = requests.get(
        url="https://opendart.fss.or.kr/api/list.json",
        params={
            "crtfc_key": API_KEY,
            "corp_code": corp_code,       
            "bgn_de": BGN_DE,           
            "end_de": END_DE,          
            "page_count": 100,
        },
    )

    data = response.json()

    if data["status"] != "000":
        print(f"{corp_code} 실패: {data['message']}")
        continue

    # data["list"]를 하나씩 돌면서
    for item in data["list"]:
        # report_nm 꺼내서 strip
        report_nm = item["report_nm"].strip()
        # rcept_dt 글자를 날짜로 바꾸기
        rcept_dt = datetime.strptime(item["rcept_dt"], "%Y%m%d").date()
        # (rcept_no, corp_code, report_nm, rcept_dt, classify(report_nm)) 튜플을 rows에 추가
        rows.append((item['rcept_no'], corp_code, report_nm, rcept_dt, classify(report_nm)))

# 개수 + 샘플 한 줄 출력 (검증!)
print(f"[수집] 공시 {len(rows)}개")
print(f"[샘플] {rows[0]}")

# ── 3. DB에 저장 ─────────────────────────
# INSERT INTO disclosures (rcept_no, corp_code, report_nm, rcept_dt, type)
# VALUES (%s, %s, %s, %s, %s) ON CONFLICT (rcept_no) DO NOTHING;
# with 연결 → 커서 → executemany → commit
sql = (
    "INSERT INTO disclosures (rcept_no, corp_code, report_nm, rcept_dt, type)"
    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (rcept_no) DO NOTHING;"
)

with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.executemany(sql, rows)

    conn.commit()

# 저장 완료 출력
print(f"[저장] disclosures에 {len(rows)}개 저장 완료")
