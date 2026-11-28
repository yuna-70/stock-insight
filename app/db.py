"""
DB 연결 담당

.env의 DATABASE_URL로 PostgreSQL에 연결하는 함수를 한 곳에 둔다.
services들은 여기서 연결을 받아 쓴다.
→ 주소·비밀번호를 여러 파일에 흩어놓지 않고, 연결 방식을 바꿀 때도 이 파일만 고치면 된다.
"""

import os

import psycopg
from dotenv import load_dotenv

# .env를 환경변수로 등록하고 DB 주소 꺼내기 (주소 안에 비밀번호가 있어서 코드에 쓰지 않음)
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# 서버는 스크립트가 아니라서 SystemExit 대신 에러를 낸다
# → uvicorn을 켤 때 바로 이 메시지가 보여서, 요청이 들어온 뒤에야 알게 되는 일을 막는다
if not DATABASE_URL:
    raise RuntimeError(".env에서 DATABASE_URL을 찾을 수 없습니다.")


def get_connection() -> psycopg.Connection:
    """DB 연결을 하나 만들어 돌려준다.

    쓰는 쪽에서 with로 열어야 끝날 때 연결이 닫힌다.
        with get_connection() as conn:
            ...
    """
    # connect_timeout: 도커 컨테이너가 꺼져 있을 때 오래 멈춰 있지 않고 5초 안에 에러로 알려줌
    return psycopg.connect(DATABASE_URL, connect_timeout=5)