"""
회사코드를 DB(corps)에 저장하는 스크립트

DART corpCode.xml을 받아서 상장사(stock_code가 있는 회사)만 corps 테이블에 넣는다.
여러 번 실행해도 안전하게: 이미 있는 회사는 종목코드·이름만 최신으로 고친다.

실행 전: docker ps로 stock-insight-db 컨테이너가 Up인지 확인
실행:    python scripts/load_corps.py  (저장소 맨 위에서)
"""

import io
import os
import zipfile
import xml.etree.ElementTree as ET

import psycopg
import requests
from dotenv import load_dotenv

# ── 1. 키와 DB 주소 불러오기 ─────────────────────────
# 둘 다 비밀 정보라 코드에 쓰지 않고 .env에서 꺼낸다
load_dotenv()
API_KEY = os.getenv("DART_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# 하나라도 없으면 요청·접속이 실패하니까 여기서 멈춤
if not API_KEY or not DATABASE_URL:
    raise SystemExit(".env에서 DART_API_KEY 또는 DATABASE_URL을 찾을 수 없습니다.")

# ── 2. corpCode.xml 받아서 XML 읽기 ──────────────────
# 응답은 ZIP이라: 상자 열기 → 안의 CORPCODE.xml 꺼내기 → XML로 읽기
response = requests.get(
    url="https://opendart.fss.or.kr/api/corpCode.xml",
    params={"crtfc_key": API_KEY},
)

with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
    xml_bytes = zf.read("CORPCODE.xml")

root = ET.fromstring(xml_bytes)

# ── 3. 상장사만 모으기 ───────────────────────────────
# 서비스 검색 기준이 종목코드라서, 종목코드 없는 비상장사는 저장하지 않는다
# (약 10만 개 중 상장사 약 4천 개)
rows = []

for item in root.iter("list"):
    # 비상장사는 stock_code가 공백(" ")으로 와서 strip해야 빈 글자로 판단 가능
    stock_code = item.findtext("stock_code").strip()

    if stock_code == "":
        continue  # 비상장사 → 이번 회사는 건너뛰고 다음으로

    # 튜플 순서 = 아래 INSERT의 컬럼 순서 (corp_code, stock_code, corp_name)
    rows.append((item.findtext("corp_code"), stock_code, item.findtext("corp_name")))

# 넣기 전에 개수 + 샘플 한 줄로 검증 (개수만 맞고 칸이 뒤바뀐 실수를 잡으려고)
print(f"[수집] 상장사 {len(rows)}개")
print(f"[샘플] {rows[0]}")

# ── 4. DB에 한 번에 저장 ─────────────────────────────
# 값은 SQL에 직접 붙이지 않고 %s 자리로 따로 넘긴다
#   → 회사명에 ' 같은 글자가 있어도 안전 (SQL 인젝션 방지)
# ON CONFLICT: 이미 있는 corp_code면 에러 대신 최신 값으로 고침 → 여러 번 실행해도 안전
sql = (
    "INSERT INTO corps (corp_code, stock_code, corp_name) "
    "VALUES (%s, %s, %s) "
    "ON CONFLICT (corp_code) DO UPDATE "
    "SET stock_code = EXCLUDED.stock_code, corp_name = EXCLUDED.corp_name;"
)

with psycopg.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        # rows의 튜플 하나마다 같은 SQL 실행 (4천 번 따로 보내는 것보다 훨씬 빠름)
        cur.executemany(sql, rows)

    # commit을 해야 확정. 안 하면 끝날 때 전부 취소된다
    conn.commit()

print(f"[저장] corps에 {len(rows)}개 저장 완료")