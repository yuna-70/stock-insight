"""
공시 목록 탐색 스크립트

삼성전자의 최근 3개월 공시 목록을 받아서
어떤 종류의 공시가 몇 번 나왔는지 확인한다.
"""

# 표준 라이브러리
import os
from collections import Counter

# 외부 라이브러리
import requests
from dotenv import load_dotenv


# ── list.json 응답 구조 메모 ──────────────────────
# 바깥:
#   status / message : DART 처리 결과 ("000" = 정상)
#   total_count      : 기간 안 전체 공시 수
#   total_page       : 전체 페이지 수 (page_no로 다음 페이지 요청)
#   list             : 이번 페이지의 공시 목록
#
# 공시 하나(list의 항목):
#   rcept_no  : 접수번호 → 공시 고유 번호, 원문 조회 열쇠
#   rcept_dt  : 접수일 (YYYYMMDD)
#   report_nm : 보고서 이름 → 공시 종류 구분 (뒤에 공백이 붙어 올 수 있음!)
#   corp_cls  : 시장 구분 (Y 유가증권, K 코스닥 등)
#   flr_nm    : 제출인


# ── 1. 인증키 불러오기 ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("DART_API_KEY")

if not API_KEY:
    raise SystemExit(".env에 DART_API_KEY가 없습니다.")


# ── 2. 삼성전자 최근 공시 목록 요청 ──────────────────
response = requests.get(
    url="https://opendart.fss.or.kr/api/list.json",
    params={
        "crtfc_key": API_KEY,
        "corp_code": "00126380",  # 삼성전자 고유번호 (collect_corp_code.py에서 찾은 값)
        "bgn_de": "20260825",     # 시작일 (YYYYMMDD)
        "end_de": "20261125",     # 종료일 (YYYYMMDD)
        "page_count": 100,        # 한 번에 받을 공시 개수
    },
)


# ── 3. JSON으로 바꾸고 DART 상태 확인 ────────────────
data = response.json()  # 응답 글자(JSON)를 파이썬 딕셔너리로 바꾼다

# HTTP 200이어도 DART 안에서는 실패일 수 있어서 status를 따로 확인한다
print("HTTP 상태:", response.status_code)
print("DART 상태:", data["status"], data["message"])

if data["status"] != "000":
    raise SystemExit("DART 요청 실패: " + data["message"])


# ── 4. 공시 목록 출력 ─────────────────────────────
# total_count(전체)와 len(list)(이번 페이지)가 다르면 아직 못 받은 페이지가 있다
print("총 공시 수:", data["total_count"])
print("이번에 받은 수:", len(data["list"]))

print("\n[목록]")
for item in data["list"]:  # 공시 하나 = 딕셔너리 하나
    report_nm = item["report_nm"].strip()  # 이름 뒤 공백 제거
    print(f"{item['rcept_dt']} | {report_nm}")


# ── 5. 종류별 개수 세기 (딕셔너리로 직접) ─────────────
counts = {}
for item in data["list"]:
    name = item["report_nm"].strip()
    counts[name] = counts.get(name, 0) + 1  # 처음 보는 이름이면 0에서 시작

print("\n[종류별 개수 - 딕셔너리]")
for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
    print(f"{name}: {count}")


# ── 6. 같은 일을 Counter로 ─────────────────────────
counter = Counter(item["report_nm"].strip() for item in data["list"])

print("\n[종류별 개수 - Counter]")
for name, count in counter.most_common():  # 많은 순으로
    print(f"{name}: {count}")
