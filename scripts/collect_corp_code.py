"""
DART 고유번호(corp_code) 조회 스크립트

종목코드(6자리)를 넣으면 DART 고유번호(8자리)와 회사명을 찾아준다.
예: 005930 -> 00126380 (삼성전자)
"""

# 표준 라이브러리
import io
import os
import zipfile
import xml.etree.ElementTree as ET

# 외부 라이브러리
import requests
from dotenv import load_dotenv


# ── 1. 인증키 불러오기 ─────────────────────────────
# 키를 코드에 직접 쓰지 않고 .env에서 읽는다 (GitHub 노출 방지)
load_dotenv()                        # .env 내용을 환경변수로 등록
API_KEY = os.getenv("DART_API_KEY")  # 등록된 환경변수에서 키 꺼내기


# ── 2. DART에 전체 회사 목록 요청 ───────────────────
# 응답은 텍스트가 아니라 ZIP 파일(bytes)로 온다
response = requests.get(
    url="https://opendart.fss.or.kr/api/corpCode.xml",
    params={"crtfc_key": API_KEY},
)

# ZIP을 열기 전에 제대로 받았는지 먼저 확인한다
# (키가 틀리면 ZIP 대신 작은 에러 메시지가 온다)
print("상태 코드:", response.status_code)
print("응답 형식:", response.headers.get("Content-Type"))
print("응답 크기:", len(response.content), "bytes")


# ── 3. ZIP 열어서 XML 꺼내기 ───────────────────────
# ZipFile은 bytes를 바로 못 받아서 BytesIO로 '파일처럼' 감싼다
with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
    print(zf.namelist())                 # ZIP 안 파일 목록: ['CORPCODE.xml']
    xml_bytes = zf.read("CORPCODE.xml")  # 파일 내용을 bytes로 꺼내 변수에 담기
                                         # (with가 끝나 ZIP이 닫혀도 내용은 남아 있음)


# ── 4. XML 구조 확인 ──────────────────────────────
# 전체는 너무 길어서 앞 500바이트만 글자로 바꿔 본다
print(xml_bytes[:500].decode("utf-8"))


# ── 5. 종목코드로 회사 찾기 ─────────────────────────
root = ET.fromstring(xml_bytes)  # XML을 트리로 읽고 맨 바깥 태그(<result>)를 얻는다


def find_corp_code(root, stock_code):
    """종목코드로 DART 고유번호와 회사명을 찾는다. 없으면 None."""
    for item in root.iter("list"):  # <list> = 회사 하나
        # 비상장 회사는 stock_code가 공백(" ")이라 strip()으로 정리하고 비교한다
        if item.findtext("stock_code").strip() == stock_code:
            corp_code = item.findtext("corp_code")
            corp_name = item.findtext("corp_name")
            return corp_code, corp_name
    return None  # 끝까지 돌았는데 못 찾음


# ── 6. 관심 종목으로 실행 ──────────────────────────
for code in ["005930", "000660", "999999"]:  # 999999는 없는 코드 테스트용
    result = find_corp_code(root, code)
    if result is None:
        print(f"{code} -> 찾을 수 없음")
    else:
        corp_code, corp_name = result
        print(f"{code} -> {corp_code} ({corp_name})")