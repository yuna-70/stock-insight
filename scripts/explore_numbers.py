"""
실적 공시 숫자 파싱 탐색 스크립트

실적 공시 원문(document.xml) 안의 표를 읽어서
(항목, 구분, 기간, 값, 단위) 튜플로 바꾼다. → 4일차 load_numbers.py의 재료

"숫자는 코드, 해석은 LLM": LLM에게 표를 통째로 주면 숫자를 틀리게 옮길 수 있어서
숫자는 코드가 정확하게 꺼내고, LLM은 나중에 이 숫자를 '해석'만 한다.

실행: python scripts/explore_numbers.py                  (기본: 삼성전자 26.3Q 실적)
      python scripts/explore_numbers.py 20261028XXXXXX    (다른 접수번호로 테스트)
"""

import io
import os
import sys
import zipfile

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
DEFAULT_RCEPT_NO = "20261029800087"  # 삼성전자 연결재무제표기준영업(잠정)실적 (2026-10-29)

# 숫자 줄에만 있는 구분 값 → 이 줄만 골라낸다
# (실적기간, IR팀, 전화번호 같은 줄은 여기에 해당하지 않아서 자동으로 빠짐)
SCOPES = ("당해실적", "누계실적")

# 8칸 줄 기준: (칸 위치, 기간 이름, 단위)
# 0번 칸은 구분(scope), 4·7번 칸은 흑자적자전환(글자)이라 v1에선 저장하지 않음
# → 저장할 칸을 늘리거나 바꿀 때는 이 표만 고치면 된다
COLUMNS = [
    (1, "당기", "억원"),
    (2, "전기", "억원"),
    (3, "전기대비", "%"),
    (5, "전년동기", "억원"),
    (6, "전년동기대비", "%"),
]


def to_number(text: str) -> float | None:
    """표의 숫자 칸(글자)을 숫자로 바꾼다.

    '1,952,532' → 1952532.0 / '13.85' → 13.85 / '-' 또는 빈칸 → None
    0과 None은 뜻이 다르다(0 = 진짜 0, None = 값 없음)
    """
    text = text.strip()
    if text in ("-", ""):
        return None
    return float(text.replace(",", ""))


def fetch_table_rows(api_key: str, rcept_no: str) -> list[list[str]]:
    """원문을 받아서 표의 모든 행을 [['칸', '칸', ...], ...] 모양으로 돌려준다.

    네트워크(DART)를 쓰는 부분은 여기에만 둔다 → parse_earnings는 인터넷 없이 테스트 가능
    """
    response = requests.get(
        DOCUMENT_URL,
        params={"crtfc_key": api_key, "rcept_no": rcept_no},
        timeout=10,
    )

    # 정상이면 ZIP이 오고, 키나 접수번호가 틀리면 ZIP 대신 에러 메시지(XML)가 온다
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = zf.namelist()
            # 공시마다 ZIP 안 파일 이름이 달라서 이름 대신 첫 번째 파일을 꺼낸다
            doc_bytes = zf.read(names[0])
    except zipfile.BadZipFile:
        raise ValueError(f"ZIP이 아닌 응답이 왔습니다: {response.text[:200]}")

    # 이름은 .xml이지만 내용은 HTML이라 BeautifulSoup으로 읽는다
    soup = BeautifulSoup(doc_bytes, "html.parser")

    rows = []
    for tr in soup.find_all("tr"):
        # 칸 태그(<td>) 대신 안쪽 글자만, 앞뒤 공백 정리해서
        rows.append([td.get_text(strip=True) for td in tr.find_all("td")])

    # 조용한 버그 방지: 표가 하나도 없으면 주소·접수번호가 잘못됐을 가능성이 크다
    if not rows:
        raise ValueError(f"{rcept_no}: 원문에서 표(tr)를 찾지 못했습니다.")

    return rows


def parse_earnings(rows: list[list[str]]) -> list[tuple]:
    """실적 표의 행들을 (항목, 구분, 기간, 값, 단위) 튜플 리스트로 바꾼다.

    표의 함정 처리:
    - rowspan: '누계실적' 줄에는 항목 이름이 없다(8칸) → 바로 위 9칸 줄의 항목을 기억해서 쓴다
    - 쉼표 숫자, '-' → to_number
    - 숫자 줄이 아닌 줄 → 구분 값이 SCOPES가 아니면 건너뛴다
    """
    results = []
    current_item = None  # 마지막으로 본 항목 이름 (예: 매출액)

    for cells in rows:
        # 9칸 = 항목 이름이 있는 줄 → 이름을 기억하고 떼어내서 8칸으로 맞춘다
        # (순서 중요: 떼어낸 뒤에야 cells[0]이 구분이 된다)
        if len(cells) == 9:
            current_item = cells[0]
            cells = cells[1:]

        # 숫자 줄만 남기기. 칸이 모자란 줄(제목 줄 등)도 여기서 걸러서 IndexError를 막는다
        if len(cells) != 8 or cells[0] not in SCOPES:
            continue

        # 항목 이름을 한 번도 못 봤는데 누계 줄이 나오면 표 모양이 예상과 다르다는 뜻
        if current_item is None:
            raise ValueError(f"항목 이름 없이 숫자 줄이 나왔습니다: {cells}")

        scope = cells[0]
        for index, period, unit in COLUMNS:
            value = to_number(cells[index])
            results.append((current_item, scope, period, value, unit))

    return results


def main():
    load_dotenv()
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        raise SystemExit(".env에서 DART_API_KEY를 찾을 수 없습니다.")

    # 실행할 때 접수번호를 붙이면 그 공시로, 안 붙이면 기본 공시로
    rcept_no = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RCEPT_NO

    rows = fetch_table_rows(api_key, rcept_no)
    results = parse_earnings(rows)

    # 검증: 행 수, 숫자 수, 항목 목록 (삼성 26.3Q 기준 31행, 50개, 항목 5개)
    items = list(dict.fromkeys(r[0] for r in results))  # 순서 유지하며 중복 제거
    print(f"[공시] {rcept_no}")
    print(f"[행] {len(rows)}개")
    print(f"[숫자] {len(results)}개 (항목 {len(items)}개 × 당해/누계 × 기간 {len(COLUMNS)}개)")
    print(f"[항목] {items}")
    for r in results:
        print(r)


# 직접 실행할 때만 main() 실행 (load_numbers.py에서 parse_earnings만 import할 수 있게)
if __name__ == "__main__":
    main()