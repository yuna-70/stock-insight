"""
공시 원문 탐색 스크립트

실적 공시 하나의 원문(document.xml)을 받아서
표(table)를 행 단위로 꺼내 구조를 확인한다.
"""

# 표준 라이브러리
import io
import os
import zipfile

# 외부 라이브러리
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


# ── 1. 인증키 불러오기 ─────────────────────────────
load_dotenv()
API_KEY = os.getenv("DART_API_KEY")

if not API_KEY:
    raise SystemExit(".env에 DART_API_KEY가 없습니다.")


# ── 2. 공시 목록에서 실적 공시의 접수번호 찾기 ────────
list_response = requests.get(
    url="https://opendart.fss.or.kr/api/list.json",
    params={
        "crtfc_key": API_KEY,
        "corp_code": "00126380",  # 삼성전자
        "bgn_de": "20260825",
        "end_de": "20261125",
        "page_count": 100,
    },
)
data = list_response.json()

rcept_no = None
for item in data["list"]:
    report_nm = item["report_nm"].strip()  # 이름 뒤 공백 제거
    # 정정 공시([기재정정])는 빼고, 원래 실적 공시만 찾는다
    if "영업(잠정)실적" in report_nm and not report_nm.startswith("[기재정정]"):
        rcept_no = item["rcept_no"]
        print("찾은 공시:", item["rcept_dt"], report_nm, rcept_no)
        break  # 목록이 최신순이라 처음 찾은 게 가장 최근 것

if rcept_no is None:
    raise SystemExit("실적 공시를 찾지 못했습니다.")


# ── 3. 공시 원문 요청 (ZIP으로 온다) ─────────────────
doc_response = requests.get(
    url="https://opendart.fss.or.kr/api/document.xml",
    params={"crtfc_key": API_KEY, "rcept_no": rcept_no},
)

# ZIP을 열기 전에 제대로 받았는지 확인
print("상태 코드:", doc_response.status_code)
print("응답 형식:", doc_response.headers.get("Content-Type"))
print("응답 크기:", len(doc_response.content), "bytes")


# ── 4. ZIP 열어서 원문 꺼내기 ───────────────────────
with zipfile.ZipFile(io.BytesIO(doc_response.content)) as zf:
    names = zf.namelist()
    print("ZIP 안 파일:", names)

    # 공시마다 파일 이름이 달라서, 이름을 직접 쓰지 않고 목록의 첫 번째를 꺼낸다
    doc_bytes = zf.read(names[0])

# 구조 확인용 (확인이 끝나서 꺼둠, 필요하면 # 지우고 다시 보기)
# print(doc_bytes[:3000].decode("utf-8", errors="replace"))


# ── 5. HTML 읽기 ──────────────────────────────────
# 파일 이름은 .xml이지만 내용은 HTML이라 BeautifulSoup으로 읽는다
# (정해진 데이터 XML → ElementTree / HTML → BeautifulSoup)
soup = BeautifulSoup(doc_bytes, "html.parser")
print("제목:", soup.title.get_text())


# ── 6. 표를 행(tr) 단위로 꺼내기 ─────────────────────
rows = soup.find_all("tr")  # 표의 모든 행
print("행 개수:", len(rows))

print("\n[표 내용]")
for row in rows:
    cells = row.find_all("td")  # 이 행 안의 모든 칸
    # 칸마다 글자만 꺼내고 앞뒤 공백 정리
    texts = [cell.get_text(strip=True) for cell in cells]
    print(texts)
