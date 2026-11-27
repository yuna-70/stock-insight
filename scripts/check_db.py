"""
DB 연결 확인 스크립트

.env의 DATABASE_URL로 도커 안의 PostgreSQL에 접속해서
버전과 테이블 목록을 출력한다.

실행 전: docker ps로 stock-insight-db 컨테이너가 Up인지 확인
실행:    python scripts/check_db.py  (저장소 맨 위에서)
"""

import os

import psycopg
from dotenv import load_dotenv

# ── 1. DB 주소 불러오기 ──────────────────────────────
# 주소 안에 비밀번호가 있어서 코드에 쓰지 않고 .env에서 꺼낸다
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# 없거나 비어 있으면 접속해봤자 실패하니까 여기서 이유를 보여주고 멈춤
if not DATABASE_URL:
    raise SystemExit(".env에서 DATABASE_URL을 찾을 수 없습니다.")

# ── 2. DB에 접속해서 확인 ────────────────────────────
# with로 열면 끝날 때 연결과 커서를 알아서 닫아준다 (ZIP 열 때와 같은 원리)
with psycopg.connect(DATABASE_URL) as conn:
    # 커서: SQL을 보내고 결과를 받아오는 손
    with conn.cursor() as cur:

        # 2-1. 버전 확인: 이 줄이 나오면 파이썬 ↔ 도커 DB 연결 성공
        cur.execute("SELECT version();")
        row = cur.fetchone()  # 결과 한 줄 = 튜플 ('PostgreSQL 16.16 ...',)
        print(f"[버전] {row[0]}")

        # 2-2. 테이블 목록 확인: schema.sql로 만든 4개가 다 있는지
        # 커서는 마지막에 보낸 SQL의 결과만 들고 있어서, 질문마다 execute를 새로 한다
        sql = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "ORDER BY table_name;"
        )
        cur.execute(sql)
        rows = cur.fetchall()  # 결과 전부 = 튜플들의 리스트 [('corps',), ...]

        print(f"[테이블] {len(rows)}개")
        for row in rows:
            # 한 줄의 칸 수 = SELECT한 컬럼 수. 지금은 table_name 하나라 [0]
            print(f"- {row[0]}")